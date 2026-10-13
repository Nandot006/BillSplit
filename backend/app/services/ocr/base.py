from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class OCRLineItem:
    """One line item as read off the receipt. Deliberately dumb (text +
    a guessed name/price) - architecture.md SS4a says to lean on a mature
    provider's receipt-aware mode rather than build item parsing ourselves,
    so this is just the shape their output gets normalized into."""

    raw_text: str
    parsed_name: str
    price: Decimal
    quantity: int = 1


@dataclass
class OCRResult:
    line_items: list[OCRLineItem] = field(default_factory=list)
    merchant_name: str | None = None
    tax_total: Decimal | None = None
    tip_total: Decimal | None = None


class OCRProviderError(Exception):
    """Raised on any OCR failure. design.md SS13: no automatic retry - the
    caller moves the Bill to needs_manual_entry and stops."""


class OCRProvider(ABC):
    """design.md SS1 / architecture.md SS4a: a swappable interface over
    whichever cloud OCR API sits behind it. Google Cloud Vision is the
    chosen v1 implementation (see google_vision.py); an optional local
    Tesseract fallback is explicitly deferred past v1 (design.md SS16)."""

    @abstractmethod
    def extract(self, image_bytes: bytes) -> OCRResult:
        raise NotImplementedError
