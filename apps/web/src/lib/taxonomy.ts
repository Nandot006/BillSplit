// Display names for the taxonomy (design.md §3) and a readable summary of a
// person's taste scores for the profile screen.

import type {
  BaseType,
  DietaryFlag,
  FlavorTag,
  PersonTaxonomyScore,
  TaxonomyValue,
} from "@billsplit/shared-types";

export const BASE_TYPE_LABELS: Record<BaseType, string> = {
  appetizer: "Starter",
  entree: "Main",
  side: "Side",
  dessert: "Dessert",
  "drink-non-alcoholic": "Soft drink",
  "drink-alcoholic": "Alcoholic drink",
  "shared-platter": "Sharing plate",
};

export const FLAVOR_LABELS: Record<FlavorTag, string> = {
  spicy: "Spicy",
  sweet: "Sweet",
  savory: "Savory",
  sour: "Sour",
  mild: "Mild",
};

export const DIETARY_LABELS: Record<DietaryFlag, string> = {
  vegetarian: "Vegetarian",
  vegan: "Vegan",
  "gluten-free": "Gluten-free",
  "dairy-free": "Dairy-free",
  "nut-free": "Nut-free",
  "no-pork": "No pork",
  "no-beef": "No beef",
  "no-alcohol": "No alcohol",
};

export function taxonomyLabel(value: TaxonomyValue): string {
  return (
    (BASE_TYPE_LABELS as Record<string, string>)[value] ??
    (FLAVOR_LABELS as Record<string, string>)[value] ??
    (DIETARY_LABELS as Record<string, string>)[value] ??
    value
  );
}

export interface TasteSummary {
  hasQuestionnaire: boolean;
  learnedFromCorrections: number;
  restrictions: string[];
  likes: string[];
  dislikes: string[];
}

/** Scores at or beyond ±0.25 count as a like/dislike worth showing. */
const SIGNAL = 0.25;

export function summarizeTaste(scores: PersonTaxonomyScore[]): TasteSummary {
  const restrictions = scores
    .filter((s) => s.is_hard_restriction)
    .map((s) => taxonomyLabel(s.taxonomy_value));
  const ranked = scores
    .filter((s) => !s.is_hard_restriction)
    .sort((a, b) => Math.abs(b.score) - Math.abs(a.score));
  return {
    hasQuestionnaire: scores.some((s) => s.source === "questionnaire"),
    learnedFromCorrections: scores.reduce((n, s) => n + s.correction_count, 0),
    restrictions,
    likes: ranked.filter((s) => s.score >= SIGNAL).map((s) => taxonomyLabel(s.taxonomy_value)),
    dislikes: ranked.filter((s) => s.score <= -SIGNAL).map((s) => taxonomyLabel(s.taxonomy_value)),
  };
}
