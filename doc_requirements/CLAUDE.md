# CLAUDE.md — BillSplit

This file governs how anyone (human or Claude) works on the BillSplit codebase. It is binding: if a step here says "must," treat it as a hard rule, not a suggestion. It summarizes and enforces decisions already made in `buildguide.md` and `docs/architecture.md` (kept in the project's docs) and adds the engineering conventions those two documents don't cover. Read `buildguide.md` and `architecture.md` in full before writing any code — this file is the enforcement layer on top of them, not a replacement.

---

## 1. What this project is

BillSplit lets a user create a group of people, capture each person's usual food/order preferences, and upload a photo of a bill. The system extracts line items via OCR, predicts which items belong to which person (using stated preferences plus learned history from past bills), and produces an accurate split. It ships as a web app and a mobile app sharing one backend.

**Non-goals for v1** (do not build these unless this file is updated first):
- Payment processing / settling money — IOU tracking only, Splitwise-style.
- Multi-currency, or tax/tip jurisdiction rules beyond simple percentage tip/tax.
- Real-time multi-user collaborative editing of the same bill.

---

## 2. Who codes what — UPDATED 2026-09-06, see decision log below

| Component | Who writes the code | Claude's role |
|---|---|---|
| Backend (API, attribution engine, data model) | **Claude** | Builds it solo |
| Web app (Next.js) | **Claude** | Builds it solo |
| Mobile app (React Native / Expo) | **Claude** | Builds it solo |

**Decision log — 2026-09-06:** The original split (developer writes Backend/Web, Claude only guides/reviews; Claude codes Mobile solo) is superseded by an explicit developer decision. The developer will learn backend/web engineering separately, on a smaller dedicated project, rather than by writing this codebase line-by-line. Claude now codes all three components solo — Backend, Web, and Mobile — end to end. This was a deliberate, informed choice (Claude flagged that this reverses the project's original learning-by-doing design before proceeding), not an assumption.

What does NOT change:
- **Phase sequencing (§3) is unchanged.** Backend must still be stable before Web is built against it; Web/Mobile still wait on a stable API contract.
- **The 4-part block rhythm (§4) still applies to how Claude works**, minus the "human writes core logic" step — Claude now does setup, scaffolding, core logic, and a self-review pass for every block, documenting what was built at each step for the developer's visibility.
- All other decisions in this file, `buildguide.md`, `architecture.md`, and `design.md` are unaffected by this change.

---

## 3. Sequencing — do not reorder

1. **Phase 0: Environment & Infrastructure Setup** (once, upfront)
2. **Phase 1: Backend** — must exist and have a stable API contract before Web is built against it
3. **Phase 2: Web app** — built against the real Backend, not a mock, once Phase 1 is stable
4. **Phase 3: Mobile app** — proceeds in parallel with or after Web, once the API contract is stable

Do not start Web work against an unstable or partial Backend API contract, and do not start Mobile ahead of a stable API contract.

---

## 4. The 4-part block rhythm — every block, every time

Backend, Web, and Mobile phases are each broken into blocks (roughly one per entity/feature, not one per layer). Every block, regardless of phase, follows these four steps **in order**:

1. **Setup + install requirements** — tools, dependencies, accounts needed for this block only
2. **Initial scaffolding** — boilerplate/config wiring
3. **Core logic** — per §2's update, Claude writes this for all three components now
4. **Review** — Claude self-reviews what was built, calling out anything worth the developer's attention, before the next block starts

Do not skip step 4. Do not begin the next block's core logic before the current block has been reviewed. Blocks are intentionally fine-grained — resist the urge to batch several blocks together to "move faster"; the frequent review checkpoint is the point.

See `buildguide.md` for the full, current block lists for each phase — that document is the source of truth for exactly which blocks exist and their order; this file only enforces the rhythm and the role split around them.

---

## 5. Tech stack — confirmed, do not relitigate without cause

| Layer | Choice |
|---|---|
| Web frontend | Next.js (React, TypeScript) |
| Mobile frontend | React Native + Expo (TypeScript) |
| Backend | Python + FastAPI |
| Database | PostgreSQL, hosted on **Supabase** (confirmed provider) |
| Image storage | S3-compatible object storage (S3 or Supabase Storage) |
| Auth | JWT-based, or a managed provider (Supabase Auth / Clerk) to start |
| Hosting | Web → Vercel · Backend → Railway/Render/Fly.io · DB → Supabase · Mobile → Expo EAS |

These are accepted defaults, not open questions. If a real blocker forces a change, update `architecture.md` and this file in the same session — don't silently drift onto a different stack.

---

## 6. Prediction approach — note the override

`architecture.md` §4b originally described a staged v1 (rule-based heuristic) → v2 (trained classifier) approach to item→person prediction. **This has been superseded by `buildguide.md`.** The actual, current approach is:

- A **deterministic taxonomy-vector dot-product scorer**, built from day one — there is no separate heuristic v1 stage and no ML classifier v2 stage.
- The LLM's only role in this pipeline is mapping raw OCR text onto taxonomy categories — it does not do attribution reasoning itself.
- OCR text extraction (architecture.md §4a) is unaffected by this override: still a mature cloud OCR provider behind a swappable `OCRProvider` interface, not something to build from scratch.
- A human-confirmation step stays in the loop regardless — predictions are suggestions until the user confirms/corrects them, never auto-committed.

If you're reading `architecture.md` §4b and it still describes staged v1/v2, trust this file and `buildguide.md` instead, and update `architecture.md` to match when you're in that area of the code.

---

## 7. Core data model (entities, not full schema)

`User`, `Group`, `Person` (holds preferences — free text + structured taxonomy tags), `Bill` (image ref, merchant, date, totals, status), `BillItem` (raw OCR text, parsed name, price, quantity, predicted/assigned Person(s)), `Split` (final computed share per Person), `PredictionFeedback` (corrections — the training/learning signal for Person taxonomy-vector updates). Full schema lives with the Backend code (and is spelled out in full in `design.md` §5), not here.

---

## 8. API principles

- REST over HTTPS, JSON, versioned under `/api/v1`.
- Bill upload is async: `POST /bills` returns immediately with a `processing` status; clients poll for OCR + prediction completion (websocket/SSE is a later upgrade, not v1).
- Every predicted assignment is returned with a confidence score and stays editable until the bill is finalized.
- The backend must never block a request on the OCR provider inline for large images — queue it (a simple background task queue, or FastAPI `BackgroundTasks` for v1) so the API stays responsive.
- Web and Mobile share one backend and one database — there is a single source of truth, but no live push mechanism in v1. The agreed behavior is **auto-refresh on focus/reopen**: screens re-fetch when foregrounded or navigated back to, not full real-time collaborative editing (an explicit non-goal).

---

## 9. Cross-cutting concerns — non-negotiable from day one

- **Privacy:** bill images can contain sensitive purchase data (alcohol, medical items, etc.). Store images with per-user access control, and decide a retention/deletion policy before launch, not after.
- **Auth & authorization:** a Person's data is only visible to Users who share a Group with them. Enforce this at the API layer, not just the UI — a UI-only check is not acceptable here.
- **Observability:** structured logging around the OCR → prediction pipeline from day one. This pipeline is where things will silently go wrong (bad OCR read, wrong split), and it needs to be debuggable against real receipts.
- **Testing:** unit tests are required for split-calculation math (rounding/tax/tip allocation is a classic source of off-by-cent bugs). Maintain a fixture set of sample receipt images with expected OCR/split output for regression testing of the pipeline.

---

## 10. Repo layout

```
billsplit/
  apps/
    web/          # Next.js app
    mobile/       # Expo app
  packages/
    shared-types/ # TS types shared between web & mobile (and mirrored in API schema)
  backend/
    app/
      api/
      services/
        ocr/
        prediction/
      models/
      db/
    tests/
  docs/
    architecture.md
  buildguide.md
  CLAUDE.md
```

---

## 11. Coding conventions

These aren't decided anywhere else in the project yet — they're sensible defaults for this stack. Treat them as binding; if one gets changed, update it here so it stays the single source of truth.

**Backend (Python / FastAPI)**
- Format with `black`, lint with `ruff`. Type-hint all function signatures; run `mypy` (or at least `ruff`'s type-adjacent checks) before merging.
- Pydantic models for every request/response body — no raw dicts crossing the API boundary.
- One test file per module under `backend/tests/`, using `pytest`. New logic in `services/` (OCR, prediction) requires a test alongside it in the same PR, not as a follow-up.
- Migrations go through the chosen migration tool (e.g. Alembic) — no hand-edited schema changes against Supabase.
- Secrets and provider keys (OCR provider, Supabase, storage) live in environment variables, never committed; keep an up-to-date `.env.example`.

**Web & Mobile (TypeScript)**
- Format with `prettier`, lint with `eslint`. No `any` without a comment explaining why it's unavoidable.
- Shared types live in `packages/shared-types` and are imported by both `apps/web` and `apps/mobile` — do not redefine the same shape twice.
- Component-level tests (e.g. React Testing Library) for anything with non-trivial logic (the itemized-breakdown editing UI, settlement UI); pure presentational components don't need dedicated tests.
- API calls go through a single typed client module per app, not scattered `fetch` calls.

**Across the board**
- Commit messages: short imperative summary line ("Add Person taxonomy scoring endpoint"), body explains *why* when it's not obvious from the diff.
- One logical change per commit/PR — don't bundle an unrelated refactor into a feature commit.
- Every PR that touches the OCR → prediction pipeline must include or update a regression fixture (see §9).
- Never commit `.env`, credentials, or provider keys.

---

## 12. Open decisions still to resolve

Per `buildguide.md`, no build-sequencing decisions are open. The following implementation-detail decisions from `architecture.md` §9 remain open and should be resolved when that part of the code is reached, then recorded back into `architecture.md`:

- Which OCR provider to start with, and its free-tier limits. (Resolved in `design.md` §1: Google Cloud Vision.)
- Managed auth provider vs. hand-rolled JWT. (Resolved in `design.md` §1: Supabase Auth.)
- When to introduce a real task queue vs. FastAPI `BackgroundTasks`. (Resolved in `design.md` §1: `BackgroundTasks` for v1.)

Note: the `architecture.md` §9 item "how much history is enough before switching a group from v1 heuristic to v2 model" is **moot** — see §6 above, there is no v1/v2 staging in the current approach.

---

## 13. If this file and another doc disagree

Precedence order: **this file → `design.md` → `buildguide.md` → `architecture.md`**, except where this file explicitly says a `buildguide.md` decision supersedes `architecture.md` (as in §6). If you find a real contradiction, resolve it by editing the lower-precedence doc to match, in the same session you found it — don't leave the contradiction for the next person.
