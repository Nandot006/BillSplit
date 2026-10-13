import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.group import Group
from app.models.person import Person
from app.models.person_taxonomy_score import PersonTaxonomyScore
from app.models.taxonomy import TaxonomySource, TaxonomyValue
from app.models.user import User


def test_unique_constraint_on_person_and_taxonomy_value(db_session_factory):
    db = db_session_factory()
    user = User(id=uuid.uuid4(), email="a@example.com")
    db.add(user)
    db.flush()
    group = Group(id=uuid.uuid4(), name="G", creator_user_id=user.id)
    db.add(group)
    db.flush()
    person = Person(id=uuid.uuid4(), group_id=group.id, display_name="Alex")
    db.add(person)
    db.flush()

    db.add(
        PersonTaxonomyScore(
            person_id=person.id,
            taxonomy_value=TaxonomyValue.VEGETARIAN,
            score=1.0,
            is_hard_restriction=True,
            source=TaxonomySource.QUESTIONNAIRE,
        )
    )
    db.commit()

    db.add(
        PersonTaxonomyScore(
            person_id=person.id,
            taxonomy_value=TaxonomyValue.VEGETARIAN,
            score=0.5,
            is_hard_restriction=True,
            source=TaxonomySource.QUESTIONNAIRE,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.close()
