import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.taxonomy import TaxonomySource, TaxonomyValue


class PersonTaxonomyScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    person_id: uuid.UUID
    taxonomy_value: TaxonomyValue
    score: float
    is_hard_restriction: bool
    source: TaxonomySource
    correction_count: int
    updated_at: datetime
