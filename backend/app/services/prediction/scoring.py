import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from app.models.taxonomy import (
    BASE_TYPE_TAXONOMY_VALUES,
    DIETARY_FLAG_TAXONOMY_VALUES,
    FLAVOR_TAG_TAXONOMY_VALUES,
)
from app.services.prediction.vectors import ItemVector, PersonVector

# design.md SS6: predictions below this confidence, or an exact tie, are
# flagged for manual review instead of auto-assigned.
NEEDS_REVIEW_CONFIDENCE_THRESHOLD = 0.40

# The dot product only runs over these dimensions - dietary-flag dimensions
# already did their filtering work via the hard-exclude check, so including
# them in the score too would double-count them (design.md SS6: "restricted
# to base-type and flavor-tag dimensions").
_SCORED_DIMENSIONS = BASE_TYPE_TAXONOMY_VALUES | FLAVOR_TAG_TAXONOMY_VALUES


@dataclass
class CandidateScore:
    # uuid.UUID (not Person) so this module has zero ORM/DB dependency and
    # stays trivially unit-testable.
    person_id: uuid.UUID
    score: float


@dataclass
class PredictionResult:
    """needs_review is True whenever a human must pick manually - either
    because a hard restriction eliminated every candidate (design.md SS6's
    explicit edge case), or because confidence came out too low / a tie."""

    winner_person_id: uuid.UUID | None
    confidence: float
    needs_review: bool
    all_scores: list[CandidateScore]


def person_survives_hard_restrictions(person_vector: PersonVector, item_vector: ItemVector) -> bool:
    """design.md SS6: if a Person has a dietary flag marked as a hard
    restriction and the item isn't tagged with that flag, the person is
    removed from consideration entirely - not just down-weighted."""
    for restricted_value in person_vector.hard_restrictions:
        if restricted_value not in DIETARY_FLAG_TAXONOMY_VALUES:
            continue  # defensive: is_hard_restriction only means hard-exclude for dietary flags
        if not item_vector.has(restricted_value):
            return False
    return True


def score_person_for_item(person_vector: PersonVector, item_vector: ItemVector) -> float:
    """Plain dot product over base-type and flavor-tag dimensions only."""
    return sum(
        person_vector.score_for(dimension)
        for dimension in _SCORED_DIMENSIONS
        if item_vector.has(dimension)
    )


def predict_assignment(
    person_vectors: Mapping[uuid.UUID, PersonVector], item_vector: ItemVector
) -> PredictionResult:
    """Scores every candidate Person (keyed however the caller likes -
    normally by Person id) against one BillItem and picks a winner, per
    design.md SS6."""

    eligible = {
        person_id: vector
        for person_id, vector in person_vectors.items()
        if person_survives_hard_restrictions(vector, item_vector)
    }

    if not eligible:
        # Edge case explicitly called out in design.md SS6: a hard
        # restriction excluded every candidate. No default assignment -
        # someone has to pick manually.
        return PredictionResult(
            winner_person_id=None, confidence=0.0, needs_review=True, all_scores=[]
        )

    scored = sorted(
        (
            CandidateScore(person_id=pid, score=score_person_for_item(vec, item_vector))
            for pid, vec in eligible.items()
        ),
        key=lambda c: c.score,
        reverse=True,
    )

    confidence = _confidence(scored)
    return PredictionResult(
        winner_person_id=scored[0].person_id,
        confidence=confidence,
        needs_review=confidence < NEEDS_REVIEW_CONFIDENCE_THRESHOLD,
        all_scores=scored,
    )


def _confidence(scored: list[CandidateScore]) -> float:
    """Normalized gap between the top score and the runner-up, as 0.0-1.0
    (design.md SS6: "a landslide win -> high confidence, a near-tie -> low
    confidence"). design.md doesn't specify the exact formula, so this is
    our own reasonable interpretation: gap / (|top| + |runner-up|), which is
    scale-invariant regardless of how many tags an item happens to carry.

    A single eligible candidate is a landslide by definition (1.0). An exact
    tie between the top two is 0.0, forcing needs_review regardless of the
    0.40 threshold.
    """
    if len(scored) == 1:
        return 1.0

    top_score, runner_up_score = scored[0].score, scored[1].score
    if top_score == runner_up_score:
        return 0.0

    spread = abs(top_score) + abs(runner_up_score)
    if spread == 0:
        return 0.0

    gap = top_score - runner_up_score
    return max(0.0, min(1.0, gap / spread))
