"""Claude API implementations of the OCR pipeline's two swappable steps
(decision 2026-11-20, superseding design.md SS1's Google Cloud Vision +
Gemini):

  - ClaudeReceiptOCRProvider (OCRProvider): receipt photo -> line items,
    merchant, tax, tip.
  - ClaudeTaxonomyClassifier (TaxonomyClassifier): item names -> the fixed
    v1 taxonomy (design.md SS3).

Both use structured outputs (a Pydantic schema the API is constrained to),
so the response is always valid JSON of the right shape - no free-text
parsing. The deterministic scorer still does all attribution (CLAUDE.md
SS6); Claude only reads the receipt and tags items.

The anthropic SDK client is built lazily (and can be injected), so this
module imports fine without an API key and tests never hit the network.
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.models.taxonomy import BaseType, DietaryFlag, FlavorTag
from app.services.ocr.base import OCRLineItem, OCRProvider, OCRProviderError, OCRResult
from app.services.ocr.taxonomy_classifier import (
    TaxonomyClassification,
    TaxonomyClassificationError,
    TaxonomyClassifier,
)

logger = logging.getLogger("billsplit.ocr")

CENT = Decimal("0.01")

# Formats the Claude API accepts for images. HEIC isn't one of them - the
# web client converts HEIC to JPEG before upload (design.md SS14).
_MAGIC_BYTES: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
]


def detect_image_media_type(image_bytes: bytes) -> str | None:
    for magic, media_type in _MAGIC_BYTES:
        if image_bytes.startswith(magic):
            return media_type
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return None


def _to_money(value: float) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


# --- Receipt extraction ------------------------------------------------------


class ReceiptLine(BaseModel):
    name: str = Field(description="The item as printed, cleaned up for display.")
    quantity: int = Field(description="How many were ordered on this line. 1 if not shown.")
    line_total: float = Field(
        description="The total price printed for this line (quantity already included)."
    )


class ReceiptExtraction(BaseModel):
    is_receipt: bool = Field(
        description="False if the image is not a readable restaurant/cafe receipt or bill."
    )
    merchant_name: str | None = None
    items: list[ReceiptLine]
    tax_total: float | None = Field(
        default=None,
        description="Sum of all tax lines (GST, CGST + SGST, VAT, sales tax). Null if none.",
    )
    tip_total: float | None = Field(
        default=None,
        description="Sum of tip / gratuity / service charge lines. Null if none.",
    )


RECEIPT_PROMPT = """Read this restaurant or cafe receipt and extract it.

Rules:
- items: one entry per ordered food/drink line. Do NOT include subtotal, total,
  tax, tip, service charge, discount, rounding, change, or payment lines.
- line_total is the price printed on that line (already multiplied by quantity).
- If a line shows a quantity (e.g. "2 x Coke" or a Qty column), put it in quantity;
  otherwise quantity is 1.
- tax_total: add up every tax line (e.g. CGST + SGST). tip_total: add up tip,
  gratuity and service charge lines.
- Use the numbers exactly as printed. Do not guess values you cannot read.
- If this is not a receipt, or no items are readable, set is_receipt to false
  and items to an empty list."""


def receipt_extraction_to_ocr_result(extraction: ReceiptExtraction) -> OCRResult:
    """Normalizes Claude's structured receipt read into the pipeline's
    OCRResult. Kept separate from the API call so it's unit-testable
    against recorded responses (tests/fixtures/receipts/).

    BillItem stores a *unit* price and a quantity (subtotal = price x
    quantity, app/services/bills.py), but receipts print line totals. When a
    line total divides evenly into its quantity we keep both; when it
    doesn't (e.g. 3 for 10.00), we store the line as quantity 1 at the full
    line total, so the bill's subtotal always matches the receipt to the
    cent.
    """
    if not extraction.is_receipt:
        return OCRResult()

    line_items: list[OCRLineItem] = []
    for line in extraction.items:
        name = line.name.strip()
        line_total = _to_money(line.line_total)
        if not name or line_total <= 0:
            # Free items / discounts / unreadable prices: nothing to split.
            continue
        quantity = max(1, line.quantity)
        unit_price = (line_total / quantity).quantize(CENT, rounding=ROUND_HALF_UP)
        if unit_price * quantity != line_total:
            name = f"{name} (x{quantity})"
            quantity, unit_price = 1, line_total
        raw_text = f"{line.quantity} x {line.name} {line_total}"
        line_items.append(
            OCRLineItem(raw_text=raw_text, parsed_name=name, price=unit_price, quantity=quantity)
        )

    return OCRResult(
        line_items=line_items,
        merchant_name=(extraction.merchant_name or "").strip() or None,
        tax_total=_to_money(extraction.tax_total) if extraction.tax_total else None,
        tip_total=_to_money(extraction.tip_total) if extraction.tip_total else None,
    )


def _make_client(api_key: str | None) -> Any:
    if not api_key:
        return None
    import anthropic

    return anthropic.Anthropic(api_key=api_key, max_retries=2, timeout=90.0)


class ClaudeReceiptOCRProvider(OCRProvider):
    def __init__(self, client: Any = None, model: str | None = None):
        self._client = client if client is not None else _make_client(settings.ANTHROPIC_API_KEY)
        self._model = model or settings.CLAUDE_MODEL

    def extract(self, image_bytes: bytes) -> OCRResult:
        if self._client is None:
            raise OCRProviderError("ANTHROPIC_API_KEY is not configured.")

        media_type = detect_image_media_type(image_bytes)
        if media_type is None:
            raise OCRProviderError("Unsupported image format (expected JPEG, PNG, GIF or WebP).")

        import base64

        try:
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=8000,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": base64.standard_b64encode(image_bytes).decode(),
                                },
                            },
                            {"type": "text", "text": RECEIPT_PROMPT},
                        ],
                    }
                ],
                output_format=ReceiptExtraction,
            )
        except Exception as exc:  # network, auth, rate limit, refusal, validation
            raise OCRProviderError(f"Claude receipt read failed: {exc}") from exc

        extraction = response.parsed_output
        if extraction is None:
            raise OCRProviderError("Claude returned no structured receipt output.")

        result = receipt_extraction_to_ocr_result(extraction)
        logger.info(
            "ocr.receipt_read model=%s is_receipt=%s raw_lines=%d kept_items=%d "
            "tax=%s tip=%s input_tokens=%s output_tokens=%s",
            self._model,
            extraction.is_receipt,
            len(extraction.items),
            len(result.line_items),
            result.tax_total,
            result.tip_total,
            getattr(response.usage, "input_tokens", None),
            getattr(response.usage, "output_tokens", None),
        )
        return result


# --- Taxonomy classification -------------------------------------------------


class ItemTags(BaseModel):
    index: int = Field(description="The item's number from the list, starting at 0.")
    base_type: BaseType
    flavor_tags: list[FlavorTag]
    dietary_flags: list[DietaryFlag]


class ItemTagsBatch(BaseModel):
    items: list[ItemTags]


def build_taxonomy_prompt(item_names: list[str]) -> str:
    """Dietary flags are a *hard* filter in the scorer (design.md SS6): a
    person with a restriction is only ever matched to items carrying that
    flag. So a flag left off an item silently excludes everyone with that
    restriction - e.g. someone who doesn't drink would never be given a
    dosa unless it's tagged no-alcohol. The prompt therefore asks for every
    flag the item obviously satisfies, not just the notable ones."""
    numbered = "\n".join(f"{i}. {name}" for i, name in enumerate(item_names))
    return (
        "Tag each item from a restaurant receipt with a fixed taxonomy.\n\n"
        "- base_type: exactly one, the kind of dish or drink.\n"
        "- flavor_tags: zero or more flavors the dish clearly has.\n"
        "- dietary_flags: who the item is SAFE for. People with a restriction are only "
        "ever matched to items carrying that flag, so include every flag the item "
        "satisfies, including the obvious ones:\n"
        "  - no-alcohol: contains no alcohol (almost all food, and every soft drink, "
        "juice, tea or coffee).\n"
        "  - no-pork / no-beef: contains no pork / no beef (vegetarian dishes, chicken, "
        "fish and most drinks qualify).\n"
        "  - vegetarian: no meat, poultry or fish. vegan: also no dairy, egg or honey.\n"
        "  - gluten-free, dairy-free, nut-free: only when the name makes it reasonably "
        "clear (plain rice is gluten-free; paneer is not dairy-free).\n"
        "  Leave a flag out only when the item may well contain that thing.\n\n"
        "Return one entry per item, using the item's number as index.\n\n"
        f"Items:\n{numbered}"
    )


def tag_batch_to_classifications(
    batch: ItemTagsBatch, item_count: int
) -> list[TaxonomyClassification | None]:
    results: list[TaxonomyClassification | None] = [None] * item_count
    for tags in batch.items:
        if 0 <= tags.index < item_count and results[tags.index] is None:
            results[tags.index] = TaxonomyClassification(
                base_type=tags.base_type,
                flavor_tags=list(dict.fromkeys(tags.flavor_tags)),
                dietary_flags=list(dict.fromkeys(tags.dietary_flags)),
            )
    return results


class ClaudeTaxonomyClassifier(TaxonomyClassifier):
    def __init__(self, client: Any = None, model: str | None = None):
        self._client = client if client is not None else _make_client(settings.ANTHROPIC_API_KEY)
        self._model = model or settings.CLAUDE_MODEL

    def classify(self, item_name: str) -> TaxonomyClassification:
        result = self.classify_many([item_name])[0]
        if result is None:
            raise TaxonomyClassificationError(f"No classification returned for {item_name!r}.")
        return result

    def classify_many(self, item_names: list[str]) -> list[TaxonomyClassification | None]:
        if not item_names:
            return []
        if self._client is None:
            raise TaxonomyClassificationError("ANTHROPIC_API_KEY is not configured.")
        try:
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=8000,
                messages=[{"role": "user", "content": build_taxonomy_prompt(item_names)}],
                output_format=ItemTagsBatch,
            )
        except Exception as exc:
            raise TaxonomyClassificationError(f"Claude taxonomy call failed: {exc}") from exc

        batch = response.parsed_output
        if batch is None:
            raise TaxonomyClassificationError("Claude returned no structured taxonomy output.")
        results = tag_batch_to_classifications(batch, len(item_names))
        logger.info(
            "ocr.taxonomy model=%s items=%d tagged=%d",
            self._model,
            len(item_names),
            sum(r is not None for r in results),
        )
        return results
