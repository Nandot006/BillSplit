# Outside Claude Code — Setup & Account Tasks (BillSplit)

Things that need to happen *outside* this tool: cloud consoles, account signups, local OS/admin changes. Claude Code can write code, run local commands, and (with your confirmation) push to GitHub — but it can't click through a web signup flow, hold your payment details, or change OS-level security policy.

Status below reflects what's actually configured right now (checked via `backend/.env`, `apps/web/.env.local`), not assumptions.

---

## Phase 0 — cloud accounts & credentials (blocking, do first)

### Supabase project (Postgres + Auth + Storage)
- Create a project at supabase.com
- Copy the Postgres connection string → `backend/.env` → `DATABASE_URL` — **already set**
- Copy the project URL + anon key → `apps/web/.env.local` → `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` — **not set yet** (`.env.local` doesn't exist)
- Copy the JWT secret → `backend/.env` → `SUPABASE_JWT_SECRET` — **not set yet**

### OCR provider account — Google Cloud Vision (per `architecture.md` §4a, `design.md` §1)
- Create/select a GCP project, enable the Vision API
- Create a service account, download its JSON key → `backend/.env` → `GOOGLE_APPLICATION_CREDENTIALS` (path to the file)
- If using Gemini for the OCR→taxonomy LLM mapping step instead/also → `GEMINI_API_KEY`
- **Not set yet**

### Object storage for bill images
- S3-compatible bucket, or a Supabase Storage bucket
- Must have per-user access control configured (bill images can contain sensitive purchase data — `CLAUDE.md` §9 is explicit this isn't optional)
- **Not set yet**

### Vercel account
- Used later, in the Web phase — provision now per Phase 0, nothing to wire up yet

### Expo EAS account
- Used later, in the Mobile phase — provision now per Phase 0, nothing to wire up yet

---

## Local machine / OS-level

- **Blocking local backend tests right now:** a Windows Application Control (WDAC/AppLocker) policy is blocking psycopg2's native DLL (`_psycopg`) from loading:
  `ImportError: DLL load failed while importing _psycopg: An Application Control policy has blocked this file.`
  This needs an admin-level allow-list exception for that DLL (or the policy owner's help) — it's a machine security policy, not something fixable from inside a coding session.

---

## When ready to deploy (later phases)

- Backend hosting account — Railway, Render, or Fly.io (pick one, per `CLAUDE.md` §5 — not yet chosen)
- Set the backend env vars (`DATABASE_URL`, `SUPABASE_*`, OCR credentials) in that provider's dashboard
- Vercel: link the `apps/web` project, set its env vars in the Vercel dashboard
- Expo EAS: run the build/submit flow for iOS/Android; Apple Developer + Google Play accounts only needed if actually publishing to app stores

---

## Handling secrets

Once the accounts above exist, paste the real values directly into `backend/.env` / `apps/web/.env.local` yourself (both are gitignored) rather than pasting keys into the chat — keeps credentials out of the conversation transcript.

---

## Already in Claude Code's reach (not actually outside-scope)

- **Git / GitHub** — `gh` is authenticated on this machine (account `Nandot006`). `git init`, repo creation, and pushing can all be done inside a Claude Code session with your confirmation; no separate manual step needed. (The project currently has no git repo initialized.)
