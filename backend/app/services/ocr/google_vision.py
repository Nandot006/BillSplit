import re
from decimal import Decimal, InvalidOperation

from app.core.config import settings
from app.services.ocr.base import OCRLineItem, OCRProvider, OCRProviderError, OCRResult

# Matches a trailing price like "12.50" or "$12.50" at the end of a line.
_PRICE_PATTERN = re.compile(r"\$?\s*(\d+\.\d{2})\s*$")


class GoogleVisionOCRProvider(OCRProvider):
    """Wraps Google Cloud Vision's text detection (design.md SS1, SS13).

    Vision returns raw text, not structured receipt line items, so this
    class does simple line-based parsing on top: for each non-empty line,
    if it ends in something that looks like a price, treat the rest of the
    line as the item name and use that. This is a plain heuristic, not a
    receipt-specific model - good enough for a clean, well-lit photo, and
    exactly why design.md SS13's needs_manual_entry fallback exists for the
    photos where it isn't.

    The google-cloud-vision package is imported lazily (inside methods, not
    at module load time) so this module - and everything that imports it -
    stays importable even before that package or real credentials exist.
    """

    def __init__(self, credentials_path: str | None = None):
        self._credentials_path = credentials_path or settings.GOOGLE_APPLICATION_CREDENTIALS

    def _client(self):
        from google.cloud import vision

        if self._credentials_path:
            return vision.ImageAnnotatorClient.from_service_account_file(self._credentials_path)
        return vision.ImageAnnotatorClient()

    def extract(self, image_bytes: bytes) -> OCRResult:
        from google.cloud import vision

        try:
            client = self._client()
            response = client.text_detection(image=vision.Image(content=image_bytes))
        except Exception as exc:  # pragma: no cover - network/SDK failures
            raise OCRProviderError(str(exc)) from exc

        if response.error.message:
            raise OCRProviderError(response.error.message)

        raw_text = response.full_text_annotation.text if response.full_text_annotation else ""
        return OCRResult(line_items=self.parse_line_items(raw_text))

    @staticmethod
    def parse_line_items(raw_text: str) -> list[OCRLineItem]:
        items: list[OCRLineItem] = []
        for line in raw_text.splitlines():
            line = line.strip()
            if not line:
                continue
            match = _PRICE_PATTERN.search(line)
            if not match:
                continue
            try:
                price = Decimal(match.group(1))
            except InvalidOperation:
                continue
            name = line[: match.start()].strip(" -\t")
            if not name:
                continue
            items.append(OCRLineItem(raw_text=line, parsed_name=name, price=price))
        return items
