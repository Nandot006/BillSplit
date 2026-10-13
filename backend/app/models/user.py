import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class User(Base):
    """Mirrors a Supabase Auth user. id is NOT generated here - it is always
    the Supabase Auth user id (the JWT's `sub` claim), so this table can be
    foreign-keyed from Group.creator_user_id and Person.supabase_user_id.
    Rows are created lazily (see app/core/security.py) the first time a given
    Supabase user hits an authenticated endpoint - there is no separate
    signup endpoint on this backend, since Web/Mobile talk to Supabase Auth
    directly for signup/login.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
