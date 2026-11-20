import logging
import uuid

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.bill import Bill, BillStatus
from app.models.bill_item import BillItem
from app.models.bill_item_tags import BillItemDietaryFlag, BillItemFlavorTag
from app.services.bills import recompute_bill_totals
from app.services.ocr.base import OCRProvider, OCRProviderError
from app.services.ocr.claude import ClaudeReceiptOCRProvider, ClaudeTaxonomyClassifier
from app.services.ocr.taxonomy_classifier import (
    TaxonomyClassification,
    TaxonomyClassificationError,
    TaxonomyClassifier,
)
from app.services.prediction.pipeline import generate_predictions_for_bill
from app.services.storage import StorageError, fetch_bill_image_bytes

logger = logging.getLogger("billsplit.ocr")


def process_bill(
    db: Session,
    bill: Bill,
    image_bytes: bytes,
    ocr_provider: OCRProvider,
    taxonomy_classifier: TaxonomyClassifier,
) -> None:
    """The OCR -> taxonomy -> prediction pipeline (design.md SS13). Takes an
    injected provider/classifier so it's fully unit-testable with fakes - no
    network, no real API credentials required to verify this logic.

    On any OCR failure or an OCR read with no line items at all, the bill
    falls back to needs_manual_entry rather than staying stuck in
    processing - design.md SS13 is explicit that there's no automatic
    retry loop; a bad photo is a bad photo.
    """
    if bill.status != BillStatus.PROCESSING:
        return

    try:
        ocr_result = ocr_provider.extract(image_bytes)
    except OCRProviderError as exc:
        logger.warning("ocr.failed bill_id=%s error=%s", bill.id, exc)
        _fall_back_to_manual_entry(db, bill)
        return

    # The OCR call is the slow part (seconds). If the user gave up waiting
    # and switched this bill to manual entry meanwhile (design.md SS13:
    # manual entry is always available on a bill stuck in processing),
    # their choice wins - re-read the status before writing anything.
    db.refresh(bill)
    if bill.status != BillStatus.PROCESSING:
        logger.info("ocr.discarded bill_id=%s status=%s", bill.id, bill.status.value)
        return

    if not ocr_result.line_items:
        logger.info("ocr.no_items bill_id=%s", bill.id)
        _fall_back_to_manual_entry(db, bill)
        return

    if ocr_result.merchant_name and not bill.merchant_name:
        bill.merchant_name = ocr_result.merchant_name
    if ocr_result.tax_total is not None:
        bill.tax_total = ocr_result.tax_total
    if ocr_result.tip_total is not None:
        bill.tip_total = ocr_result.tip_total

    try:
        classifications = taxonomy_classifier.classify_many(
            [line.parsed_name for line in ocr_result.line_items]
        )
    except TaxonomyClassificationError as exc:
        # Items still get created, just untagged - the scorer won't have
        # anything to match them against, and a human reviewing
        # needs_review assigns them by hand. Not a reason to fail the bill.
        logger.warning("ocr.taxonomy_failed bill_id=%s error=%s", bill.id, exc)
        classifications = [None] * len(ocr_result.line_items)

    for line, classification in zip(ocr_result.line_items, classifications):
        item = BillItem(
            bill_id=bill.id,
            raw_ocr_text=line.raw_text,
            parsed_name=line.parsed_name,
            price=line.price,
            quantity=line.quantity,
        )
        db.add(item)
        db.flush()
        if classification is not None:
            _apply_classification(db, item, classification)

    db.flush()
    db.refresh(bill)
    recompute_bill_totals(bill)
    # Backend Block 9: run the scorer over the freshly-tagged items before
    # handing the bill to the user for review - "OCR + prediction
    # completion" (CLAUDE.md SS8) is one async unit from the client's POV.
    generate_predictions_for_bill(db, bill)
    bill.status = BillStatus.NEEDS_REVIEW
    db.commit()
    logger.info(
        "ocr.done bill_id=%s items=%d subtotal=%s tax=%s tip=%s",
        bill.id,
        len(bill.items),
        bill.subtotal,
        bill.tax_total,
        bill.tip_total,
    )


def _apply_classification(
    db: Session, item: BillItem, classification: TaxonomyClassification
) -> None:
    item.base_type = classification.base_type
    for tag in classification.flavor_tags:
        db.add(BillItemFlavorTag(bill_item_id=item.id, flavor_tag=tag))
    for flag in classification.dietary_flags:
        db.add(BillItemDietaryFlag(bill_item_id=item.id, dietary_flag=flag))


def _fall_back_to_manual_entry(db: Session, bill: Bill) -> None:
    bill.status = BillStatus.NEEDS_MANUAL_ENTRY
    db.commit()


def run_bill_processing_job(bill_id: uuid.UUID) -> None:
    """Entry point registered with FastAPI's BackgroundTasks (design.md SS8:
    never block the upload request on the OCR provider inline). Opens its
    own DB session rather than reusing the request's - the request's
    session is torn down once the response is sent, which can happen before
    a background task is guaranteed to run.
    """
    db = SessionLocal()
    try:
        bill = db.get(Bill, bill_id)
        if bill is None or bill.status != BillStatus.PROCESSING:
            return
        # routes/bill.py's create_bill only sets PROCESSING when
        # image_storage_path was provided, so this is always set here.
        assert bill.image_storage_path is not None

        try:
            image_bytes = fetch_bill_image_bytes(bill.image_storage_path)
        except StorageError as exc:
            logger.warning("ocr.image_fetch_failed bill_id=%s error=%s", bill.id, exc)
            _fall_back_to_manual_entry(db, bill)
            return

        process_bill(db, bill, image_bytes, ClaudeReceiptOCRProvider(), ClaudeTaxonomyClassifier())
    except Exception:
        # Never leave a bill stuck in processing because of an unexpected
        # bug - log it and hand the bill to manual entry.
        logger.exception("ocr.unexpected_error bill_id=%s", bill_id)
        db.rollback()
        bill = db.get(Bill, bill_id)
        if bill is not None and bill.status == BillStatus.PROCESSING:
            _fall_back_to_manual_entry(db, bill)
    finally:
        db.close()
