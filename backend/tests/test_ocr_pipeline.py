import uuid
from decimal import Decimal

import pytest

from app.models.bill import Bill, BillStatus
from app.models.group import Group
from app.models.person import Person
from app.models.person_taxonomy_score import PersonTaxonomyScore
from app.models.taxonomy import BaseType, TaxonomySource, TaxonomyValue
from app.models.user import User
from app.services.ocr.base import OCRLineItem, OCRProvider, OCRProviderError, OCRResult
from app.services.ocr.pipeline import process_bill
from app.services.ocr.taxonomy_classifier import (
    TaxonomyClassification,
    TaxonomyClassificationError,
    TaxonomyClassifier,
)
from tests.bill_helpers import add_whole_group_as_participants

# Provider-specific parsing (Claude) is covered in tests/test_claude_ocr.py.
# This file covers the provider-agnostic pipeline with fakes.


# --- process_bill: the OCR -> taxonomy -> prediction pipeline, with fakes ---


class FakeOCRProvider(OCRProvider):
    def __init__(self, result: OCRResult | None = None, error: Exception | None = None):
        self._result = result
        self._error = error

    def extract(self, image_bytes: bytes) -> OCRResult:
        if self._error is not None:
            raise self._error
        return self._result


class FakeTaxonomyClassifier(TaxonomyClassifier):
    def __init__(self, classifications: dict[str, TaxonomyClassification] | None = None):
        self._classifications = classifications or {}

    def classify(self, item_name: str) -> TaxonomyClassification:
        if item_name not in self._classifications:
            raise TaxonomyClassificationError(f"no fake classification for {item_name!r}")
        return self._classifications[item_name]


@pytest.fixture()
def db(db_session_factory):
    session = db_session_factory()
    yield session
    session.close()


@pytest.fixture()
def bill_in_group(db):
    creator = User(id=uuid.uuid4(), email="creator@example.com")
    db.add(creator)
    db.flush()
    group = Group(name="Lunch Crew", creator_user_id=creator.id)
    db.add(group)
    db.flush()
    bill = Bill(group_id=group.id, status=BillStatus.PROCESSING, image_storage_path="r/1.jpg")
    db.add(bill)
    db.commit()
    return group, bill


def test_process_bill_happy_path_tags_items_and_predicts(db, bill_in_group):
    group, bill = bill_in_group

    alice = Person(group_id=group.id, display_name="Alice")
    bob = Person(group_id=group.id, display_name="Bob")
    db.add_all([alice, bob])
    db.flush()
    add_whole_group_as_participants(db, bill)
    # Alice loves entrees, Bob doesn't - a clean, confident prediction.
    db.add(
        PersonTaxonomyScore(
            person_id=alice.id,
            taxonomy_value=TaxonomyValue.ENTREE,
            score=0.9,
            is_hard_restriction=False,
            source=TaxonomySource.QUESTIONNAIRE,
        )
    )
    db.add(
        PersonTaxonomyScore(
            person_id=bob.id,
            taxonomy_value=TaxonomyValue.ENTREE,
            score=-0.5,
            is_hard_restriction=False,
            source=TaxonomySource.QUESTIONNAIRE,
        )
    )
    db.commit()

    ocr_result = OCRResult(
        line_items=[
            OCRLineItem(raw_text="Pizza $12.50", parsed_name="Pizza", price=Decimal("12.50"))
        ],
        merchant_name="Pasta Place",
        tax_total=Decimal("1.00"),
    )
    classifier = FakeTaxonomyClassifier(
        {"Pizza": TaxonomyClassification(base_type=BaseType.ENTREE)}
    )

    process_bill(db, bill, b"fake-bytes", FakeOCRProvider(result=ocr_result), classifier)

    db.refresh(bill)
    assert bill.status == BillStatus.NEEDS_REVIEW
    assert bill.merchant_name == "Pasta Place"
    assert bill.tax_total == Decimal("1.00")
    assert len(bill.items) == 1

    item = bill.items[0]
    assert item.base_type == BaseType.ENTREE
    assert len(item.assignments) == 1
    assignment = item.assignments[0]
    assert assignment.person_id == alice.id
    assert assignment.is_predicted is True
    assert assignment.confidence_score == 1.0  # only one eligible candidate's score matters here


def test_process_bill_ocr_failure_falls_back_to_manual_entry(db, bill_in_group):
    _, bill = bill_in_group
    process_bill(
        db,
        bill,
        b"bytes",
        FakeOCRProvider(error=OCRProviderError("boom")),
        FakeTaxonomyClassifier(),
    )
    db.refresh(bill)
    assert bill.status == BillStatus.NEEDS_MANUAL_ENTRY
    assert bill.items == []


def test_process_bill_no_line_items_falls_back_to_manual_entry(db, bill_in_group):
    _, bill = bill_in_group
    process_bill(
        db,
        bill,
        b"bytes",
        FakeOCRProvider(result=OCRResult(line_items=[])),
        FakeTaxonomyClassifier(),
    )
    db.refresh(bill)
    assert bill.status == BillStatus.NEEDS_MANUAL_ENTRY


def test_process_bill_classification_failure_leaves_item_untagged_not_bill_failed(
    db, bill_in_group
):
    _, bill = bill_in_group
    ocr_result = OCRResult(
        line_items=[
            OCRLineItem(
                raw_text="Mystery Item $9.00", parsed_name="Mystery Item", price=Decimal("9.00")
            )
        ]
    )
    process_bill(db, bill, b"bytes", FakeOCRProvider(result=ocr_result), FakeTaxonomyClassifier({}))

    db.refresh(bill)
    assert bill.status == BillStatus.NEEDS_REVIEW
    assert len(bill.items) == 1
    assert bill.items[0].base_type is None


def test_process_bill_ignores_bill_not_currently_processing(db, bill_in_group):
    _, bill = bill_in_group
    bill.status = BillStatus.NEEDS_MANUAL_ENTRY
    db.commit()

    process_bill(db, bill, b"bytes", FakeOCRProvider(result=OCRResult()), FakeTaxonomyClassifier())
    db.refresh(bill)
    assert bill.status == BillStatus.NEEDS_MANUAL_ENTRY  # untouched - not PROCESSING, so no-op
