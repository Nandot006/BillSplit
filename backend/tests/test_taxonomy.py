from app.models.taxonomy import BaseType, DietaryFlag, FlavorTag, TaxonomyValue


def test_taxonomy_value_matches_the_three_category_enums_exactly():
    """Guards against TaxonomyValue drifting away from BaseType/FlavorTag/
    DietaryFlag - design.md SS3 says this should always be exactly 20 values
    (7 + 5 + 8)."""
    combined = {member.value for member in (*BaseType, *FlavorTag, *DietaryFlag)}
    assert combined == {member.value for member in TaxonomyValue}
    assert len(combined) == 20


def test_taxonomy_catalog_endpoint(client):
    resp = client.get("/api/v1/taxonomy")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["base_types"]) == 7
    assert len(body["flavor_tags"]) == 5
    assert len(body["dietary_flags"]) == 8
