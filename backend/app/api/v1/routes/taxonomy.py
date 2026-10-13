from fastapi import APIRouter

from app.models.taxonomy import BaseType, DietaryFlag, FlavorTag
from app.schemas.taxonomy import TaxonomyCatalogOut

router = APIRouter()


@router.get("/taxonomy", response_model=TaxonomyCatalogOut)
def get_taxonomy_catalog():
    """The fixed v1 taxonomy (design.md SS3) - public reference data, no auth
    needed. Clients read this instead of hardcoding the 20 values, so the
    questionnaire UI and any future taxonomy-tagging UI stay in sync with
    the backend automatically."""
    return TaxonomyCatalogOut(
        base_types=list(BaseType),
        flavor_tags=list(FlavorTag),
        dietary_flags=list(DietaryFlag),
    )
