// The cold-start questionnaire (design.md §4): 12 core + 5 optional
// questions. The backend stores preference answers as numbers in [-1, 1]
// (backend/app/schemas/questionnaire.py) and leaves the scale shown to people
// up to the client - so each scale question here has five plain-language
// steps that map to -1, -0.5, 0, 0.5, 1.

import type { QuestionnaireSubmission } from "@billsplit/shared-types";

export const SCALE_VALUES = [-1, -0.5, 0, 0.5, 1] as const;

type YesNoField =
  | "avoids_gluten"
  | "avoids_dairy"
  | "has_nut_allergy"
  | "avoids_pork"
  | "avoids_beef"
  | "drinks_alcohol";

type ScaleField =
  | "appetizer_frequency"
  | "entree_vs_shared_preference"
  | "spice_tolerance"
  | "dessert_frequency"
  | "savory_vs_sweet_preference"
  | "non_alcoholic_drink_frequency"
  | "sour_preference"
  | "mild_preference"
  | "side_frequency";

export type Question =
  | {
      kind: "diet";
      field: "vegetarian_or_vegan";
      prompt: string;
      options: { value: QuestionnaireSubmission["vegetarian_or_vegan"]; label: string }[];
    }
  | { kind: "yesno"; field: YesNoField; prompt: string; hint?: string }
  | {
      kind: "scale";
      field: ScaleField;
      prompt: string;
      /** Five labels, from the -1 end to the +1 end. */
      steps: [string, string, string, string, string];
      optional?: boolean;
    }
  | { kind: "text"; field: "additional_preferences"; prompt: string; optional: true };

const FREQUENCY = ["Never", "Rarely", "Sometimes", "Often", "Almost always"] as const;

export const CORE_QUESTIONS: Question[] = [
  {
    kind: "diet",
    field: "vegetarian_or_vegan",
    prompt: "Do you follow a vegetarian or vegan diet?",
    options: [
      { value: "none", label: "Neither" },
      { value: "vegetarian", label: "Vegetarian" },
      { value: "vegan", label: "Vegan" },
    ],
  },
  { kind: "yesno", field: "avoids_gluten", prompt: "Do you avoid gluten?" },
  { kind: "yesno", field: "avoids_dairy", prompt: "Do you avoid dairy?" },
  { kind: "yesno", field: "has_nut_allergy", prompt: "Do you have a nut allergy?" },
  {
    kind: "yesno",
    field: "avoids_pork",
    prompt: "Do you avoid pork?",
    hint: "For any reason - religious, personal, or just taste.",
  },
  {
    kind: "yesno",
    field: "avoids_beef",
    prompt: "Do you avoid beef?",
    hint: "For any reason - religious, personal, or just taste.",
  },
  { kind: "yesno", field: "drinks_alcohol", prompt: "Do you drink alcohol?" },
  {
    kind: "scale",
    field: "appetizer_frequency",
    prompt: "When you eat out, how often do you order a starter?",
    steps: [...FREQUENCY],
  },
  {
    kind: "scale",
    field: "entree_vs_shared_preference",
    prompt: "Do you usually order your own main dish, or share smaller plates?",
    steps: ["Always share", "Mostly share", "Either", "Mostly my own", "Always my own"],
  },
  {
    kind: "scale",
    field: "spice_tolerance",
    prompt: "How do you feel about spicy food?",
    steps: ["Avoid it", "A little is fine", "Neutral", "Like it", "The hotter the better"],
  },
  {
    kind: "scale",
    field: "dessert_frequency",
    prompt: "How often do you order dessert?",
    steps: [...FREQUENCY],
  },
  {
    kind: "scale",
    field: "savory_vs_sweet_preference",
    prompt: "Savory or sweet - which do you usually go for?",
    steps: ["Sweet", "Mostly sweet", "Both equally", "Mostly savory", "Savory"],
  },
];

export const OPTIONAL_QUESTIONS: Question[] = [
  {
    kind: "scale",
    field: "non_alcoholic_drink_frequency",
    prompt: "How often do you order a soft drink, juice or mocktail?",
    steps: [...FREQUENCY],
    optional: true,
  },
  {
    kind: "scale",
    field: "sour_preference",
    prompt: "Do you enjoy sour or tangy flavors?",
    steps: ["Not at all", "Not really", "Neutral", "Yes", "Love them"],
    optional: true,
  },
  {
    kind: "scale",
    field: "mild_preference",
    prompt: "Do you tend to order milder dishes?",
    steps: ["Never", "Rarely", "Sometimes", "Often", "Almost always"],
    optional: true,
  },
  {
    kind: "scale",
    field: "side_frequency",
    prompt: "How often do you order a side (rice, fries, bread) with your main?",
    steps: [...FREQUENCY],
    optional: true,
  },
  {
    kind: "text",
    field: "additional_preferences",
    prompt: "Anything else about food preferences or restrictions?",
    optional: true,
  },
];

/** Answers as the form holds them; undefined = not answered yet. */
export type Answers = {
  vegetarian_or_vegan?: QuestionnaireSubmission["vegetarian_or_vegan"];
} & Partial<Record<YesNoField, boolean>> &
  Partial<Record<ScaleField, number>> & { additional_preferences?: string };

export function unansweredCoreQuestions(answers: Answers): Question[] {
  return CORE_QUESTIONS.filter((q) => answers[q.field] === undefined);
}

/** Builds the API body. Throws if a core question is unanswered. */
export function toSubmission(answers: Answers): QuestionnaireSubmission {
  const missing = unansweredCoreQuestions(answers);
  if (missing.length > 0) {
    throw new Error(`Answer every required question first (${missing.length} left).`);
  }
  const text = answers.additional_preferences?.trim();
  return {
    vegetarian_or_vegan: answers.vegetarian_or_vegan!,
    avoids_gluten: answers.avoids_gluten!,
    avoids_dairy: answers.avoids_dairy!,
    has_nut_allergy: answers.has_nut_allergy!,
    avoids_pork: answers.avoids_pork!,
    avoids_beef: answers.avoids_beef!,
    drinks_alcohol: answers.drinks_alcohol!,
    appetizer_frequency: answers.appetizer_frequency!,
    entree_vs_shared_preference: answers.entree_vs_shared_preference!,
    spice_tolerance: answers.spice_tolerance!,
    dessert_frequency: answers.dessert_frequency!,
    savory_vs_sweet_preference: answers.savory_vs_sweet_preference!,
    non_alcoholic_drink_frequency: answers.non_alcoholic_drink_frequency ?? null,
    sour_preference: answers.sour_preference ?? null,
    mild_preference: answers.mild_preference ?? null,
    side_frequency: answers.side_frequency ?? null,
    additional_preferences: text ? text : null,
  };
}

/** "Do you avoid gluten?" -> "Does Priya avoid gluten?" for someone else. */
export function rephrase(prompt: string, name: string): string {
  return prompt
    .replace(/^Do you /, `Does ${name} `)
    .replace(/^When you eat out, how often do you /, `When ${name} eats out, how often do they `)
    .replace(/^How often do you /, `How often does ${name} `)
    .replace(/^How do you /, `How does ${name} `)
    .replace(/^Anything else about food/, `Anything else about ${name}'s food`)
    .replace(/which do you /, `which does ${name} `)
    .replace(/ your /g, " their ")
    .replace(/ you /g, " they ")
    .replace(/\byou usually\b/, "they usually");
}
