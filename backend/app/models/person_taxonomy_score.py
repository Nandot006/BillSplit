import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.taxonomy import TaxonomySource, TaxonomyValue

if TYPE_CHECKING:
    from app.models.person import Person


class PersonTaxonomyScore(Base):
    """One row per (person, taxonomy_value) - the 20-dimensional preference
    vector described in design.md SS6. Seeded with source=questionnaire
    (Backend Block 4) and nudged over time by source=learned_correction
    (Backend Block 9's shrinking-learning-rate update, design.md SS8).
    """

    __tablename__ = "person_taxonomy_scores"
    __table_args__ = (UniqueConstraint("person_id", "taxonomy_value"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), nullable=False
    )
    taxonomy_value: Mapped[TaxonomyValue] = mapped_column(
        SAEnum(TaxonomyValue, name="taxonomy_value", native_enum=True), nullable=False
    )
    # Affinity weight, roughly [-1, 1]. Dietary flags don't really use this
    # dimension as a weight - they're a hard exclude instead (see
    # is_hard_restriction and design.md SS6) - but the column still holds a
    # placeholder score for schema uniformity.
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_hard_restriction: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[TaxonomySource] = mapped_column(
        SAEnum(TaxonomySource, name="taxonomy_source", native_enum=True), nullable=False
    )
    # Denominator for the shrinking learning rate (design.md SS8) - how many
    # learned_correction updates have landed on this specific dimension.
    correction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    person: Mapped["Person"] = relationship(back_populates="taxonomy_scores")
