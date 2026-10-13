import enum


class BaseType(str, enum.Enum):
    """A BillItem's single, mutually-exclusive base type (design.md SS3)."""

    APPETIZER = "appetizer"
    ENTREE = "entree"
    SIDE = "side"
    DESSERT = "dessert"
    DRINK_NON_ALCOHOLIC = "drink-non-alcoholic"
    DRINK_ALCOHOLIC = "drink-alcoholic"
    SHARED_PLATTER = "shared-platter"


class FlavorTag(str, enum.Enum):
    """A BillItem can carry several of these (design.md SS3)."""

    SPICY = "spicy"
    SWEET = "sweet"
    SAVORY = "savory"
    SOUR = "sour"
    MILD = "mild"


class DietaryFlag(str, enum.Enum):
    """On a BillItem this is descriptive (the dish IS vegetarian). On a
    Person (via PersonTaxonomyScore.is_hard_restriction) it's a hard
    requirement, not just a preference - see design.md SS6."""

    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"
    GLUTEN_FREE = "gluten-free"
    DAIRY_FREE = "dairy-free"
    NUT_FREE = "nut-free"
    NO_PORK = "no-pork"
    NO_BEEF = "no-beef"
    NO_ALCOHOL = "no-alcohol"


class TaxonomySource(str, enum.Enum):
    QUESTIONNAIRE = "questionnaire"
    LEARNED_CORRECTION = "learned_correction"


class TaxonomyValue(str, enum.Enum):
    """All 20 taxonomy values (design.md SS3), spanning base types, flavor
    tags, and dietary flags - the dimensionality of every Person and
    BillItem vector (design.md SS6). This is a flat enum rather than a union
    of the three category enums above because PersonTaxonomyScore.taxonomy_value
    needs one column type that can hold any of the 20. tests/test_taxonomy.py
    asserts this stays exactly in sync with BaseType + FlavorTag + DietaryFlag,
    so the two representations can't silently drift apart.
    """

    APPETIZER = "appetizer"
    ENTREE = "entree"
    SIDE = "side"
    DESSERT = "dessert"
    DRINK_NON_ALCOHOLIC = "drink-non-alcoholic"
    DRINK_ALCOHOLIC = "drink-alcoholic"
    SHARED_PLATTER = "shared-platter"

    SPICY = "spicy"
    SWEET = "sweet"
    SAVORY = "savory"
    SOUR = "sour"
    MILD = "mild"

    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"
    GLUTEN_FREE = "gluten-free"
    DAIRY_FREE = "dairy-free"
    NUT_FREE = "nut-free"
    NO_PORK = "no-pork"
    NO_BEEF = "no-beef"
    NO_ALCOHOL = "no-alcohol"


# Runtime-derived sets so the scoring engine (Backend Block 6) can ask "is
# this taxonomy value a dietary flag?" without a hardcoded second list.
DIETARY_FLAG_TAXONOMY_VALUES = {TaxonomyValue(flag.value) for flag in DietaryFlag}
BASE_TYPE_TAXONOMY_VALUES = {TaxonomyValue(base.value) for base in BaseType}
FLAVOR_TAG_TAXONOMY_VALUES = {TaxonomyValue(flavor.value) for flavor in FlavorTag}
