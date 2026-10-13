import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.core.config import settings
from app.models.taxonomy import BaseType, DietaryFlag, FlavorTag


class TaxonomyClassificationError(Exception):
    """Raised when the model call fails or returns something we can't parse
    into the fixed taxonomy. The caller (app/services/ocr/pipeline.py)
    treats this as "leave the item untagged" rather than failing the whole
    bill - a human reviewing needs_review can tag it by hand."""


@dataclass
class TaxonomyClassification:
    base_type: BaseType | None = None
    flavor_tags: list[FlavorTag] = field(default_factory=list)
    dietary_flags: list[DietaryFlag] = field(default_factory=list)


class TaxonomyClassifier(ABC):
    """CLAUDE.md SS6: the LLM's only job in this pipeline is mapping raw OCR
    text onto taxonomy categories - it never does attribution reasoning
    itself (that's the deterministic scorer in Block 6)."""

    @abstractmethod
    def classify(self, item_name: str) -> TaxonomyClassification:
        raise NotImplementedError


def build_classification_prompt(item_name: str) -> str:
    """Built from the live enums (not a hardcoded copy of the value lists)
    so the prompt can never drift out of sync with app/models/taxonomy.py."""
    base_types = ", ".join(v.value for v in BaseType)
    flavor_tags = ", ".join(v.value for v in FlavorTag)
    dietary_flags = ", ".join(v.value for v in DietaryFlag)
    return (
        "You are classifying a single food/drink item from a restaurant receipt "
        "into a fixed taxonomy. Respond with ONLY a JSON object - no markdown, "
        "no explanation, no other text.\n\n"
        f'Item: "{item_name}"\n\n'
        f"Pick exactly one base_type from: {base_types}.\n"
        f"Pick zero or more flavor_tags from: {flavor_tags}.\n"
        f"Pick zero or more dietary_flags from: {dietary_flags} - only ones you are "
        "reasonably confident the dish actually has. If the item name alone doesn't "
        "make a flag clear (e.g. you can't tell if a generic 'pasta' is vegan), leave "
        "it out rather than guessing.\n\n"
        'Respond exactly as: {"base_type": "...", "flavor_tags": [...], "dietary_flags": [...]}'
    )


def parse_classification_response(raw: str) -> TaxonomyClassification:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TaxonomyClassificationError(f"Model did not return valid JSON: {raw!r}") from exc

    try:
        base_type_value = data.get("base_type")
        base_type = BaseType(base_type_value) if base_type_value else None
        flavor_tags = [FlavorTag(v) for v in data.get("flavor_tags", [])]
        dietary_flags = [DietaryFlag(v) for v in data.get("dietary_flags", [])]
    except ValueError as exc:
        # A value outside our fixed taxonomy - the model hallucinated a
        # category that doesn't exist.
        raise TaxonomyClassificationError(
            f"Model returned an unknown taxonomy value: {exc}"
        ) from exc

    return TaxonomyClassification(
        base_type=base_type, flavor_tags=flavor_tags, dietary_flags=dietary_flags
    )


class GeminiTaxonomyClassifier(TaxonomyClassifier):
    """design.md SS1: Gemini API, small/cheap tier (e.g. Flash-Lite) - this
    is a small classification task, not a reasoning task, so there's no
    need for a large model. The google-generativeai package is imported
    lazily so this module stays importable without it installed."""

    def __init__(self, api_key: str | None = None, model: str = "gemini-2.0-flash-lite"):
        self._api_key = api_key or settings.GEMINI_API_KEY
        self._model_name = model

    def classify(self, item_name: str) -> TaxonomyClassification:
        raw = self._call_model(item_name)
        return parse_classification_response(raw)

    def _call_model(self, item_name: str) -> str:
        if not self._api_key:
            raise TaxonomyClassificationError("GEMINI_API_KEY is not configured.")

        import google.generativeai as genai

        genai.configure(api_key=self._api_key)
        model = genai.GenerativeModel(self._model_name)
        try:
            response = model.generate_content(build_classification_prompt(item_name))
        except Exception as exc:  # pragma: no cover - network/SDK failures
            raise TaxonomyClassificationError(str(exc)) from exc
        return response.text
