# Pre-registration: first-time users on the live site, Toloka (22 Oct 2026)

Committed before any worker sees the task and before any Toloka spend.

## Amendment, 23 Oct 2026 (before any worker, any data or any Toloka spend)

**One run, not a trial and a main run.** Kash, 23 Oct, relayed by the integrator: "it
normally takes a day right for people to do it so i will run out of time before credit can
we just change it so we just do one run". The Toloka credit may lapse around 25 Oct, and a
trial then a main run would need about two days of worker time.

- **The run:** 1 task, overlap **11**, on the same sample, at the same pay: $1.25 a task,
  $1.6667 with Toloka's 33%, so **$18.33** of the $20.40 balance. The forecast in Toloka's
  deploy window stays the binding number; if its maximum is over $18.40, the overlap comes
  down until it fits.
  Read on 23 Oct with overlap 11: $18.34 expected and maximum. The dataset is the one-row
  `site-study-trial-t01.json` already uploaded (task id t01, the same sample and site).
- **Superseded below:** the "Trial" section, the cost table's Trial 3 / Main run 8 rows,
  "the two runs together", the trial-and-main-run overlap line, and the 7-minute pay rule.
  The run is the single overlap-11 task above.
- **A broken task** (a field that will not save, a step nobody can follow, a site error) is
  judged ONLY from Q2 (reached the page), Q8 (free text) and the site's own log, never from
  the answers to Q3, Q5 or Q6. Only the rows of workers who hit the fault are dropped, and
  they are reported with what happened. If it breaks for every worker, the run is reported
  as failed, with no pass or fail on the bars.
- **Unchanged:** the task's ten questions, the scoring, the bars (P1 ≥ 70%, S1 ≥ 60%, S2 ≥
  70%; S3 to S6 reported), the two blind labellers, Wilson intervals, privacy, and raw
  answers off git. One answer per Toloka annotator id, as before.
- **The site does not change while workers are on it:** the integrator holds visible
  deploys for the run. The revision is still read from the site and recorded.

## Why

The story's "Not done yet" lists a beginner user test on the final site. Kash asked for
it, relayed by the integrator on 22 Oct: "can we get an idle session to start setting up
toloka to use last $20 for study of the website". This study uses the last of the Toloka
credit ($20.40). It replaces the advice-clarity run planned on the same credit
(the private working repo's `2026-10-21-judge-session-handoff.md` §4), which will not run.

The question: can a first-time visitor with no plant of their own get an answer, say what
it told them to do, find where the advice came from, and use the Ask box?

## What is fixed

- **Site:** https://herbtwin.kashifnazir.com/, live, at whatever revision is deployed when
  the run starts. The revision is read from the site and recorded with the results.
- **Sample:** every worker taps the same home sample, **Rosemary beetles**. It is a
  problem sample, so the page has a pest, sources and the Ask box to find. No location is
  typed, so the sample's own place, London, is used.
- **One headline a day.** A repeat of the same photo, place and day returns a stored copy
  of the first answer, with no model call (`src/herbtwin/replays.py`). So every worker on
  the same UK day sees the same headline.
- **The task** (Toloka pipeline "Site test 22 Oct - USE THIS ONE", one quorum node,
  built by a local script kept off git with the other Toloka files,
  `build_site_study.py` sha256 `817a1bfc624e69c0…f3f999`):
  1. Open the site, tap the sample, press "What does my plant need?".
  2. Did you get an answer page? (yes / limit / error / other; if no, what happened)
  3. In your own words: what did the website tell you to do?
  4. One thing you would check next.
  5. Where did the advice come from, and where on the page? Plus found it / not sure /
     couldn't find it.
  6. Ask one question in the Ask box. Write the question; say what happened.
  7. Clarity 1–5 and trust 1–5.
  8. The ONE thing that confused you most (free text, "nothing" allowed).
  9. Device; how many plants they look after.
  10. Last, so it cannot steer question 3: copy the page's big heading.
- **Privacy:** no names, emails or photos. The task says so twice and tells workers not to
  upload their own photos or type anything about themselves. Free text only. The site
  stores a visitor only as a keyed hash of the IP (`/privacy`).
- **Never** the judges' code. Workers use the public site under its normal visitor caps.

## Workers and money

Toloka's own prices, read in Kash's account on 22 Oct:
- the price per task is set by us, at least $0.40 for 120 s, which is $12 an hour;
- Toloka adds a fixed 33% commission;
- training is off, so there is no onboarding charge (it was $0.80 per new worker on 11 Oct).

| | Per worker | Workers | Cost |
| --- | --- | --- | --- |
| Pay for a 5-minute task: $1.25 ($15 an hour) | $1.25 + 33% = $1.67 | | |
| Trial | | 3 | $5.00 |
| Main run | | 8 | $13.33 |
| **Total** | | **11** | **$18.33** of $20.40, leaving $2.07 |

- **Why not 20 to 40.** That many workers in $18.40 would mean $0.46 to $0.92 each all in,
  so $0.35 to $0.69 of pay for 5 minutes. That is $4 to $8 an hour, below Toloka's own
  minimum of $12 an hour.
- **At Toloka's minimum,** $1.00 per task, the run would be 3 + 10 = 13 workers for $17.33.
  We pay $15 an hour instead, because the 11 Oct run took about twice its priced time.
- **The forecast in Toloka's deploy window is the binding number.** If its maximum is over
  $18.40 for the two runs together, the main run's overlap comes down until it fits.
- **The trial** is 1 task with overlap 3. The main run is 1 task with overlap 8, on the same
  sample. A quorum never gives one task to the same worker twice. Across the two runs, a
  repeat worker is told apart by Toloka's annotator id, and only their first answer counts.
- **If the trial's median time is over 7 minutes,** the main run's pay rises to $0.25 a
  minute of that median, and its overlap falls so the total stays within $18.40.
- **Site load:** at most about 11 photo reads. That is under the 10 per visitor IP and 200
  site-wide each day. The model cost is a few cents: one fresh read a day, then stored
  copies, plus about 11 short chats.

## Trial

- The trial runs first, with 3 workers.
- **If its rows show a broken task,** such as a field that will not save, a step nobody can
  follow, or a site error, the task is fixed before the main run. The trial rows are then
  reported apart and left out of the scores.
- **If the task is not changed,** the trial rows are pooled with the main run.
- Either way, the trial's times and confusions are reported.

## Scoring (once, after the main run)

**The reference headline** for a UK day is the heading the answer page showed that day for
the sample. It is the one most workers pasted in question 10; the replay rule makes them
the same. Any worker whose pasted heading differs is listed. This includes a heading copied
from the home page's example card, which is a different plant.

**Who is scored:**
- **In:** every worker who reached an answer page (Q2 = yes).
- **Reported apart:** workers who did not reach a page, with what happened. This is the
  reach rate, with no bar.
- **Out, and counted:** a worker whose free-text answers are all filler, such as 'ok' or
  'good', or copies of the task text.

**Labels:** two fresh subagents label each scored worker. Each sees only:
- the reference headline;
- the worker's answers to Q3, Q4, Q5 and Q6;
- the strict rules below.

A label is yes only when both say yes. Their agreement is reported.

| | Measure | Bar |
| --- | --- | --- |
| **P1** | **Right action:** Q3 names the same action as the reference headline (e.g. "pick the beetles off" for a remove-the-beetles headline). Copying the heading word for word counts. Naming a different action, or only the plant, does not. | **≥ 70%** |
| S1 | **Found the source:** Q5 names something the page shows about where the advice came from: the Sources line, a named site, the "A trusted page says the same" quote, the model named in "Decided by", or the "How we worked it out" fold. | ≥ 60% |
| S2 | **Used the Ask box:** Q6 = "It answered my question", with a real question written. | ≥ 70% |
| S3 | **Check next:** Q4 names something the page says to watch or check. | reported, no bar |
| S4 | **Clarity and trust:** medians and full counts, 1–5. | no bar |
| S5 | **Confusions:** Q8 coded into themes by one subagent. Each theme is given with its count and short paraphrases, never long quotes. | no bar |
| S6 | **Time:** median and range of seconds on task. | no bar |

Each measure is given as k of n with a Wilson 95% interval. With about 11 workers, the
interval on P1 is wide; at 8 of 11 it is roughly 43% to 90%. The bars are point-estimate
bars, and the write-up says how few workers there were.

**Raw answers stay off git.** Toloka owns the output, and Kash has a 30-day licence to use
it for internal evaluation. The raw export stays under `data/external/` (git-excluded).
Only aggregate numbers and paraphrased themes go in the repo or the story.

## Known limits

- **One sample, one month, one site revision.** A crowd of strangers is a proxy for first
  time users, not real gardeners.
- **No plant of their own,** so this tests understanding and finding things, not whether
  the advice works.
- **Workers are paid and know they are in a test,** so they may read more carefully than a
  real visitor.
- **About 11 workers.** This is a usability probe, not a rate.
