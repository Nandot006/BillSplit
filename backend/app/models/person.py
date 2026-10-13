import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.group import Group
    from app.models.person_taxonomy_score import PersonTaxonomyScore


class Person(Base):
    """A member of exactly one Group (design.md SS2): the same real human in two
    different groups is two separate Person rows, each with its own
    independently-learned taxonomy vector, because order habits can genuinely
    differ by social context (e.g. a coworker-lunch group vs. a family group).
    """

    __tablename__ = "people"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    # NULL = shadow contact (someone in the group who hasn't signed up).
    # Set = claimed account (a real registered User). A single User can be
    # linked to multiple Person rows, one per group they're a claimed member of.
    supabase_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    free_text_preferences: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    group: Mapped["Group"] = relationship(back_populates="people")
    taxonomy_scores: Mapped[list["PersonTaxonomyScore"]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )
