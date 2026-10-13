from collections.abc import Iterable
from dataclasses import dataclass, field

from app.models.person_taxonomy_score import PersonTaxonomyScore
from app.models.taxonomy import DIETARY_FLAG_TAXONOMY_VALUES, TaxonomyValue


@dataclass
class PersonVector:
    """A Person's 20-dim taxonomy preference vector (design.md SS6)."""

    scores: dict[TaxonomyValue, float] = field(default_factory=dict)
    hard_restrictions: set[TaxonomyValue] = field(default_factory=set)

    def score_for(self, value: TaxonomyValue) -> float:
        return self.scores.get(value, 0.0)


@dataclass
class ItemVector:
    """A BillItem's tag set: 1.0 for every taxonomy value it's tagged with,
    0 otherwise (design.md SS6). Deliberately has no dependency on the
    BillItem ORM model (which doesn't exist until Backend Block 7) - Block 7
    / B lock 9 just need to build one of these from a real BillItem's
    base_type + flavor/dietary tags before calling the scorer.
    """

    tags: set[TaxonomyValue] = field(default_factory=set)

    def has(self, value: TaxonomyValue) -> bool:
        return value in self.tags


def build_person_vector(taxonomy_scores: Iterable[PersonTaxonomyScore]) -> PersonVector:
    """Converts a Person's PersonTaxonomyScore rows into the vector shape the
    scorer works with. Only dietary-flag dimensions are ever treated as hard
    restrictions here, even if is_hard_restriction were somehow set on a
    non-dietary row - dietary flags are the only category design.md SS6
    defines hard-exclude behavior for."""
    vector = PersonVector()
    for row in taxonomy_scores:
        vector.scores[row.taxonomy_value] = row.score
        if row.is_hard_restriction and row.taxonomy_value in DIETARY_FLAG_TAXONOMY_VALUES:
            vector.hard_restrictions.add(row.taxonomy_value)
    return vector
