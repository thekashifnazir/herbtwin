# Pre-registration: the trusted-page check, round 7, real pages for the action we advise (21 Oct 2026)

Committed before any search or model call for this round.

## Why

The trusted-page quote (#297, passed round 6: 0/191 false agrees) showed **0 quotes in 12
answers** on the 6 judge sample photos (`data/eval/reports/2026-10-21-trusted-hit-rate.json`).

- The cause is that the search ran before the advice was known ("basil care October"), so
  Tavily's snippets were page introductions.
- Round 6 shows the same thing: 65% of the sentences read named no action.
- A 4-search probe with the action in the query found a sentence on our action on every
  page, and 1 agree.

The change adds agrees, so it may not ship on round 6's result. Kash chose to fix it and run
a blind round (21 Oct, relayed by the integrator: "377 yes let's fix it would rather have
working in there / yes blind run!"). If this round fails, the app keeps round 6's check
unchanged.

## What is frozen

- **Product code:** `src/herbtwin` at the commit named as `FROZEN` in
  `scripts/trusted_realpage_r7.py`. That commit is the parent of the one that adds this
  file. The harness refuses to collect or score if `git diff FROZEN -- src/herbtwin` is
  not empty.
- **The change under test** (`stages/trusted_page.py`, `pipeline.decide`):
  - The search runs once the advisors have decided.
  - The query is `trusted_page.query`. For a checked action it is the plant, the problem
    (for treat-or-remove only), and the action's words: watering, overwatering, winter
    protection, sunny position, cutting back, control.
  - `pick` reads only the sentences that `trusted_check.could_agree` accepts, meaning they
    name one of our actions in decide's own words. It takes at most 6, from the first
    trusted page about the plant that has any.
- **The reader:** Nemotron 3 Ultra (`nvidia/Nemotron-3-Ultra-550b-a55b`), thinking off,
  prompt E0, then the condition pass, at temperature 0. This is `trusted_page._read`,
  unchanged.
- **The decision:** `trusted_check.decide`, unchanged since round 6.

## Sampling (fixed now, before any search)

- **Answer states:** round 6's 64 states, in round 6's order (`STATES`, copied unchanged).
  They cover 14 outdoor herbs, the 6 checked actions, and problems from the app's own list.
  They were fixed on 19 Oct, before any round-7 idea existed.
- **What each state knows:** October, outdoors, and round 6's `WEATHER` per action.
- **Search:** one per unique query, using the product's round-7 query. That is at most 64
  Tavily searches, on trusted sites only.
- **Page and sentences:** the product's own `pick`, with `about_the_plant` as round 6.
- **Items:** each picked sentence becomes two items with the same plant, action, problem,
  pot or bed, and forecast:
  - **soil as fixed:** the state with round 6's `WEATHER`;
  - **soil not known:** the same state, but with no finger test and no soil visible. This
    is the common live case.

  A sentence may be met again under another state. Each (sentence, state) pair is one item.
- **Stop rule:** states are taken in order until there are at least **300 items and 150
  unique sentences**, or 64 searches, or the list runs out. The set is then fixed:
  `data/eval/sets/trusted_realpage_r7.jsonl`, with the raw picks in `…_searches.json`.
  - Why 300: about 80% are expected to be negatives, giving about 240.
  - With 1 false agree, about 200 negatives keep the Wilson upper bound at 3% or below.

## Labels (blind)

- The labellers see only `data/eval/sets/trusted_realpage_r7_items.jsonl`. Each item has:
  the plant, the month, our advice in plain words, what we know (pot or bed, soil or "not
  known", forecast, the problem found), and the page's sentence. They see **no model
  output**. They are **not this session**: the integrator sends fresh subagents that read
  only that file, with round 6's strict guide: does this sentence, on its own, tell the
  gardener to do our advice for this plant now, given what we know? Unsure means no.
- The labels are committed unchanged, with their sha256, to
  `data/eval/labels/2026-10-21-realpage-r7-blind.jsonl` before scoring.

## Scoring (once)

- `score` reads each unique (sentence, plant) once with the reader above, and decides each
  item with `decide`. It refuses a second run.
- **The bar (as round 6).** False agrees are items the code agrees on and the blind label
  says no, over all blind-negative items.
  - The round **PASSES** if the Wilson 95% upper bound on that rate is **≤ 3%**.
  - It is **INCONCLUSIVE** if there are fewer than 125 blind negatives. That does not pass.
- **Recall target: 50%** (agrees over blind positives), reported with its Wilson interval.
  It is not a bar: a quote is extra, so a low recall cannot make a quote wrong. If recall
  is under 50%, the report says the target was missed. The ship decision then goes to Kash
  and the integrator, and does not follow automatically from a PASS.
- **Reported, with no bar:**
  - each half (soil as fixed, soil not known) on its own: negatives, false agrees and
    their Wilson bound, recall;
  - each false agree's sentence;
  - failed reads;
  - read latency p50 and p95;
  - the money spent.
- **After scoring, and only if PASS:** `scripts/trusted_hit_rate.py` on the 6 judge
  samples (2 reads each, about $0.06). It reports the product's quote rate, with no bar.
- **Cost cap:** $0.50 of Token Factory for scoring (estimate about $0.20), and 64 Tavily
  credits for collection. A run that hits a cap stops and is reported as incomplete.

## Known limits

- **One month only:** October, as the demo.
- **One labeller pool.** The integrator's labellers are blind to model output, but their
  guide spells out the strict reading used since round 4 (disclosed then as now).
- **Correlated items.** Every sentence is in at least two items, so items are not
  independent. The bar is per item, as in round 6. The halves and the unique-sentence count
  are reported beside it.
- **Synthetic states.** These are not live answers: the action is fixed, not decided by
  the advisors. Live, the advisors' action and the page's sentence are less likely to
  clash than they are here.
