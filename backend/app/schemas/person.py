import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PersonBase(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    free_text_preferences: str | None = None


class PersonUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    free_text_preferences: str | None = None


class PersonOut(PersonBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    group_id: uuid.UUID
    supabase_user_id: uuid.UUID | None = None
    created_at: datetime
