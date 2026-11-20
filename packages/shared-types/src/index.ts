// Shared TypeScript types between apps/web and apps/mobile (CLAUDE.md §11:
// "do not redefine the same shape twice"). Each type mirrors a Pydantic
// schema in backend/app/schemas/ - the file named in each comment. Money
// fields are strings: the API serializes Python Decimals as "12.50" so no
// precision is lost on the way to the client.

export const SHARED_TYPES_PACKAGE_VERSION = "0.2.0";

export type UUID = string;
/** A decimal amount as sent by the API, e.g. "12.50". */
export type Money = string;
/** ISO 8601 timestamp. */
export type Timestamp = string;
/** ISO date, YYYY-MM-DD. */
export type DateString = string;

// --- taxonomy (backend/app/models/taxonomy.py, design.md §3) ---------------

export const BASE_TYPES = [
  "appetizer",
  "entree",
  "side",
  "dessert",
  "drink-non-alcoholic",
  "drink-alcoholic",
  "shared-platter",
] as const;
export type BaseType = (typeof BASE_TYPES)[number];

export const FLAVOR_TAGS = ["spicy", "sweet", "savory", "sour", "mild"] as const;
export type FlavorTag = (typeof FLAVOR_TAGS)[number];

export const DIETARY_FLAGS = [
  "vegetarian",
  "vegan",
  "gluten-free",
  "dairy-free",
  "nut-free",
  "no-pork",
  "no-beef",
  "no-alcohol",
] as const;
export type DietaryFlag = (typeof DIETARY_FLAGS)[number];

export type TaxonomyValue = BaseType | FlavorTag | DietaryFlag;
export type TaxonomySource = "questionnaire" | "learned_correction";

// --- users, groups, people (schemas/user.py, group.py, person.py) ----------

export interface User {
  id: UUID;
  email: string | null;
  display_name: string | null;
  created_at: Timestamp;
}

export interface Person {
  id: UUID;
  group_id: UUID;
  /** null = shadow contact (no account); set = claimed by that user. */
  supabase_user_id: UUID | null;
  display_name: string;
  free_text_preferences: string | null;
  created_at: Timestamp;
}

export interface PersonUpdate {
  display_name?: string;
  free_text_preferences?: string | null;
}

export interface Group {
  id: UUID;
  name: string;
  creator_user_id: UUID;
  created_at: Timestamp;
}

export interface GroupDetail extends Group {
  people: Person[];
}

export interface AddPersonToGroup {
  display_name: string;
  free_text_preferences?: string | null;
}

// --- taste profile (schemas/person_taxonomy_score.py, questionnaire.py) ----

export interface PersonTaxonomyScore {
  id: UUID;
  person_id: UUID;
  taxonomy_value: TaxonomyValue;
  /** Roughly -1 (dislikes) to 1 (likes). */
  score: number;
  is_hard_restriction: boolean;
  source: TaxonomySource;
  correction_count: number;
  updated_at: Timestamp;
}

/** Preference answers are -1..1; the UI maps its own scale onto that. */
export interface QuestionnaireSubmission {
  vegetarian_or_vegan: "none" | "vegetarian" | "vegan";
  avoids_gluten: boolean;
  avoids_dairy: boolean;
  has_nut_allergy: boolean;
  avoids_pork: boolean;
  avoids_beef: boolean;
  drinks_alcohol: boolean;
  appetizer_frequency: number;
  entree_vs_shared_preference: number;
  spice_tolerance: number;
  dessert_frequency: number;
  savory_vs_sweet_preference: number;
  non_alcoholic_drink_frequency?: number | null;
  sour_preference?: number | null;
  mild_preference?: number | null;
  side_frequency?: number | null;
  additional_preferences?: string | null;
}

// --- bills (schemas/bill.py, bill_item.py) ----------------------------------

export type BillStatus =
  "uploading" | "processing" | "needs_manual_entry" | "needs_review" | "open" | "closed";

export interface Bill {
  id: UUID;
  group_id: UUID;
  image_storage_path: string | null;
  merchant_name: string | null;
  bill_date: DateString | null;
  subtotal: Money | null;
  tax_total: Money | null;
  tip_total: Money;
  grand_total: Money | null;
  status: BillStatus;
  payer_person_id: UUID | null;
  /** Who was on this bill - the subset of the group that splits it. */
  participant_person_ids: UUID[];
  created_at: Timestamp;
  closed_at: Timestamp | null;
}

export interface BillItemAssignment {
  id: UUID;
  person_id: UUID;
  /** true = the scorer's guess; false = a person picked it. */
  is_predicted: boolean;
  /** 0..1, only meaningful when is_predicted. */
  confidence_score: number | null;
  share_fraction: number;
}

export interface BillItem {
  id: UUID;
  bill_id: UUID;
  raw_ocr_text: string | null;
  parsed_name: string;
  /** Unit price; the line costs price × quantity. */
  price: Money;
  quantity: number;
  base_type: BaseType | null;
  flavor_tags: FlavorTag[];
  dietary_flags: DietaryFlag[];
  assignments: BillItemAssignment[];
  created_at: Timestamp;
}

export interface BillDetail extends Bill {
  items: BillItem[];
}

export interface BillCreate {
  image_storage_path?: string | null;
  merchant_name?: string | null;
  bill_date?: DateString | null;
  /** Omit for "everyone in the group". */
  participant_person_ids?: UUID[];
}

export interface BillUpdate {
  merchant_name?: string | null;
  bill_date?: DateString | null;
  tax_total?: Money | null;
  tip_total?: Money | null;
}

export interface BillItemCreate {
  parsed_name: string;
  price: Money;
  quantity?: number;
  base_type?: BaseType | null;
  flavor_tags?: FlavorTag[];
  dietary_flags?: DietaryFlag[];
}

export type BillItemUpdate = Partial<BillItemCreate>;

export interface BillImageUrl {
  url: string;
  expires_in: number;
}

// --- payer, splits, settlement (schemas/payer.py, split.py) ----------------

export interface PayerSuggestion {
  person_id: UUID;
  display_name: string;
  payment_count: number;
  last_paid_at: Timestamp | null;
}

/** Live (unsaved) per-person breakdown - GET /bills/{id}/splits. */
export interface PersonSplit {
  person_id: UUID;
  display_name: string;
  item_subtotal_share: Money;
  tax_share: Money;
  tip_share: Money;
  total_owed: Money;
}

/** Saved settlement row with paid status - GET /bills/{id}/settlement. */
export interface SettlementRow extends PersonSplit {
  id: UUID;
  bill_id: UUID;
  is_paid: boolean;
  paid_at: Timestamp | null;
}
