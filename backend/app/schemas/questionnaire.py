from typing import Literal

from pydantic import BaseModel, Field


class QuestionnaireSubmission(BaseModel):
    """One submission of the cold-start questionnaire (design.md SS4) for a
    single Person. The 12 core fields are required; the 5 optional ones
    default to None and are simply skipped if not answered.

    Preference fields are floats in [-1, 1]. The client UI turns whatever
    scale it shows the user (a 4-point Likert row, a slider, two buttons)
    into this range - the backend only stores it. That keeps the exact
    wording/UX of the questionnaire a Web/Mobile Block 4 concern, matching
    design.md SS4's own framing of the question list as "user-facing copy,
    not an architectural decision."

    Field -> taxonomy value mapping (see app/services/questionnaire.py for
    the code that applies this):
      Q1  vegetarian_or_vegan            -> VEGETARIAN / VEGAN (hard restriction)
      Q2  avoids_gluten                  -> GLUTEN_FREE (hard restriction)
      Q3  avoids_dairy                   -> DAIRY_FREE (hard restriction)
      Q4  has_nut_allergy                -> NUT_FREE (hard restriction)
      Q5  avoids_pork                    -> NO_PORK (hard restriction)
      Q6  avoids_beef                    -> NO_BEEF (hard restriction)
      Q7  drinks_alcohol      -> NO_ALCOHOL (hard, if False) / DRINK_ALCOHOLIC (affinity, if True)
      Q8  appetizer_frequency            -> APPETIZER
      Q9  entree_vs_shared_preference    -> ENTREE (+) / SHARED_PLATTER (-)
      Q10 spice_tolerance                -> SPICY
      Q11 dessert_frequency              -> DESSERT, SWEET
      Q12 savory_vs_sweet_preference     -> SAVORY (+) / SWEET (-)
      Q13 non_alcoholic_drink_frequency  -> DRINK_NON_ALCOHOLIC (optional)
      Q14 sour_preference                -> SOUR (optional)
      Q15 mild_preference                -> MILD (optional)
      Q16 side_frequency                 -> SIDE (optional)
      Q17 additional_preferences         -> Person.free_text_preferences, not a taxonomy score
    """

    vegetarian_or_vegan: Literal["none", "vegetarian", "vegan"]
    avoids_gluten: bool
    avoids_dairy: bool
    has_nut_allergy: bool
    avoids_pork: bool
    avoids_beef: bool
    drinks_alcohol: bool

    appetizer_frequency: float = Field(ge=-1.0, le=1.0)
    entree_vs_shared_preference: float = Field(ge=-1.0, le=1.0)
    spice_tolerance: float = Field(ge=-1.0, le=1.0)
    dessert_frequency: float = Field(ge=-1.0, le=1.0)
    savory_vs_sweet_preference: float = Field(ge=-1.0, le=1.0)

    non_alcoholic_drink_frequency: float | None = Field(default=None, ge=-1.0, le=1.0)
    sour_preference: float | None = Field(default=None, ge=-1.0, le=1.0)
    mild_preference: float | None = Field(default=None, ge=-1.0, le=1.0)
    side_frequency: float | None = Field(default=None, ge=-1.0, le=1.0)
    additional_preferences: str | None = None
