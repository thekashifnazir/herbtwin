# Re-photo reminders: operations

Spec: `docs/superpowers/specs/2026-10-11-phase-d-deploy-design.md`, section 7 (D65).

## What runs where

- **The box** ("Email me when it's time to check again") sits under a signed-in answer whose
  main action has a check window. Ticking it stores one row in Supabase `reminders`, due
  halfway through that window (watering: day 4 of 1 to 7). Unticking deletes the row
  until the email has gone; a sent reminder stays, so an answer gets one email at most.
- **The job**, `python -m herbtwin.reminders`, sends the reminders due today through Resend,
  once each (Resend idempotency key `reminder-<answer id>`), and marks them sent. A
  reminder is turned off instead when a later photo of the plant exists, when its window
  has passed, or when the account is gone.
- **Where it runs:** this repo ships no scheduler. Run `python -m herbtwin.reminders` once a
  day from your own scheduler (cron, a scheduled CI job or a serverless job), from the
  app's image or a checkout after `uv sync`. README, "Deploying your own copy", gives one
  way to do it.
- **Settings:** the job reads `HERBTWIN_SUPABASE_URL`, `HERBTWIN_SUPABASE_SECRET_KEY`,
  `HERBTWIN_RESEND_API_KEY`, `HERBTWIN_MAIL_FROM` and `HERBTWIN_REMINDER_SECRET`, and
  `HERBTWIN_SITE_URL` for the links in the email; `.env.example` names and explains each.
  Keep the keys in your scheduler's secret store, not in the repo. The site needs the same
  `HERBTWIN_REMINDER_SECRET` to check unsubscribe links.
- **Unsubscribe:** the link opens a page with one "Stop this reminder" button (mail scanners
  open links, so opening changes nothing). Mail clients' one-click unsubscribe posts to the
  same address.

## Running it now

Run `python -m herbtwin.reminders` (or `uv run python -m herbtwin.reminders`) with the
settings above in the environment. A run with nothing due ends with
`reminders: sent 0, skipped 0, failed 0` in its log.

## When a run fails

The exit code says what happened:

- Exit 1 means at least one send failed: it stays due and the next day's run tries again
  until the window ends.
- Exit 2 means it could not start: the log names the missing setting, or Supabase was
  unreachable.

## Turning it off

Stop your scheduled run. Without `HERBTWIN_REMINDER_SECRET` on the site, the box is hidden.

## One-off setup

1. Apply the migrations to your Supabase project (`supabase db push`, see
   `docs/SUPABASE.md`); one of them adds the `reminders` table.
2. Generate a reminder secret, a long random string such as the output of
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`, and set it with the
   other settings above for both the site and the job.
3. Redeploy the site, so it reads the reminder secret.
