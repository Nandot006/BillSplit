# BillSplit — Build Guide

This is a phased roadmap for building BillSplit, with teaching embedded at
each phase. It assumes the product decisions in the (separate) PRD and the
tech-stack defaults in `architecture.md` as given.

**Coding responsibility**

| Component | Who codes | Claude's role |
|---|---|---|
| Backend (API, attribution engine, data model) | **You** | Guide, teach, review — not writing the code |
| Web app (Next.js) | **You** | Guide, teach, review — not writing the code |
| Mobile app (React Native / Expo) | **Claude** | Builds it solo; still documented here in the same 4-part structure for your visibility |

**Sequencing:** Environment Setup → Backend → Web (Backend must exist before
Web can be built against it) → Mobile proceeds in parallel/after, once the
API contract is stable.

**Tech stack (accepted defaults from `architecture.md`):** Next.js (web),
React Native + Expo (mobile), FastAPI/Python (backend), PostgreSQL (DB).
**Prediction approach (supersedes `architecture.md` §4b):** a deterministic
taxonomy-vector dot-product scorer from day one — no heuristic v1 / ML
classifier v2 staging. The LLM's only role is mapping raw OCR text onto
taxonomy categories, not attribution reasoning.

---

## The 4-part block rhythm

Every block below (Backend, Web, and Mobile) follows the same four steps:

1. **Setup + install requirements** — tools, dependencies, accounts needed for this block
2. **Initial scaffolding** — boilerplate/config wiring, typically done together since it's not where the learning value is
3. **Core logic, coded by you with guidance** — the actual learning happens here; Claude explains concepts and teaches as you go, but you write the code (Backend, Web only — Mobile is Claude-coded)
4. **Review** — Claude reviews what was built, catches issues, confirms it's solid before moving to the next block

Blocks are **fine-grained** (per entity/feature, not per layer), so you get a review checkpoint frequently rather than after long, multi-concept stretches.

---

## Phase 0: Environment & Infrastructure Setup

A single upfront block covering accounts/infrastructure needed across the
whole project, so this busywork happens once rather than interrupting later
phases. Note: the Vercel and EAS items here aren't *used* until the Web and
Mobile phases respectively — they're just provisioned now.

- **Postgres provider** — **Supabase** (confirmed)
- Object storage for bill images (S3-compatible, or Supabase Storage)
- OCR provider account (Google Cloud Vision / AWS Textract / Azure Document Intelligence — per `architecture.md` §4a)
- Vercel account (used later, in the Web phase)
- Expo EAS account (used later, in the Mobile phase)

---

## Phase 1: Backend (FastAPI + Python) — you code, Claude guides

Each block follows the 4-part rhythm above.

1. **Setup & project scaffolding** — FastAPI project structure, DB connection, env config, migrations tool
2. **Person entity** — profile, shadow-contact vs. claimed-account distinction
3. **Taxonomy schema** — base types, flavor tags, dietary flags (shared reference data everything else depends on)
4. **Cold-start questionnaire** — 12 core + 5 optional questions → seeds `source=questionnaire` scores onto a Person's taxonomy-vector
5. **Group entity** — creator-only add/remove, scopes people to a group
6. **Attribution scoring engine** — the dot-product scorer (person vector vs. item vector); the app's differentiator
7. **Bill + BillItem entities** — receipt metadata, line items, OCR-failure manual-entry fallback
8. **OCR → taxonomy mapping (LLM step)** — raw OCR text → taxonomy categories, feeding block 6's scorer
9. **Prediction + correction loop** — running the scorer on a bill, capturing `learned_correction` feedback with shrinking learning rate back onto Person profiles
10. **Bill editing & person-removal redistribution** — tax recalculation (`total_tax / remaining_people`) + re-scoring redistribution for remaining people
11. **Payer tracking** — lightweight `{group_id, person_id, payment_count, last_paid_at}`, prefill/tie-break logic
12. **Settlement & closing** — per-person settlement amount, payer-controlled "marked as paid," close-gated-on-full-settlement, immutability

---

## Phase 2: Web app (Next.js) — you code, Claude guides

Mirrors the backend's entity order, plus web-specific concerns (auth
session handling, routing, upload UX) with no backend equivalent.

1. **Setup & project scaffolding** — Next.js project, TypeScript config, API client, env config
2. **Auth & session flow** — sign up/login UI, session persistence, protected routes
3. **Person/profile UI** — view/edit a profile; shadow-contact vs. claimed-account states
4. **Cold-start questionnaire UI** — the 12 core + 5 optional question flow, triggered at registration and when adding a contact
5. **Group UI** — create group, add/remove members (creator-only), group list/detail views
6. **Bill upload flow** — receipt image upload (file-picker), async "processing" state while OCR/prediction runs (polling)
7. **Itemized breakdown & editing UI** — predicted assignments, editable before finalizing, shared/split item UI. *Includes auto-refresh on focus/reopen* (re-fetches current bill state when the tab is refocused or the user navigates back — no live push/websocket)
8. **Correction feedback wiring** — connecting UI edits to the backend's `learned_correction` signal
9. **Bill editing & person-removal UI** — reflects tax recalculation + redistribution when someone's removed from an open bill. *Includes auto-refresh on focus/reopen*, same as block 7
10. **Payer & settlement UI** — payer dropdown (prefilled via `payment_count`/`last_paid_at`), "mark as paid" toggle (payer-controlled), settlement summary view
11. **Bill closing UI** — close action gated on full settlement; immutable state after closing

---

## Phase 3: Mobile app (React Native / Expo) — Claude codes solo

Same scope as Web, documented in the same 4-part structure for visibility.
Can proceed in parallel with, or after, Web once the backend API contract
is stable. Block 1 and block 6 differ from Web; the rest are equivalent in
scope.

1. **Setup & project scaffolding** — Expo project, navigation (stack/tab), API client, env config
2. **Auth & session flow** — same scope as Web block 2, native session storage
3. **Person/profile UI** — same scope as Web block 3
4. **Cold-start questionnaire UI** — same scope as Web block 4
5. **Group UI** — same scope as Web block 5
6. **Receipt capture & upload flow** — camera / `expo-image-picker`; mobile's genuinely distinct block (camera-first, vs. Web's file-picker)
7. **Itemized breakdown & editing UI** — same scope as Web block 7, including auto-refresh on focus/reopen
8. **Correction feedback wiring** — same scope as Web block 8
9. **Bill editing & person-removal UI** — same scope as Web block 9, including auto-refresh on focus/reopen
10. **Payer & settlement UI** — same scope as Web block 10
11. **Bill closing UI** — same scope as Web block 11

---

## Notes on cross-client sync

Web and Mobile share one backend and one database — there's a single
source of truth, so there's no data-divergence risk. What they don't have
is a live push mechanism: if Person A is viewing a bill on Web and Person B
edits it on Mobile, A's screen goes stale until it refetches. Confirmed
behavior for v1 is **auto-refresh on focus/reopen** — screens automatically
re-fetch when the app/tab is foregrounded or the user navigates back to a
bill screen. This is *not* full real-time collaborative editing (two people
editing the same field simultaneously) — that remains an explicit v1
non-goal per `architecture.md`.

---

## Open decisions still to resolve

None — every decision in this guide, including the Postgres provider
(Supabase), reflects choices already confirmed across prior sessions.
