from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.models.taxonomy import BaseType, DietaryFlag, FlavorTag


class TaxonomyClassificationError(Exception):
    """Raised when the model call fails or returns something we can't map
    onto the fixed taxonomy. The caller (app/services/ocr/pipeline.py)
    treats this as "leave the item(s) untagged" rather than failing the
    whole bill - a human reviewing needs_review can tag them by hand."""


@dataclass
class TaxonomyClassification:
    base_type: BaseType | None = None
    flavor_tags: list[FlavorTag] = field(default_factory=list)
    dietary_flags: list[DietaryFlag] = field(default_factory=list)


class TaxonomyClassifier(ABC):
    """CLAUDE.md SS6: the LLM's only job in this pipeline is mapping raw OCR
    text onto taxonomy categories - it never does attribution reasoning
    itself (that's the deterministic scorer in Backend Block 6)."""

    @abstractmethod
    def classify(self, item_name: str) -> TaxonomyClassification:
        raise NotImplementedError

    def classify_many(self, item_names: list[str]) -> list[TaxonomyClassification | None]:
        """Classifies a whole receipt's items, returning one result per
        input in the same order (None = couldn't classify that one item).

        This default calls classify() once per item, so a classifier only
        has to implement classify(). Implementations backed by a paid API
        should override it to classify every item in a single request -
        one call per receipt instead of one per line item.
        """
        results: list[TaxonomyClassification | None] = []
        for name in item_names:
            try:
                results.append(self.classify(name))
            except TaxonomyClassificationError:
                results.append(None)
        return results
