import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.bill import Bill
    from app.models.person import Person


class Group(Base):
    """A set of people who split bills together, owned by the User who created it.

    Note: this table is created here (Backend Block 2) because Person.group_id
    needs it to exist, but the *behavior* around groups (creator-only add/remove
    of members, group CRUD API) is Backend Block 5's scope per buildguide.md -
    that block adds the API routes and business rules on top of this table.
    """

    __tablename__ = "groups"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    creator_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    people: Mapped[list["Person"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    bills: Mapped[list["Bill"]] = relationship(back_populates="group", cascade="all, delete-orphan")
