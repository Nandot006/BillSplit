import uuid

from sqlalchemy.orm import Session

from app.models.bill import Bill
from app.models.bill_item import BillItem
from app.models.bill_item_assignment import BillItemAssignment
from app.models.person import Person
from app.models.person_taxonomy_score import PersonTaxonomyScore
from app.models.prediction_feedback import PredictionFeedback
from app.models.taxonomy import TaxonomySource, TaxonomyValue
from app.services.prediction.scoring import _SCORED_DIMENSIONS, predict_assignment
from app.services.prediction.vectors import ItemVector, PersonVector, build_person_vector

# design.md SS8's formula only fixes the *shape* of the learning-rate decay
# (base_rate / (1 + corrections_so_far)) - it doesn't pin a specific
# base_rate. 0.3 is our own choice: large enough that a person's very first
# correction on a dimension moves their vector by a third of the way to a
# fully-confident +/-1.0 score (fast cold-start improvement, matching
# design.md SS8's stated intent), small enough that a single odd correction
# can't instantly flip a well-established preference.
BASE_LEARNING_RATE = 0.3

# PersonTaxonomyScore.score is documented (see that model) as "roughly
# [-1, 1]" - clamp learned updates to that same range so corrections can't
# drift a score out of the band the questionnaire seeds scores into.
_SCORE_MIN, _SCORE_MAX = -1.0, 1.0


def build_item_vector(item: BillItem) -> ItemVector:
    """Builds the tag set the scorer/hard-restriction-check need from a real
    BillItem row: its base_type plus every flavor and dietary tag attached
    via the join tables (app/models/bill_item_tags.py). Deliberately
    includes dietary tags even though scoring itself only reads
    base-type/flavor dimensions (see _SCORED_DIMENSIONS) - the hard-
    restriction check in scoring.py needs to know an item's dietary tags
    too, so the vector has to carry all three categories.
    """
    tags: set[TaxonomyValue] = set()
    if item.base_type is not None:
        tags.add(TaxonomyValue(item.base_type.value))
    for flavor_tag in item.flavor_tags:
        tags.add(TaxonomyValue(flavor_tag.flavor_tag.value))
    for dietary_flag in item.dietary_flags:
        tags.add(TaxonomyValue(dietary_flag.dietary_flag.value))
    return ItemVector(tags=tags)


def _build_person_vectors(
    db: Session, group_id: uuid.UUID, exclude_person_id: uuid.UUID | None = None
) -> dict[uuid.UUID, PersonVector]:
    """Builds every current group member's PersonVector, keyed by Person id.
    exclude_person_id (Backend Block 10) leaves one Person out entirely -
    used when re-scoring an item after that specific person has been
    removed, so they can never end up re-selected as their own item's
    replacement assignee."""
    query = db.query(Person).filter(Person.group_id == group_id)
    if exclude_person_id is not None:
        query = query.filter(Person.id != exclude_person_id)
    people = query.all()
    return {person.id: build_person_vector(person.taxonomy_scores) for person in people}


def generate_predictions_for_bill(db: Session, bill: Bill) -> None:
    """Runs the Block 6 scorer over every item on a bill that doesn't
    already have an assignment, and records the result as a
    BillItemAssignment (design.md SS6/SS8). Safe to call more than once -
    only unassigned items are scored, so it never overwrites an assignment
    a human has already made or confirmed.

    When the scorer can't produce a winner at all (design.md SS6's hard-
    restriction edge case: every candidate excluded, or there are no People
    in the group yet), the item is simply left with no assignment - there's
    nothing to predict, and a human has to assign it manually before the
    bill can be confirmed (see the /confirm endpoint in routes/bill.py).
    """
    person_vectors = _build_person_vectors(db, bill.group_id)

    for item in bill.items:
        if item.assignments:
            continue

        item_vector = build_item_vector(item)
        result = predict_assignment(person_vectors, item_vector)
        if result.winner_person_id is None:
            continue

        db.add(
            BillItemAssignment(
                bill_item_id=item.id,
                person_id=result.winner_person_id,
                is_predicted=True,
                confidence_score=result.confidence,
                share_fraction=1.0,
            )
        )

    db.flush()


def redistribute_bill_after_person_removal(
    db: Session, bill: Bill, removed_person_id: uuid.UUID
) -> bool:
    """Backend Block 10 (buildguide.md / design.md SS9): call this on every
    one of a group's not-yet-closed bills *before* actually deleting a
    Person. For every item that person was assigned to:

    - if the item was shared with other people too (design.md SS7), the
      removed person's slice just drops out and the remaining assignees'
      shares are re-normalized to 1 / (their new count) - no re-scoring
      needed, the item was already correctly attributed to them too;
    - if the removed person was the item's *sole* assignee, the item goes
      back into the prediction pool and is re-scored against only the
      *remaining* people's vectors (design.md SS9: "the vegetarian dish"
      should go to whichever remaining person is the next-best match, not
      be split evenly by default or left with the departing person).

    design.md SS9/SS10's tax/tip "even split across remaining people" isn't
    persisted anywhere on Bill or BillItemAssignment - there's no Split row
    to update until Block 12 - so it isn't touched here. It's computed live
    against the group's *current* people by app/services/splits.py, so
    removing a Person is automatically reflected there with no separate
    recalculation step.

    Returns True if any item was left with no assignee at all afterward (a
    hard restriction excluded every remaining candidate, or no people are
    left) - the caller should treat that bill the same as any other with an
    unassigned item: push it back to needs_review for a human to finish by
    hand via the existing PUT .../assign endpoint.
    """
    affected_items = [
        item
        for item in bill.items
        if any(a.person_id == removed_person_id for a in item.assignments)
    ]
    if not affected_items:
        return False

    remaining_person_vectors: dict[uuid.UUID, PersonVector] | None = None
    needs_review = False

    for item in affected_items:
        removed_assignment = next(a for a in item.assignments if a.person_id == removed_person_id)
        db.delete(removed_assignment)
        db.flush()
        db.refresh(item)

        remaining_assignments = [a for a in item.assignments if a.person_id != removed_person_id]

        if remaining_assignments:
            new_fraction = 1.0 / len(remaining_assignments)
            for assignment in remaining_assignments:
                assignment.share_fraction = new_fraction
            continue

        if remaining_person_vectors is None:
            remaining_person_vectors = _build_person_vectors(
                db, bill.group_id, exclude_person_id=removed_person_id
            )
        item_vector = build_item_vector(item)
        result = predict_assignment(remaining_person_vectors, item_vector)
        if result.winner_person_id is None:
            needs_review = True
            continue

        db.add(
            BillItemAssignment(
                bill_item_id=item.id,
                person_id=result.winner_person_id,
                is_predicted=True,
                confidence_score=result.confidence,
                share_fraction=1.0,
            )
        )

    db.flush()
    return needs_review


def _get_or_create_score(
    db: Session, person_id: uuid.UUID, taxonomy_value: TaxonomyValue
) -> PersonTaxonomyScore:
    row = (
        db.query(PersonTaxonomyScore)
        .filter(
            PersonTaxonomyScore.person_id == person_id,
            PersonTaxonomyScore.taxonomy_value == taxonomy_value,
        )
        .first()
    )
    if row is None:
        row = PersonTaxonomyScore(
            person_id=person_id,
            taxonomy_value=taxonomy_value,
            score=0.0,
            is_hard_restriction=False,
            source=TaxonomySource.LEARNED_CORRECTION,
        )
        db.add(row)
        db.flush()
    return row


def _nudge_score(row: PersonTaxonomyScore, signal: float) -> None:
    """design.md SS8's shrinking-learning-rate update: early corrections on
    a dimension move it a lot, later ones nudge it gently."""
    rate = BASE_LEARNING_RATE / (1 + row.correction_count)
    row.score = max(_SCORE_MIN, min(_SCORE_MAX, row.score + rate * signal))
    row.correction_count += 1
    row.source = TaxonomySource.LEARNED_CORRECTION


def apply_learned_correction(
    db: Session,
    item: BillItem,
    original_person_id: uuid.UUID | None,
    corrected_person_id: uuid.UUID,
) -> None:
    """Nudges the affected People's taxonomy vectors from one correction
    (design.md SS8). Only the base-type/flavor-tag dimensions this item
    actually carries are touched - the same _SCORED_DIMENSIONS the scorer
    itself reads (design.md SS6: dietary flags are a hard exclude, not a
    weighted/learned dimension).

    corrected_person gets a +1 signal on each of those dimensions (this
    item genuinely belongs to them). original_person (when there was one,
    and it's a different Person) gets a -1 signal on the same dimensions
    (they were wrongly predicted for an item like this).
    """
    item_vector = build_item_vector(item)
    scored_values = [value for value in _SCORED_DIMENSIONS if item_vector.has(value)]
    if not scored_values:
        return  # nothing to learn from - the item carries no tagged dimensions

    for taxonomy_value in scored_values:
        _nudge_score(_get_or_create_score(db, corrected_person_id, taxonomy_value), signal=1.0)

    if original_person_id is not None and original_person_id != corrected_person_id:
        for taxonomy_value in scored_values:
            _nudge_score(_get_or_create_score(db, original_person_id, taxonomy_value), signal=-1.0)

    db.flush()


def record_correction(
    db: Session, item: BillItem, corrected_person_id: uuid.UUID
) -> list[BillItemAssignment]:
    """The single-assignee confirm/correct action (PRD SS5 step 4): sets
    item's sole assignee to corrected_person_id. If that's a genuine change
    from what's currently assigned (a fresh assignment, or a different
    person than before), records a PredictionFeedback row and feeds the
    correction into apply_learned_correction. Re-confirming the person
    already assigned is a no-op - it isn't a correction, so it shouldn't
    generate learning-signal noise every time a bill is reopened and
    re-viewed.

    Deliberately replaces the item's whole assignment set with a single
    row - this is the primary-assignee correction flow. Multi-person shared
    items (design.md SS7) are a separate additive feature for the
    itemized-breakdown editing UI to build against later; nothing here
    prevents adding that endpoint alongside this one.
    """
    existing = list(item.assignments)
    current_sole_person_id = existing[0].person_id if len(existing) == 1 else None
    if current_sole_person_id == corrected_person_id:
        return existing

    original_predicted_person_id = next(
        (row.person_id for row in existing if row.is_predicted), None
    )

    for row in existing:
        db.delete(row)
    db.flush()

    db.add(
        PredictionFeedback(
            bill_item_id=item.id,
            original_predicted_person_id=original_predicted_person_id,
            corrected_person_id=corrected_person_id,
        )
    )

    new_assignment = BillItemAssignment(
        bill_item_id=item.id,
        person_id=corrected_person_id,
        is_predicted=False,
        confidence_score=None,
        share_fraction=1.0,
    )
    db.add(new_assignment)

    apply_learned_correction(db, item, original_predicted_person_id, corrected_person_id)

    db.flush()
    db.refresh(item)
    return item.assignments
