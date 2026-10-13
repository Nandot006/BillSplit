# BillSplit — Design Decisions & Entity Schema

This document resolves every open decision left by `buildguide.md`, `CLAUDE.md`, and `architecture.md` before Phase 1 (Backend) work begins. It is a companion to those three docs, not a replacement — precedence order is unchanged: **`CLAUDE.md` → `buildguide.md` → `architecture.md` → this file**, except where this file is explicitly resolving something none of the other three settled (which is its whole purpose). If a decision here ever conflicts with one of the other three, treat it as this file updating them, and reconcile the wording in the same session it's noticed.

Every decision below was reached through a structured interview with the developer (not assumed by Claude) and confirmed before being recorded.

---

## 1. Infrastructure & tooling decisions

| Area | Decision | Notes |
|---|---|---|
| Auth | **Supabase Auth** | Reuses the Supabase project already confirmed for Postgres. |
| Auth wiring placement | **Phase 1 block 1** (Setup & scaffolding) | Not a dedicated block — it's config + a JWT-verification middleware, not core logic. `Person` links to it (see §3). |
| OCR provider | **Google Cloud Vision** (primary) | Free tier (1,000 units/month) comfortably covers this project's scale. Sits behind the swappable `OCRProvider` interface per `architecture.md` §4a. |
| OCR fallback | **Tesseract**, optional, later | Fully local/offline, zero cost, but noticeably worse on skewed/faded photographed receipts without a preprocessing pipeline. Not built for v1 — a future addition if wanted for the learning value, not a replacement for Cloud Vision. |
| OCR→taxonomy LLM | **Gemini API**, small/cheap tier (e.g. Flash-Lite) | Free tier. This is a small classification task (map OCR text → taxonomy categories), not a reasoning task — no need for a large model. |
| Image storage | **Supabase Storage** | One vendor for DB + Auth + Storage keeps Phase 0 simple. |
| Image retention | **Keep indefinitely** | Revisit a deletion policy once there's real usage data on storage cost — bill images are the source of truth if a split is ever disputed. |
| Migrations | **Alembic** | Standard for SQLAlchemy/FastAPI. |
| Task queue | **FastAPI `BackgroundTasks`** for v1 | No extra infra (no Redis/broker). Upgrade to Celery/RQ later if volume or reliability needs demand it. |
| Environments | **Dev + Prod only** | No staging tier — not enough team/process overhead to justify it for a solo project. |
| Secrets | **`.env`** (gitignored, `.env.example` committed) locally; hosting provider's secret store (Railway/Render/Vercel/Expo EAS) in deployed environments. | |
| Observability | **Structured JSON logs to stdout** around the OCR→prediction pipeline for v1 (request IDs, OCR confidence, scoring inputs/outputs). No dedicated error-tracking service (e.g. Sentry) yet — easy to wire in once there's a real deploy target. | |

---

## 2. Person ↔ Group scoping

**A Person is scoped to exactly one Group.** If the same real human is in two different Groups (e.g. a coworker lunch group and a family group), that's two separate `Person` rows, each with its own independently-learned taxonomy vector. This matches `architecture.md`'s original phrasing of Person as "a member of a Group," and reflects that someone's order habits can genuinely differ by social context — a correction made in one group's history should not bleed into predictions in an unrelated group.

A `Person` may optionally be linked to a `User` account via a nullable `supabase_user_id`:
- `supabase_user_id IS NULL` → **shadow contact** (someone in the group who hasn't signed up).
- `supabase_user_id IS NOT NULL` → **claimed account** (a real registered User).

A single `User` can be linked to multiple `Person` rows — one per Group they're a claimed member of.

---

## 3. Taxonomy (fixed v1 list)

Hardcoded for v1 — a small, shippable set, expanded later once real bills reveal gaps. Not a dynamically-editable table; represented as constrained enums in the schema.

**Base types** (mutually exclusive per item — pick one): `appetizer`, `entree`, `side`, `dessert`, `drink-non-alcoholic`, `drink-alcoholic`, `shared-platter`

**Flavor tags** (an item can have several): `spicy`, `sweet`, `savory`, `sour`, `mild`

**Dietary flags** (an item can have several; on a Person these represent a restriction, not just a preference): `vegetarian`, `vegan`, `gluten-free`, `dairy-free`, `nut-free`, `no-pork`, `no-beef`, `no-alcohol`

That's 20 taxonomy values total — the dimensionality of every Person and BillItem vector (see §6).

---

## 4. Cold-start questionnaire (12 core + 5 optional)

Drafted here for review/editing — this is user-facing copy, not an architectural decision. Each question seeds a `PersonTaxonomyScore` row with `source=questionnaire`.

**Core (12):**
1. Do you follow a vegetarian or vegan diet? *(seeds: vegetarian, vegan — hard restriction if yes)*
2. Do you avoid gluten? *(gluten-free)*
3. Do you avoid dairy? *(dairy-free)*
4. Do you have any nut allergies? *(nut-free)*
5. Do you avoid pork for religious or personal reasons? *(no-pork)*
6. Do you avoid beef for religious or personal reasons? *(no-beef)*
7. Do you drink alcohol? *(no-alcohol if "no"; drink-alcoholic affinity if "yes")*
8. When you eat out, how often do you order an appetizer or starter? *(appetizer)*
9. Do you usually order a main dish, or prefer to share smaller plates? *(entree vs. shared-platter)*
10. How do you feel about spicy food? *(spicy)*
11. Do you have a sweet tooth — do you usually order dessert? *(dessert, sweet)*
12. Do you generally prefer savory over sweet flavors? *(savory vs. sweet)*

**Optional (5):**
13. Do you usually order non-alcoholic drinks (soda, juice, mocktails)? *(drink-non-alcoholic)*
14. Do you enjoy sour or tangy flavors (citrus, vinegar-based dishes)? *(sour)*
15. Do you tend to order milder dishes overall? *(mild)*
16. Do you usually order a side (fries, rice, etc.) alongside your main? *(side)*
17. Anything else about your food preferences or restrictions we should know? *(free text → `Person.free_text_preferences`, not a taxonomy score)*

---

## 5. Entity schema

```
User
  id                  uuid PK   -- = Supabase Auth user id
  email               text
  display_name        text
  created_at          timestamptz

Group
  id                  uuid PK
  name                text
  creator_user_id     uuid FK -> User.id
  created_at          timestamptz

Person
  id                       uuid PK
  group_id                 uuid FK -> Group.id NOT NULL   -- scoped to one group, see §2
  supabase_user_id         uuid FK -> User.id NULL         -- null = shadow contact
  display_name             text
  free_text_preferences    text NULL
  created_at               timestamptz

PersonTaxonomyScore
  id                  uuid PK
  person_id           uuid FK -> Person.id
  taxonomy_value      enum (one of the 20 values in §3)
  score                float          -- affinity weight, roughly [-1, 1]
  is_hard_restriction  boolean        -- true for a dietary flag the person requires (see §7)
  source               enum (questionnaire | learned_correction)
  correction_count     integer default 0   -- denominator for the shrinking learning rate, see §9
  updated_at           timestamptz
  UNIQUE (person_id, taxonomy_value)

Bill
  id                  uuid PK
  group_id            uuid FK -> Group.id
  image_storage_path  text NULL       -- Supabase Storage path
  merchant_name       text NULL
  bill_date           date NULL
  subtotal            numeric(10,2)
  tax_total           numeric(10,2)
  tip_total           numeric(10,2) default 0
  grand_total         numeric(10,2)
  status              enum (uploading | processing | needs_manual_entry | needs_review | open | closed)
  payer_person_id     uuid FK -> Person.id NULL
  created_at          timestamptz
  closed_at           timestamptz NULL

BillItem
  id                  uuid PK
  bill_id             uuid FK -> Bill.id
  raw_ocr_text        text NULL       -- null if manually entered
  parsed_name         text
  price               numeric(10,2)
  quantity            integer default 1
  base_type           enum NULL       -- one of the 7 base types, set by the OCR->taxonomy LLM step
  created_at          timestamptz

BillItemFlavorTag              -- join table: an item can have several flavor tags
  bill_item_id        uuid FK -> BillItem.id
  flavor_tag          enum (one of the 5 flavor tags)

BillItemDietaryFlag             -- join table: an item can have several dietary flags
  bill_item_id        uuid FK -> BillItem.id
  dietary_flag        enum (one of the 8 dietary flags)

BillItemAssignment             -- many-to-many BillItem <-> Person; supports shared items (§8)
  id                  uuid PK
  bill_item_id        uuid FK -> BillItem.id
  person_id           uuid FK -> Person.id
  is_predicted        boolean         -- true = came from the scorer, false = manually added/edited
  confidence_score    float NULL      -- only meaningful when is_predicted = true, see §8
  share_fraction       numeric        -- 1 / (number of people assigned to this item)

PredictionFeedback
  id                          uuid PK
  bill_item_id                uuid FK -> BillItem.id
  original_predicted_person_id uuid FK -> Person.id NULL
  corrected_person_id          uuid FK -> Person.id
  created_at                   timestamptz

Split
  id                  uuid PK
  bill_id             uuid FK -> Bill.id
  person_id           uuid FK -> Person.id
  item_subtotal_share numeric(10,2)   -- sum of this person's share across assigned/shared items
  tax_share            numeric(10,2)   -- even split, largest-remainder rounding, see §10
  tip_share            numeric(10,2)   -- even split, largest-remainder rounding, see §10
  total_owed           numeric(10,2)
  is_paid              boolean default false   -- payer-controlled "marked as paid"
  paid_at              timestamptz NULL

PayerHistory
  group_id            uuid FK -> Group.id
  person_id           uuid FK -> Person.id
  payment_count       integer default 0
  last_paid_at         timestamptz NULL
  PRIMARY KEY (group_id, person_id)
```

---

## 6. Attribution scoring engine

Each `Person` and each `BillItem` is represented as a 20-dimensional vector over the taxonomy values in §3.

- **Person vector:** one float weight per taxonomy value (`PersonTaxonomyScore.score`), seeded from the questionnaire (§4) and updated by corrections (§9).
- **Item vector:** 1.0 for every taxonomy value the item is tagged with (its one base type, plus any flavor/dietary tags from the OCR→taxonomy LLM step), 0 otherwise.
- **Dietary flags are a hard exclude, not a weighted dimension.** If a Person has a dietary flag marked as `is_hard_restriction = true` (e.g. vegan) and a candidate item is *not* tagged with that flag, that Person is removed from consideration for that item entirely — it isn't just down-weighted. *(Edge case: if this excludes every person in the group from an item, fall back to `needs_review` with no default assignment — someone has to pick manually.)*
- **Score = plain dot product** of the two vectors, restricted to base-type and flavor-tag dimensions (dietary flags already did their filtering work above). The highest-scoring remaining Person(s) get the item.

**Confidence score:** normalized gap between the top-scoring Person and the runner-up, expressed as 0–100% (a landslide win → high confidence, a near-tie → low). Predictions are flagged **"needs review"** when confidence falls below **40%**, or on an exact tie.

---

## 7. Shared items

A `BillItem` can be assigned to more than one Person (`BillItemAssignment` is many-to-many). The scorer still predicts a single best-match default; the itemized-breakdown editing UI (Phase 2 block 7 / Phase 3 block 7) lets the user multi-select additional people onto an item before finalizing. Cost splits evenly among everyone assigned (`share_fraction = 1 / assigned_count`).

---

## 8. Learning loop (`learned_correction`)

Every correction updates the affected Person's `PersonTaxonomyScore` rows with a **shrinking learning rate, decaying by that Person's own correction count**:

```
new_score = old_score + (base_rate / (1 + corrections_so_far_for_this_person)) * signal
```

Early corrections move the vector a lot (fast cold-start improvement); later corrections nudge it gently, so one odd order doesn't destabilize an otherwise well-established preference. `corrections_so_far_for_this_person` is `PersonTaxonomyScore.correction_count`, incremented on each `PredictionFeedback` row written for that person.

---

## 9. Bill editing & person-removal redistribution

When a person is removed from an open bill:
- **Tax and tip** are recalculated as an even split across the remaining people (see §10 for the exact rounding rule) — not proportional to item subtotal.
- **Items** previously assigned to the removed person go back into the prediction pool and are **re-scored against only the remaining people's vectors** — not split evenly by default, since e.g. "the vegetarian dish" should go to whichever remaining person is the next-best match.

---

## 10. Tax, tip, and rounding

- **Tax:** `total_tax / remaining_people` — an even split across everyone on the bill (per `buildguide.md` block 10), not proportional to what each person ordered.
- **Tip:** same rule — an even split, consistent with tax, rather than a separate proportional-to-subtotal calculation.
- **Rounding:** the **largest-remainder method** — round every person's share down to the nearest cent, then distribute the leftover pennies one at a time to whichever shares have the largest fractional remainder. This guarantees the split always sums to exactly the bill total, which matters given `CLAUDE.md` §9's explicit concern about off-by-cent bugs — this is exactly the calculation that needs a unit test fixture per that requirement.

---

## 11. Payer tracking & tie-break

Prefill defaults to whoever paid **least recently**: sort by `last_paid_at` ascending, with `NULL` (never paid) sorted first. If still tied, break alphabetically by Person `display_name` for a deterministic, explainable result. The prefill is always manually overridable.

---

## 12. Settlement & closing

- **Closing is hard-gated**: a bill can only move to `closed` once every non-payer Person's `Split.is_paid` is true.
- **Closed bills are fully immutable**: no editing items, no re-adding/removing people, no un-marking payment, no reopening. A mistake after closing means creating a correcting entry, not editing history.
- Closed bills still feed the taxonomy-vector learning signal (§8) — they just can't be altered once counted.

---

## 13. OCR pipeline & failure handling

1. Receipt image → **Google Cloud Vision** (`OCRProvider` interface) → raw text.
2. Raw text → **Gemini API** (small model tier) → mapped onto the taxonomy in §3, populating `BillItem.base_type` and the `BillItemFlavorTag`/`BillItemDietaryFlag` join tables.
3. **On OCR failure** (provider error, or text extraction that can't be parsed into line items at all): the Bill moves to `needs_manual_entry` status. The user types in merchant, items, prices, and tax/tip by hand instead of the pipeline populating them. No automatic retry loop — a bad photo is a bad photo; manual entry is simply always available as an option on any bill stuck in `processing` or `needs_manual_entry`.

---

## 14. Web-specific decisions (Phase 2)

- **Session/auth (block 2):** Supabase's official Next.js SSR client, storing the session in cookies (works across server and client components) + a `middleware.ts` that redirects unauthenticated requests away from protected routes before render.
- **Upload UX (block 6):** accept JPEG, PNG, HEIC; 10MB cap; client-side compression/resize to ~2000px longest edge before upload, to keep storage and OCR payload size down and reject obviously-wrong files early.

---

## 15. Mobile-specific decisions (Phase 3, Claude-coded)

- **Navigation:** bottom tab navigation for top-level sections (Groups, Bills, Profile), with stack navigation within each tab for drill-down (e.g. Group → Bill detail).
- **Session storage:** `expo-secure-store` (encrypted) for the Supabase session token — the standard choice over `AsyncStorage` for auth tokens.
- **Receipt capture:** `expo-image-picker` camera mode, with a gallery-picker fallback for an existing photo.

---

## 16. Items intentionally deferred, not decided now

These were explicitly discussed and deferred rather than left open by oversight:

- Bill image retention/deletion policy beyond "keep indefinitely" — revisit once real storage-cost data exists.
- Dedicated error-tracking service (e.g. Sentry) — add once there's a real deploy target.
- Tesseract OCR fallback — worth adding later for the learning value, not required for v1 launch.
- Real task queue (Celery/RQ) — upgrade path if `BackgroundTasks` proves insufficient under real load.
