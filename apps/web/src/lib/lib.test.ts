import type {
  BillDetail,
  BillItem,
  PersonTaxonomyScore,
  SettlementRow,
} from "@billsplit/shared-types";
import { describe, expect, it } from "vitest";

import { closeReadiness, itemAssignmentState, outstandingCents, reviewSummary } from "./bill";
import { formatCents, parseMoneyInput, toCents } from "./money";
import {
  CORE_QUESTIONS,
  OPTIONAL_QUESTIONS,
  rephrase,
  toSubmission,
  type Answers,
} from "./questionnaire";
import { fitWithin, isHeic, validateReceiptFile } from "./receipt-image";
import { summarizeTaste } from "./taxonomy";

const item = (overrides: Partial<BillItem> = {}): BillItem => ({
  id: "i1",
  bill_id: "b1",
  raw_ocr_text: null,
  parsed_name: "Dosa",
  price: "60.00",
  quantity: 1,
  base_type: "entree",
  flavor_tags: [],
  dietary_flags: [],
  assignments: [],
  created_at: "2026-11-20T00:00:00Z",
  ...overrides,
});

const assignment = (personId: string, predicted: boolean, confidence: number | null = null) => ({
  id: `a-${personId}`,
  person_id: personId,
  is_predicted: predicted,
  confidence_score: confidence,
  share_fraction: 1,
});

const row = (personId: string, total: string, paid: boolean): SettlementRow => ({
  id: `s-${personId}`,
  bill_id: "b1",
  person_id: personId,
  display_name: personId.toUpperCase(),
  item_subtotal_share: total,
  tax_share: "0.00",
  tip_share: "0.00",
  total_owed: total,
  is_paid: paid,
  paid_at: null,
});

describe("money", () => {
  it("works in integer cents", () => {
    expect(toCents("10.10")).toBe(1010);
    expect(toCents("0.29")).toBe(29); // 0.29 * 100 = 28.999… without rounding
    expect(toCents(null)).toBe(0);
    expect(formatCents(123456)).toMatch(/^1.?234\.56$/);
    expect(formatCents(-5)).toBe("-0.05");
  });

  it("validates typed amounts", () => {
    expect(parseMoneyInput("12")).toBe("12.00");
    expect(parseMoneyInput(" 12.5 ")).toBe("12.50");
    expect(parseMoneyInput("1,250.75")).toBe("1250.75");
    expect(parseMoneyInput("12.505")).toBeNull();
    expect(parseMoneyInput("-3")).toBeNull();
    expect(parseMoneyInput("abc")).toBeNull();
  });
});

describe("bill review", () => {
  it("classifies an item's assignment state", () => {
    expect(itemAssignmentState(item())).toBe("unassigned");
    expect(itemAssignmentState(item({ assignments: [assignment("a", true, 0.9)] }))).toBe("guess");
    expect(itemAssignmentState(item({ assignments: [assignment("a", true, 0.39)] }))).toBe(
      "guess-check",
    );
    expect(itemAssignmentState(item({ assignments: [assignment("a", false)] }))).toBe("confirmed");
    expect(
      itemAssignmentState(item({ assignments: [assignment("a", false), assignment("b", false)] })),
    ).toBe("shared");
  });

  it("counts what still needs attention", () => {
    const bill = {
      items: [
        item({ id: "1" }),
        item({ id: "2", assignments: [assignment("a", true, 0.1)] }),
        item({ id: "3", assignments: [assignment("a", true, 0.8)] }),
      ],
    } as BillDetail;
    expect(reviewSummary(bill)).toEqual({ unassigned: 1, toCheck: 1 });
  });
});

describe("closing a bill (design.md §12)", () => {
  it("needs a payer", () => {
    expect(closeReadiness(null, [row("a", "10.00", false)]).canClose).toBe(false);
  });

  it("ignores the payer's own row and waits on everyone else", () => {
    const rows = [row("a", "10.00", false), row("b", "5.00", false), row("c", "2.50", true)];
    const r = closeReadiness("a", rows);
    expect(r.canClose).toBe(false);
    expect(r.unpaidNames).toEqual(["B"]);
    expect(r.reason).toBe("Waiting on B to pay back.");
    expect(outstandingCents("a", rows)).toBe(500);
  });

  it("allows closing once everyone else has paid", () => {
    expect(closeReadiness("a", [row("a", "10.00", false), row("b", "5.00", true)]).canClose).toBe(
      true,
    );
  });
});

describe("questionnaire", () => {
  const fullCore: Answers = {
    vegetarian_or_vegan: "vegetarian",
    avoids_gluten: false,
    avoids_dairy: false,
    has_nut_allergy: true,
    avoids_pork: true,
    avoids_beef: true,
    drinks_alcohol: false,
    appetizer_frequency: 0.5,
    entree_vs_shared_preference: -1,
    spice_tolerance: 1,
    dessert_frequency: 0,
    savory_vs_sweet_preference: 0.5,
  };

  it("has the 12 core and 5 optional questions from design.md §4", () => {
    expect(CORE_QUESTIONS).toHaveLength(12);
    expect(OPTIONAL_QUESTIONS).toHaveLength(5);
  });

  it("refuses to submit with a core question unanswered", () => {
    const { spice_tolerance: _omit, ...partial } = fullCore;
    void _omit;
    expect(() => toSubmission(partial)).toThrow(/1 left/);
  });

  it("sends skipped optional answers as null and trims free text", () => {
    const body = toSubmission({ ...fullCore, sour_preference: -0.5, additional_preferences: "  " });
    expect(body.sour_preference).toBe(-0.5);
    expect(body.side_frequency).toBeNull();
    expect(body.additional_preferences).toBeNull();
    expect(body.has_nut_allergy).toBe(true);
  });

  it("rephrases every question for someone else", () => {
    for (const q of [...CORE_QUESTIONS, ...OPTIONAL_QUESTIONS]) {
      const text = rephrase(q.prompt, "Priya");
      expect(text, q.prompt).not.toMatch(/\byou\b|\byour\b/i);
    }
    expect(rephrase("Do you avoid gluten?", "Priya")).toBe("Does Priya avoid gluten?");
  });
});

describe("taste summary", () => {
  const score = (value: string, s: number, hard = false): PersonTaxonomyScore => ({
    id: value,
    person_id: "p",
    taxonomy_value: value as PersonTaxonomyScore["taxonomy_value"],
    score: s,
    is_hard_restriction: hard,
    source: "questionnaire",
    correction_count: 0,
    updated_at: "",
  });

  it("splits restrictions, likes and dislikes", () => {
    const t = summarizeTaste([
      score("vegetarian", 1, true),
      score("spicy", 1),
      score("dessert", -0.5),
      score("appetizer", 0.1),
    ]);
    expect(t.restrictions).toEqual(["Vegetarian"]);
    expect(t.likes).toEqual(["Spicy"]);
    expect(t.dislikes).toEqual(["Dessert"]);
    expect(t.hasQuestionnaire).toBe(true);
  });
});

describe("receipt photo checks (design.md §14)", () => {
  const file = (name: string, type: string, size = 1000) =>
    Object.defineProperty(new File(["x"], name, { type }), "size", { value: size });

  it("accepts JPEG, PNG and HEIC under 10 MB", () => {
    expect(validateReceiptFile(file("r.jpg", "image/jpeg"))).toBeNull();
    expect(validateReceiptFile(file("r.png", "image/png"))).toBeNull();
    expect(validateReceiptFile(file("IMG_1.HEIC", ""))).toBeNull();
    expect(isHeic(file("IMG_1.HEIC", ""))).toBe(true);
  });

  it("rejects other formats and big files", () => {
    expect(validateReceiptFile(file("r.pdf", "application/pdf"))).toMatch(/JPEG/);
    expect(validateReceiptFile(file("r.jpg", "image/jpeg", 11 * 1024 * 1024))).toMatch(/10 MB/);
  });

  it("shrinks to 2000px on the longest edge, keeping the aspect ratio", () => {
    expect(fitWithin(4000, 3000)).toEqual({ width: 2000, height: 1500 });
    expect(fitWithin(1080, 2400)).toEqual({ width: 900, height: 2000 });
    expect(fitWithin(800, 600)).toEqual({ width: 800, height: 600 });
  });
});
