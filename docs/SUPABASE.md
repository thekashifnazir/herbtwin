# Supabase (accounts and plant history)

Accounts are optional: with `HERBTWIN_SUPABASE_URL` and `HERBTWIN_SUPABASE_PUBLISHABLE_KEY`
unset, the app has no sign-in and stores nothing. Pattern and lessons:
`~/Code/tools/docs/app-services-stack.md` (Supabase, Resend SMTP).

## Hosted project (London) — one-off setup

1. **Auth → URL configuration:** Site URL = the app's address (development
   `http://localhost:8000`), and `<site>/auth/callback` in the redirect URLs. **The email
   link is built from this Site URL** (`{{ .SiteURL }}` in the templates); keep
   `HERBTWIN_SITE_URL` the same value (the app uses it for `Secure` cookies and its
   same-site check on the sign-in button).
2. **Sending domain:** Resend → Domains → `herbtwin.kashifnazir.com` (Ireland), its DKIM TXT
   and two `send` CNAME records in Cloudflare (DNS only), verified before anything else.
   Supabase's built-in mailer only reaches the project's team and runs out within a few
   sign-ins: it is not a launch path.
3. **Auth → Emails → SMTP Settings:** custom SMTP on; sender `noreply@example.com`,
   name `herbtwin`; host `smtp.resend.com`, port 465, user `resend`, password = a Resend API
   key with sending access (Kash enters it; it lives only in the dashboard).
4. **Auth → Emails → Templates:** **Magic link** and **Confirm signup** both get subject
   "Sign in to herbtwin" and the body of `supabase/templates/magic_link.html` /
   `confirmation.html` (the same link). A new person's first email is Confirm signup; without
   our template it carries Supabase's default link, which whatever opens it first spends.
   The repo files are the copy: dashboard and repo must match.
5. **Auth → Rate limits:** emails sent per hour raised to 30 (the default throttles the
   SMTP sender).
6. **Schema:** `supabase link --project-ref <ref>` then `supabase db push` (asks for the
   database password), or paste `supabase/migrations/*.sql` into the SQL editor and then
   `supabase migration repair --status applied <version>` once linked, so a later push
   does not re-run it. Each new file in `supabase/migrations/` is applied the same way after its
   PR merges (C3 adds `20261008120000_user_settings.sql`).
7. **`.env`:** `HERBTWIN_SUPABASE_URL`, `HERBTWIN_SUPABASE_PUBLISHABLE_KEY`,
   `HERBTWIN_SUPABASE_SECRET_KEY` (account delete, and `scripts/export_scored_pairs.py` run locally), `HERBTWIN_SITE_URL`.

Resend is a data processor (it sees sign-in email addresses): name it in the privacy page
when the app gets one (phase D).

## How sign-in works

The email links to our `/auth/callback?token_hash=…`. Opening it only shows a "Sign in"
button: mail scanners open links before the person does, and only the button's POST
(same site only) spends the one-time token. Tokens live in `httpOnly` cookies and are
refreshed when the access token is refused; an Auth outage keeps the cookies and the
page says "History is not available right now".

## Sharing scored pairs (C3)

After the first sign-in the home page asks once: "Help improve advice for everyone? We'd
share how past advice turned out, never your photos." The answer is kept in
`user_settings` (off by default, owner-only, deleted with the account) and can be changed
on My plants; the sign-in page's consent line says the same.

`uv run python scripts/export_scored_pairs.py` (Kash, locally; it needs
`HERBTWIN_SUPABASE_SECRET_KEY` because it reads across people) writes
`data/pool/scored_pairs.json` (gitignored): only people who said yes, one row per scored
pair with a fresh random pair id, species, month, region in whole degrees, signal before
and after, action, prediction, did-it and result. No photos, typed text, user ids or
emails. It is rebuilt from scratch each run, so switching off counts at the next export;
delete the file once the refit has read it. It prints counts per action; the confidence
refit waits for about 50 scored pairs. The migration grants the admin role read-only
access to just the columns it reads (with "Expose new tables" off, even the admin key is
refused without it); typed questions, advice text and the model's reasons stay closed to
it.

## Local stack (tests)

`colima start`, then
`supabase start -x vector,logflare,studio,imgproxy,realtime,postgres-meta,edge-runtime,supavisor`,
`supabase db reset`, the private working repo's `rls.sh`, and `uv run pytest -m supabase -q` for the
store's contract tests against real Postgres, Auth and Storage. Emails land in Mailpit
(`MAILPIT_URL` from `supabase status -o env`).
