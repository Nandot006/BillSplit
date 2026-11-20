"""Claude-backed OCR + taxonomy (app/services/ocr/claude.py), plus the
receipt regression fixtures in tests/fixtures/receipts/. A fake client
stands in for the anthropic SDK, so nothing here touches the network."""

import json
import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.bill import Bill, BillStatus
from app.models.group import Group
from app.models.taxonomy import BaseType, DietaryFlag, FlavorTag
from app.models.user import User
from app.services.ocr.base import OCRProviderError
from app.services.ocr.claude import (
    ClaudeReceiptOCRProvider,
    ClaudeTaxonomyClassifier,
    ItemTags,
    ItemTagsBatch,
    ReceiptExtraction,
    build_taxonomy_prompt,
    detect_image_media_type,
    receipt_extraction_to_ocr_result,
)
from app.services.ocr.pipeline import process_bill
from app.services.ocr.taxonomy_classifier import TaxonomyClassificationError

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "receipts"
FIXTURES = sorted(FIXTURE_DIR.glob("*.json"))

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 16
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class FakeMessages:
    def __init__(self, outputs=None, error=None):
        self.outputs = list(outputs or [])
        self.error = error
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        output = self.outputs.pop(0)
        return SimpleNamespace(
            parsed_output=output, usage=SimpleNamespace(input_tokens=1, output_tokens=1)
        )


class FakeClient:
    def __init__(self, outputs=None, error=None):
        self.messages = FakeMessages(outputs, error)


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _money(value):
    return None if value is None else Decimal(value)


# --- regression fixtures -----------------------------------------------------


@pytest.mark.parametrize("fixture_path", FIXTURES, ids=lambda p: p.stem)
def test_receipt_fixture_normalizes_as_expected(fixture_path):
    fixture = _load(fixture_path)
    extraction = ReceiptExtraction.model_validate(fixture["claude_response"])
    expected = fixture["expected"]

    result = receipt_extraction_to_ocr_result(extraction)

    assert result.merchant_name == expected["merchant_name"]
    assert result.tax_total == _money(expected["tax_total"])
    assert result.tip_total == _money(expected["tip_total"])
    assert [(i.parsed_name, i.price, i.quantity) for i in result.line_items] == [
        (i["parsed_name"], Decimal(i["price"]), i["quantity"]) for i in expected["items"]
    ]


@pytest.mark.parametrize("fixture_path", FIXTURES, ids=lambda p: p.stem)
def test_receipt_fixture_through_full_pipeline(fixture_path, db_session_factory):
    fixture = _load(fixture_path)
    expected = fixture["expected"]
    db = db_session_factory()
    user = User(id=uuid.uuid4(), email="u@example.com")
    db.add(user)
    db.flush()
    group = Group(name="Fixture Group", creator_user_id=user.id)
    db.add(group)
    db.flush()
    bill = Bill(group_id=group.id, status=BillStatus.PROCESSING, image_storage_path="x.jpg")
    db.add(bill)
    db.commit()

    receipt_client = FakeClient([ReceiptExtraction.model_validate(fixture["claude_response"])])
    item_count = len(expected["items"])
    taxonomy_client = FakeClient(
        [
            ItemTagsBatch(
                items=[
                    ItemTags(index=i, base_type=BaseType.ENTREE, flavor_tags=[], dietary_flags=[])
                    for i in range(item_count)
                ]
            )
        ]
    )

    process_bill(
        db,
        bill,
        JPEG_BYTES,
        ClaudeReceiptOCRProvider(client=receipt_client, model="test-model"),
        ClaudeTaxonomyClassifier(client=taxonomy_client, model="test-model"),
    )
    db.refresh(bill)

    if expected["items"]:
        assert bill.status == BillStatus.NEEDS_REVIEW
        assert bill.subtotal == Decimal(expected["subtotal"])
        assert bill.merchant_name == expected["merchant_name"]
        assert sorted(i.parsed_name for i in bill.items) == sorted(
            i["parsed_name"] for i in expected["items"]
        )
        assert all(i.base_type == BaseType.ENTREE for i in bill.items)
    else:
        assert bill.status == BillStatus.NEEDS_MANUAL_ENTRY
        assert bill.items == []
        assert taxonomy_client.messages.calls == []  # no items -> no tagging call
    db.close()


# --- ClaudeReceiptOCRProvider ------------------------------------------------


def test_detect_image_media_type():
    assert detect_image_media_type(JPEG_BYTES) == "image/jpeg"
    assert detect_image_media_type(PNG_BYTES) == "image/png"
    assert detect_image_media_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert detect_image_media_type(b"GIF89a....") == "image/gif"
    assert detect_image_media_type(b"\x00\x00\x00\x18ftypheic") is None  # HEIC


def test_receipt_provider_sends_image_and_schema():
    client = FakeClient([ReceiptExtraction(is_receipt=True, items=[])])
    ClaudeReceiptOCRProvider(client=client, model="claude-haiku-5-5").extract(PNG_BYTES)

    call = client.messages.calls[0]
    assert call["model"] == "claude-haiku-5-5"
    assert call["output_format"] is ReceiptExtraction
    image_block = call["messages"][0]["content"][0]
    assert image_block["type"] == "image"
    assert image_block["source"]["media_type"] == "image/png"


def test_receipt_provider_rejects_unsupported_format_without_calling_api():
    client = FakeClient()
    with pytest.raises(OCRProviderError):
        ClaudeReceiptOCRProvider(client=client).extract(b"not an image")
    assert client.messages.calls == []


def test_receipt_provider_wraps_api_errors():
    client = FakeClient(error=RuntimeError("rate limited"))
    with pytest.raises(OCRProviderError):
        ClaudeReceiptOCRProvider(client=client).extract(JPEG_BYTES)


def test_receipt_provider_without_api_key_raises(monkeypatch):
    import app.services.ocr.claude as claude_module

    monkeypatch.setattr(claude_module.settings, "ANTHROPIC_API_KEY", None)
    with pytest.raises(OCRProviderError):
        ClaudeReceiptOCRProvider().extract(JPEG_BYTES)


# --- ClaudeTaxonomyClassifier ------------------------------------------------


def test_taxonomy_prompt_numbers_items():
    prompt = build_taxonomy_prompt(["Masala Dosa", "Filter Coffee"])
    assert "0. Masala Dosa" in prompt
    assert "1. Filter Coffee" in prompt
    # Hard-filter safety: the prompt must ask for the "obvious" flags too,
    # or anyone who doesn't drink / avoids pork is never matched to food.
    assert "no-alcohol" in prompt and "almost all food" in prompt
    assert "no-pork / no-beef" in prompt


def test_classify_many_is_one_call_and_maps_by_index():
    batch = ItemTagsBatch(
        items=[
            ItemTags(
                index=1,
                base_type=BaseType.DRINK_NON_ALCOHOLIC,
                flavor_tags=[],
                dietary_flags=[DietaryFlag.NO_ALCOHOL, DietaryFlag.NO_ALCOHOL],
            ),
            ItemTags(
                index=0,
                base_type=BaseType.ENTREE,
                flavor_tags=[FlavorTag.SAVORY, FlavorTag.SPICY],
                dietary_flags=[DietaryFlag.VEGETARIAN],
            ),
            ItemTags(index=7, base_type=BaseType.SIDE, flavor_tags=[], dietary_flags=[]),
        ]
    )
    client = FakeClient([batch])
    results = ClaudeTaxonomyClassifier(client=client).classify_many(
        ["Masala Dosa", "Filter Coffee", "Unreadable"]
    )

    assert len(client.messages.calls) == 1
    assert results[0].base_type == BaseType.ENTREE
    assert results[0].dietary_flags == [DietaryFlag.VEGETARIAN]
    assert results[1].base_type == BaseType.DRINK_NON_ALCOHOLIC
    assert results[1].dietary_flags == [DietaryFlag.NO_ALCOHOL]  # de-duplicated
    assert results[2] is None  # index 7 out of range is ignored; item 2 left untagged


def test_classify_many_wraps_api_errors():
    client = FakeClient(error=RuntimeError("boom"))
    with pytest.raises(TaxonomyClassificationError):
        ClaudeTaxonomyClassifier(client=client).classify_many(["Tea"])


def test_classify_many_empty_input_makes_no_call():
    client = FakeClient()
    assert ClaudeTaxonomyClassifier(client=client).classify_many([]) == []
    assert client.messages.calls == []


def test_whole_batch_failure_still_creates_untagged_items(db_session_factory):
    db = db_session_factory()
    user = User(id=uuid.uuid4(), email="u@example.com")
    db.add(user)
    db.flush()
    group = Group(name="G", creator_user_id=user.id)
    db.add(group)
    db.flush()
    bill = Bill(group_id=group.id, status=BillStatus.PROCESSING, image_storage_path="x.jpg")
    db.add(bill)
    db.commit()

    receipt = ReceiptExtraction(
        is_receipt=True,
        items=[{"name": "Idli", "quantity": 2, "line_total": 60.0}],
    )
    process_bill(
        db,
        bill,
        JPEG_BYTES,
        ClaudeReceiptOCRProvider(client=FakeClient([receipt])),
        ClaudeTaxonomyClassifier(client=FakeClient(error=RuntimeError("down"))),
    )
    db.refresh(bill)
    assert bill.status == BillStatus.NEEDS_REVIEW
    assert [(i.parsed_name, i.price, i.quantity, i.base_type) for i in bill.items] == [
        ("Idli", Decimal("30.00"), 2, None)
    ]
    db.close()


def test_switch_to_manual_entry_during_ocr_discards_result(db_session_factory):
    """design.md SS13: manual entry is always available on a bill stuck in
    processing. If the user switches while Claude is still reading the
    receipt, the late OCR result must not overwrite their choice."""
    db = db_session_factory()
    user = User(id=uuid.uuid4(), email="u@example.com")
    db.add(user)
    db.flush()
    group = Group(name="G", creator_user_id=user.id)
    db.add(group)
    db.flush()
    bill = Bill(group_id=group.id, status=BillStatus.PROCESSING, image_storage_path="x.jpg")
    db.add(bill)
    db.commit()
    bill_id = bill.id

    class SwitchingProvider(ClaudeReceiptOCRProvider):
        def extract(self, image_bytes):
            other = db_session_factory()
            other.get(Bill, bill_id).status = BillStatus.NEEDS_MANUAL_ENTRY
            other.commit()
            other.close()
            return receipt_extraction_to_ocr_result(
                ReceiptExtraction(
                    is_receipt=True, items=[{"name": "Tea", "quantity": 1, "line_total": 20.0}]
                )
            )

    process_bill(
        db, bill, JPEG_BYTES, SwitchingProvider(client=FakeClient()), ClaudeTaxonomyClassifier()
    )
    db.refresh(bill)
    assert bill.status == BillStatus.NEEDS_MANUAL_ENTRY
    assert bill.items == []
    db.close()
