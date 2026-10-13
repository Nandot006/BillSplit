from pydantic import BaseModel

from app.models.taxonomy import BaseType, DietaryFlag, FlavorTag


class TaxonomyCatalogOut(BaseModel):
    base_types: list[BaseType]
    flavor_tags: list[FlavorTag]
    dietary_flags: list[DietaryFlag]
