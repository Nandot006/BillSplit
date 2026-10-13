import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.person import PersonOut


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class GroupUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    creator_user_id: uuid.UUID
    created_at: datetime


class GroupDetailOut(GroupOut):
    people: list[PersonOut] = []


class AddPersonToGroup(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    free_text_preferences: str | None = None
