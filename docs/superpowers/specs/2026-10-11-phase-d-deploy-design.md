# Phase D: deploy, design spec

Agreed with Kash on 7 and 11 Oct 2026, section by section. Roadmap:
the private working repo's `2026-10-04-roadmap.md` (phase D, 19 to 23 Oct). Phase C spec:
`docs/superpowers/specs/2026-10-06-phase-c-follow-up-and-learn-design.md`. Decisions are
numbered from D56 (D47 to D55 live in the phase C spec and the handoff).

## 1. Intent

Phases A to C built the app on Kash's Mac. Phase D puts it **on a public address that
stays up until judging ends (15 Dec 2026)**, for judges and the people Kash shares it
with, without a cost surprise; then adds the two pieces that need a live site: re-photo
reminder emails and a lasting trace of what the live site did.

**Audience (A, 7 Oct):** judges plus people Kash shares the link with. Open sign-up, a
generous daily cap on photo reads, and a judges' code that skips the cap (the rules ask
for free access "without any restriction" for judges until 15 Dec, and a private site
must give them credentials).

**In scope:** the live site (D1a streaming, D1b go live); LangSmith tracing (D3);
reminder emails on Nebius (D2); a demo dry run and judges' notes (D4).

**Out of scope:** the Nemotron vision GPU test on Nebius AI Cloud (own spec); Toloka
human ratings (side stream); indoor light (D55); generated images or growth prediction
(stretch, phase E at the earliest); more than one app instance.

**Success:**
- `https://herbtwin.kashifnazir.com` serves the app; a photo read through it shows a
  progress line per stage and lands on the answer, including reads longer than 125 s.
- The `run.app` address refuses requests that did not come through the Worker (except
  `/health`).
- The 11th photo read from one visitor in a day, and the 201st site-wide, get a polite
  "come back tomorrow" page; the same reads with the judges' code go through.
- At $16 of estimated live spend Kash gets one email; at $20 photo reads stop for
  everyone without the judges' code.
- A signed-in person who ticks "email me" gets one reminder in the check window, with a
  working one-click unsubscribe; a rerun of the daily job sends nothing twice.
- Every live photo read, refine and chat appears in LangSmith as one trace with no photo,
  email or coordinates in it; a scored follow-up shows as feedback on the original trace.
- With none of the new keys set, the app behaves as today apart from streaming, and every
  offline test passes.

## 2. Shape (D57)

One spec, five PRs, built in this order. Each gets its own plan, written just in time.

| PR | What | Why here |
|---|---|---|
| D1a | Stream the photo read | App only, testable locally; the riskiest change to existing code |
| D1b | Go live: image, Cloud Run, Worker + domain, edge secret, caps, judges' code, budget, privacy page, the private working repo's `deploy.sh` | Needs D1a (a silent 100 s read has only ~25 s of slack through the Worker) |
| D3 | LangSmith tracing + outcome feedback | Small; lets us watch the live site from its first day |
| D2 | Reminder emails, daily Nebius Serverless Job | Needs the live site for the links in the email |
| D4 | Demo dry run + `JUDGES.md` | Last, on the finished site |

## 3. Hosting (D56, carried from 7 Oct; probe 11 Oct)

- **Google Cloud Run**, project `YOUR_GCP_PROJECT` on a free-trial billing account, region
  `europe-west2` (London). Budget alert "herbtwin £20
  alert" on the project (credits excluded, emails at 50/90/100%).
- **Domain, option A:** a small Cloudflare Worker on `herbtwin.kashifnazir.com` forwards
  every request to the `run.app` address. Cloud Run's own domain mapping is preview-only
  and not offered in London; Firebase Hosting caps rewrites at 60 s.
- **Probe result (11 Oct, ~$0, deleted after):** through a `workers.dev` Worker in front
  of Cloud Run London, a 12 MB POST arrived whole (3.8 s); a 100 s silent request
  passed; a 130 s silent request got a 524 at ~125 s (direct to `run.app` it passed);
  headers sent at once then silence was cut at 125 s; **a byte every 10 s kept a 150 s
  request alive.** Cloudflare's limit is ~125 s of *idle* connection, not total time.
  Cold start was not measured (the probe image says nothing about ours).
- **Nebius stays in the build where it shows:** Token Factory for every model call (that
  alone meets "runs on Nebius", per the hackathon FAQ), the daily reminder job (D2), and
  the GPU test (own spec).

## 4. D1a: stream the photo read (D58)

Today `POST /analyse` reads the photo, runs the whole pipeline (about 100 s at worst) and
returns a full page, sending nothing meanwhile.

**Change:** `POST /analyse` validates the photo and the caps as now (errors are ordinary
pages, as today), then returns a **streamed HTML page**:

1. At once: the page head and a "Working on your photo" heading, padded to at least
   1 KB so browsers start drawing.
2. One line per stage as it finishes, in plain words: "Reading the photo... found
   basil", "Looking up how basil likes to grow", "Checking the weather where you are",
   "Thinking about what it needs" (the advisor panel), "Done".
3. While a stage is still working, an invisible keep-alive (an HTML comment) every 10 s.
4. At the end, a jump to where the answer lives: `location.replace(...)` plus a plain
   link for when scripts are off.

**Where the answer lives:** a new `GET /answers/{id}` renders the cached answer with the
same owner check refine already uses (signed in: the account, falling back to stored
history after the hour; signed out: the unguessable answer id, as refine already allows). Signed in, when the read needs "which plant is this?", the jump goes to a new
`GET /answers/{id}/plant` that shows the choice from `PendingChoices` without using it
up; the existing POST still makes the choice. A side benefit: reloading the answer no
longer re-posts the photo.

**How it is wired:** the pipeline gets an optional progress callback
(`on_stage(name, detail)`), called from `read_photo` and `decide` at stage boundaries;
`/analyse` runs the pipeline in a worker thread as now and turns callbacks into chunks
through a queue, with the 10 s keep-alive on queue timeout. No callback, no change: the
JSON `/api/analyse` route and the evals call the pipeline exactly as today.

**Failure mid-stream:** the status line has already gone out as 200, so a failure writes
a plain line ("That didn't work: <short reason>. Try again") with a link back to the
form, and logs the real exception. A partial failure the pipeline already tolerates
(for example the weather) is just another progress line and the answer still comes.

**Testing:** offline, with the scripted mock backend: stage lines arrive in order; a
stage held past 10 s by a fake clock produces a keep-alive; an exception produces the
error line and no jump; the jump target is the answer page (and the plant page for a
signed-in pending choice); `GET /answers/{id}` refuses another owner; `/api/analyse`
output is unchanged.

## 5. D1b: go live (D59 to D63)

**Image.** The existing Dockerfile, plus the four data folders every read needs
(`data/seasonal`, `data/outcomes`, `data/confidence`, `data/scoring`; without them the
first photo fails). Runtime writes (`traces.db`, `data/packs/`, `data/pages/`) go to
Cloud Run's in-memory disk and last until the next deploy.

**Cloud Run service `herbtwin` (D62).** `--min-instances 1 --max-instances 1`, request
timeout 300 s, 1 vCPU, 1 GiB (adjust from the first week's numbers). One instance
because answers, chat and plant choices live in process memory; always one running so
there is no wake-up wait and those caches survive between visits (about £10 a month
from the trial credit; measure and record it after the first week). CPU stays
request-billed: nothing may rely on running after a response has finished (see D3).

**Secrets.** Every key comes from Google Secret Manager as an environment variable,
never baked into the image. Already created: `herbtwin-nebius-api-key` (a separate live
Token Factory key, 11 Oct). Kash creates the rest the same way (clipboard piped into
`gcloud secrets create`, so values never appear in a session): Supabase secret key,
TinyFish, Tavily, Exa, OpenPlantBook id and secret, the edge secret, the judges' code,
and later LangSmith and Resend. Non-secret settings (backend, model ids,
`HERBTWIN_SITE_URL=https://herbtwin.kashifnazir.com`, `HERBTWIN_TAVILY_ENABLED=1`,
`HERBTWIN_SEARCH_ENABLED=1`) are plain environment variables. `HERBTWIN_HOME_LAT/LON`
stay unset.

**Worker (`edge/`, D63).** A few lines of JavaScript with its own `wrangler.toml`
(`custom_domain` on `herbtwin.kashifnazir.com`). For every request it forwards method,
path, body and headers to the `run.app` address, adding `X-Herbtwin-Edge: <edge secret>`
(a Worker secret) and `X-Herbtwin-Visitor-IP` from `CF-Connecting-IP`. It passes
responses through unbuffered. The app refuses any request without a matching edge header
(constant-time compare) with 403, except `/health`; with no edge secret configured
(local runs) the check is off. The visitor IP header is trusted only when the edge
header matched.

**Caps (D59).** Only photo reads count (`/analyse`, `/api/analyse`); refine and chat
already have per-answer limits.
- 200 photo reads a day site-wide; 10 a day per visitor. Days run on UK time.
- The visitor is the forwarded IP, stored as an HMAC with a server secret, never raw.
- Counts live in a new Supabase table (migration in D1b; Kash runs `supabase db push`),
  written only with the secret key, behind RLS like the others; increments go through a
  SQL function so a count cannot be lost between read and write.
- Over a cap: a short page ("The garden's had a busy day. Try again tomorrow") with
  status 429. The cap is checked before the stream starts.

**Live budget (D60).** The live site's Token Factory spend has its own budget, separate
from Kash's $25 development cap: **$20 to 15 Dec.** Each counted read adds an estimated
$0.005 (`HERBTWIN_READ_COST_USD`, from `docs/reference/model-speed-and-cost.md`) to a
running total in the same table. The first time the total reaches 80% ($16) the app
emails Kash once through Resend; at 100% photo reads stop with a polite page for anyone
without the judges' code. D4 checks the estimate against the Token Factory dashboard and
corrects the per-read figure if it is off.

**Judges' code (D59).** A `/judge` page takes the code (`HERBTWIN_JUDGE_CODE`), compares
it in constant time and sets a signed, HTTP-only cookie for 60 days. With it, the caps
and the budget stop are skipped. A wrong code gets the same page back with "That code
didn't work", and attempts per visitor are capped at 10 a day.

**Also in D1b.** The Supabase project's Site URL and allowed redirects gain the live
domain (localhost stays), done in Chrome with Kash watching. A `/privacy` page, linked
in the footer: what is stored (signed-in photos and history in Supabase; emails sent by
Resend; model calls processed by Nebius Token Factory; later, traces in LangSmith) and
how to delete an account.

**Releases (D61): the private working repo's `deploy.sh`, run by Kash after each merge** (the private working repo's `deploy.sh`).
It refuses unless the checkout is `main`, clean and equal to `origin/main`; then
`gcloud run deploy --source .` with the settings above, `npx wrangler deploy` in
`edge/`, and a live check through the domain: `/health`, then one real photo read of a
bundled public sample photo with the judges' code (about $0.005), which must stream and
land on an answer. It prints the deployed revision and the time from deploy to first
answer.

**Testing:** offline: edge header present / missing / wrong / unset; visitor IP ignored
without the edge header; caps at 10 and 200 with a fake clock and fake store, including
the UK day boundary; budget warn once at 80% and stop at 100%; judges' cookie skips both
and a tampered cookie does not; `/privacy` renders. Supabase (local, `pytest -m
supabase`): the migration, its RLS and the increment function. Live: the private working repo's `deploy.sh`'s
check.

## 6. D3: LangSmith tracing (D64)

- **Traces:** each photo read is one trace with a child step per stage (observe,
  research, environment, twin, advise x3, confidence) and the model calls inside, each
  with model id, tokens, time and estimated cost. Refine and chat are traces of their
  own. Project names from `HERBTWIN_LANGSMITH_PROJECT` (`herbtwin-live` on Cloud Run,
  `herbtwin-dev` locally).
- **Why live needs it:** `traces.db` sits on Cloud Run's in-memory disk and is wiped by
  every deploy; LangSmith is the lasting record.
- **Privacy:** image parts of prompts become `<image omitted>`; no email addresses; no
  latitude or longitude (place names only). A test feeds a record holding all three and
  checks none reaches the sink.
- **Safe by design:** on only when `HERBTWIN_LANGSMITH_API_KEY` is set. It hangs off the
  existing `tracing.on_record` hook. Sending is in the background, and a LangSmith
  failure is logged, never raised. Because Cloud Run bills CPU per request, pending
  traces are flushed before the response ends (in the streamed page, before the final
  jump), with a short timeout.
- **Outcome feedback:** the original read's trace id is stored with the answer in the
  plant history (a column added in D3's migration). When a later "Did you do it?"
  comparison scores that advice (C2), the score is attached to the original trace as
  LangSmith feedback (`outcome`: improved / no clear change / worse / can't tell). The
  traces then record which advice worked.
- The `langsmith` package is added with `uv add`, pinned.
- **Free tier:** 5,000 traces a month. The daily caps alone would allow about 6,000
  photo reads a month, but the $20 budget stops reads at about 4,000 in total, and real
  use should be far below either.

## 7. D2: reminder emails on Nebius (D65)

- **Opt-in:** on a signed-in plant's answer, a box "Email me when it's time to check
  again", unticked by default, saved against that answer. Signed-out answers have no
  email to send to, so no box.
- **When:** halfway through the main action's check window (the same window "Did you do
  it?" uses: 1 to 7 days for watering, 3 to 21 days by default), rounded down to a whole
  day, so at least half the window is left to take the photo. At most one email per
  answer, and none if a follow-up photo already arrived.
- **Email:** "Time to check your basil. On 12 Oct you were told to <action>. A new photo
  shows whether it worked." A link to the site and a one-click unsubscribe (a signed
  token; `GET /reminders/unsubscribe` turns that answer's reminder off and says so).
  Sent through Resend from Kash's verified domain, with a plain-text part.
- **The job:** the same Docker image with another command, `python -m
  herbtwin.reminders`. It reads the reminders due today from Supabase (secret key), sends
  each with Resend's idempotency key set to the reminder id, then marks it sent. A rerun
  the same day sends nothing twice. One failed send is logged and the rest continue; the
  job exits non-zero if any failed, so the run shows red.
- **Runs on Nebius, no fallback (Kash, 11 Oct: "we have enough credit and helps the
  story").** A daily GitHub Actions workflow (cron, plus a manual "run now" button)
  starts a Nebius Serverless Job from the image, because Nebius jobs have no schedule of
  their own. The image is pushed to Nebius Container Registry. The job's keys come from
  Nebius's secret store if jobs can read it, else from GitHub secrets passed at creation
  and never echoed. Cost: cents a day from the $125 AI Cloud credit. Step 0 of the D2
  plan is a throwaway probe of the Nebius job API and the CLI auth from GitHub Actions,
  because neither has been tried yet.
- **Kash adds at build time:** a Resend sending key (domain-scoped), a Nebius service
  account key in GitHub's secret settings, and `supabase db push` for the reminders
  migration.
- **Testing:** offline: the due-date rule per action type; already-sent and
  already-followed-up answers are skipped; an idempotent rerun; one failed send doesn't
  stop the rest and sets the exit code; the unsubscribe token can't be forged; no box
  for signed-out answers. Supabase (local): the migration and RLS. Live: one forced
  reminder to a test account in D4.

## 8. D4: demo dry run and judges' notes (D66)

- A scripted run on the live site: a first visit, sign-up by emailed link, five photo
  reads (Kash's garden and public photos), refine, chat, "Did you do it?", a forced
  reminder to a test account, the judges' code, and the caps page. Record each read's
  time, the cold start after a deploy, the Token Factory dashboard against the budget
  estimate, and what feels rough; fix the rough parts in small PRs.
- `JUDGES.md` at the repo root, linked from the README: the address, the judges' code
  (given in the submission form, not in the repo), what to try in five minutes, sample
  photos to download, how long a read takes and why it streams, and known limits.

## 9. Error handling

- Every new user-facing failure is a short plain page or line with what to do next; the
  real exception is logged; nothing is swallowed.
- A Supabase outage on the cap check: photo reads are allowed and the failure is logged
  (the budget estimate may undercount for that time; Token Factory's dashboard is the
  backstop).
- A Resend failure on the 80% warning: logged and retried on the next counted read until
  one is sent.
- LangSmith failures never touch a request (section 6).

## 10. Risks and what would change the plan

- **Cloudflare compressing or buffering `text/html` through the Worker** would hide the
  progress lines. The probe streamed `text/plain`; D1b's live check streams real HTML.
  If it buffers, send `Cache-Control: no-transform` and an identity encoding from the
  app.
- **The min-instance cost** could be higher than estimated. Measure after a week; if it
  is over £15 a month, drop to `--min-instances 0` and accept a cold start.
- **The Nebius job API from GitHub Actions** is untried (D2 step 0).
- **The per-read cost estimate** may drift from real spend (prompt changes, search
  credits). D4 recalibrates it.

## 11. Decisions

| # | Decision | Kash |
|---|---|---|
| D56 | Live site on Google Cloud Run in a new trial-billed project; Nebius shows through Token Factory, the reminder job and the GPU test | "Let's do it with Google Cloud" (7 Oct) |
| D57 | Phase D as D1a, D1b, D3, D2, D4, in that order (D1 to D4 confirmed; D1 split in two) | "sure", "yes" |
| D58 | The photo read streams a progress line per stage plus a keep-alive every 10 s, then jumps to `GET /answers/{id}`; no page polling | "sure", "yep" |
| D59 | Caps: 200 photo reads a day site-wide, 10 per visitor; a judges' code skips both | "yes" |
| D60 | Live Token Factory spend has its own $20 budget to 15 Dec: email at 80%, photo reads stop at 100% except with the judges' code | "yes and own budget", "sure sounds good" |
| D61 | Releases by the private working repo's `deploy.sh`, run by Kash after each merge; no deploy-on-merge | "sure go with what you recommend" |
| D62 | One Cloud Run instance, always running (`--min-instances 1 --max-instances 1`) | "yep" (section 2) |
| D63 | Worker adds an edge secret and the visitor IP; the app refuses requests without the secret; all counting in the app and Supabase | "yep" (section 2) |
| D64 | LangSmith traces for reads, refine and chat, redacted, flushed before the response ends; C2 scores attached as feedback | "sounds good" |
| D65 | Reminders: opt-in per answer, a daily Nebius Serverless Job started by GitHub Actions, Resend; no Cloud Scheduler fallback | "let's keep it on nebius" |
| D66 | D4: scripted dry run on the live site, then `JUDGES.md` | "yes" |

Details not put to Kash, chosen by the session and open to change: the progress
wording; the 1 KB padding; `GET /answers/{id}/plant`; 1 vCPU and 1 GiB; UK-time days;
the HMAC on visitor IPs; the 60-day judges' cookie and the 10 wrong-code attempts; the
$0.005 per-read estimate; allowing reads when Supabase is down; LangSmith project names;
**the reminder at the window's halfway point** (section 3 of the chat said "at the end
of the window", which would leave no time to take the photo); the Resend idempotency
key; the `edge/` folder name.
