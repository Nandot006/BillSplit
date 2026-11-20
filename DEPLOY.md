# Deploying BillSplit

Three services, set up in this order (each step needs a URL from the one before):

| Piece | Where | Cost |
|---|---|---|
| Database, logins, receipt photos | Supabase (your existing project) | Free plan |
| Backend API (`backend/`) | Render, free plan, from `render.yaml` | Free (sleeps after 15 min idle, ~1 min to wake) |
| Web app (`apps/web/`) | Vercel | Free (Hobby) |
| Receipt reading | Claude API, `claude-haiku-5-5` | Paid per receipt - a few paise each |

Keys go into dashboards and your local `.env` files only - never into git or a chat.

---

## 0. Push the code

From your own terminal, in the repo folder:

```bash
git status          # review what changed
git add -A
git commit -m "Finish web app; Claude OCR; per-bill participants; deploy config"
git push
```

`git add -A` also records two files that were deleted on purpose:
`backend/app/services/ocr/google_vision.py` (replaced by Claude) and
`apps/web/src/app/dashboard/page.tsx` (moved to `apps/web/src/app/(app)/dashboard/`).

## 1. Supabase

1. **SQL Editor → New query →** paste all of `supabase/setup.sql` → **Run**.
   This creates the private `bill-images` bucket and the rule that users can only
   upload into their own folder. (The tables are created by the backend itself, in step 3.)
2. **Project Settings → API keys** (or **API**). Copy:
   - Project URL - `https://<ref>.supabase.co`
   - the **anon** / **publishable** key (public, safe in the browser)
   - the **service_role** / **secret** key (secret - backend only)
3. **Project Settings → JWT Keys.** If it shows a **legacy JWT secret** and your
   project still signs with it, copy that too. If it uses the newer signing keys,
   you don't need anything from here - the backend fetches the public keys itself.
4. **Connect** (top bar) → **Session pooler** → copy the connection string
   (`postgresql://postgres.<ref>:[YOUR-PASSWORD]@aws-0-<region>.pooler.supabase.com:5432/postgres`)
   and put your database password in it.
   Use **Session pooler**, not "Direct connection" - the direct host is IPv6-only
   and Render can't reach it.

## 2. Claude API key

1. Sign in at the Claude Console (console.anthropic.com), add billing credit.
2. **API keys → Create key**, name it `billsplit-render`, copy it.
3. Recommended: set a monthly spend limit under **Limits**, so a bug or abuse can't
   run up a bill.

## 3. Render (backend)

1. render.com → sign in with GitHub → **New → Blueprint** → pick `Nandot006/BillSplit`.
   Render finds `render.yaml` and proposes the `billsplit-api` service on the free plan.
2. Fill the variables it asks for:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | the Session pooler string from 1.4 |
   | `SUPABASE_URL` | Project URL from 1.2 |
   | `SUPABASE_SERVICE_ROLE_KEY` | service_role key from 1.2 |
   | `SUPABASE_JWT_SECRET` | legacy JWT secret from 1.3, **or leave empty** |
   | `ANTHROPIC_API_KEY` | from step 2 |
   | `CORS_ORIGINS` | `http://localhost:3000` for now - updated in step 5 |

3. **Apply**. The first build takes a few minutes. In **Logs** you should see
   `Running upgrade ... -> c41f8e7a9d02` (tables created, row level security on),
   then `Uvicorn running`.
4. Open `https://<your-service>.onrender.com/` - it should show
   `{"status":"ok","env":"prod","db_loaded":true}`. Copy this URL.

## 4. Vercel (web app)

1. vercel.com → **Add New → Project** → import `Nandot006/BillSplit`.
2. **Root Directory → Edit → `apps/web`**. Framework is detected as Next.js; leave
   build settings as they are.
3. **Environment Variables:**

   | Variable | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | `https://<your-service>.onrender.com/api/v1` |
   | `NEXT_PUBLIC_SUPABASE_URL` | Project URL from 1.2 |
   | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | anon / publishable key from 1.2 |

4. **Deploy**, then copy the production URL (e.g. `https://billsplit-abc.vercel.app`).

## 5. Connect them

1. **Render → billsplit-api → Environment →** set `CORS_ORIGINS` to your Vercel URL
   (no trailing slash). For several, separate with commas:
   `https://billsplit-abc.vercel.app,http://localhost:3000`. Save - Render redeploys.
2. **Supabase → Authentication → URL Configuration:**
   - **Site URL:** your Vercel URL
   - **Redirect URLs:** add `https://<your-vercel-url>/auth/callback`
     (and `http://localhost:3000/auth/callback` if you'll run it locally)

## 6. Check it works

1. Open the Vercel URL. If Render was asleep, the first page can take ~1 minute.
2. Create an account → confirm the email → you land logged in.
3. Create a group → answer your questionnaire → add a friend.
4. **New bill → Take photo / Choose photo** with a real receipt. Within ~30 s it
   should list the items with a guess for each.
5. Fix a guess, confirm, set the payer, mark someone paid, close the bill.

If a step fails, **Render → Logs** shows the backend side - lines starting with
`billsplit.ocr` trace each receipt through reading and tagging.

### Good to know

- **Email limits:** Supabase's built-in email sender only sends a few emails per
  hour. Fine for you and friends testing; for real users, add your own SMTP under
  Authentication → Emails, or turn off "Confirm email" while testing.
- **Free Supabase projects pause** after about a week without activity. Unpause from
  the dashboard; nothing is lost.
- **Running the web app locally** (optional): in the repo root on Windows run
  `npm install`, copy `apps/web/.env.local.example` to `apps/web/.env.local`, fill it
  in (pointing `NEXT_PUBLIC_API_URL` at your Render URL works), then
  `npm run dev -w apps/web`.
