# Pre-registration: the trusted-page check, round 6, real pages (19 Oct 2026)

Committed before any search or model call for this round.

## Why

Round 5 passed its bar on written test sentences: 4/435 false agrees, Wilson upper 2.3%,
recall 81.5%. On live Tavily pages (PR #297), the check then quoted two things it should not:

- two list lines glued into one sentence;
- "Check rosemary plants regularly for rosemary beetle." for "treat it or remove the affected parts".

A probe found two more misreads that the rules then allowed:

- whole plants dug up, counted as removing the affected parts;
- "ventilate the greenhouse", read as protecting from cold.

Each was fixed with code that can only remove agrees (the PR lists them). There were about 3
misreads in about 25 live sentences, and round 5 cannot speak to that rate. This round
measures the false-agree rate on the sentences the product actually reads. The integrator
decided that #297 merges only if this round passes. If it fails, the app ships without
quotes and the round is reported.

## What is frozen

- **Product code:** `src/herbtwin` at **72c23bf**. The harness (`scripts/trusted_realpage.py`)
  refuses to collect or score if `git diff 72c23bf -- src/herbtwin` is not empty.
- **The reader:** Nemotron 3 Ultra (`nvidia/Nemotron-3-Ultra-550b-a55b`), thinking off,
  prompt E0, then the condition pass, at temperature 0. This is the product's
  `trusted_page._read`.
- **The decision:** `trusted_check.decide` at 72c23bf. This includes every post-test rule
  (pinch out, each action in its own words, whole plants), as it ships.

## Sampling (fixed now, before any search)

- **Answer states:** 64 states, listed in order in `STATES` in the harness. Each state is a
  herb, a problem or none, our action, and pot or ground.
  - They cover 14 outdoor herbs the app knows: basil, mint, rosemary, sage, thyme, parsley,
    chives, coriander, oregano, tarragon, lemon balm, bay, dill and garlic chives.
  - They cover the 6 actions the check is tested on: water, hold off, shelter, move to
    light, cut back, and treat or remove.
  - Problems come from the app's own problem list for each herb.
  - The order is round robin: each herb's care, then its problems, then a second care action.
- **What each state knows:** October, outdoors, and a forecast and soil fixed per action in
  `WEATHER`:
  - water: dry soil, no rain;
  - hold off: wet soil, rain;
  - shelter: a cold night ahead;
  - the rest: moist soil, rain, no cold.
- **Search:** one per unique query, using the product's own query, `"{plant} {problem or
  'care'} October"`. That gives at most 44 Tavily searches. Results come from Tavily, on
  trusted sites only.
- **Page and sentences:** the product's own `trusted_page.pick`.
  - The page is the first trusted page about the plant (`about_the_plant`) that has whole
    sentences.
  - It is read line by line. Lead-ins, glued words, fragments and over-long sentences are
    left out.
  - At most 6 sentences are taken from a page.
- **Items:** one per (sentence, action) pair. Every sentence of a state's page is paired
  with that state, and a pair already taken is skipped. The same page can therefore be met
  again under another action. Items are labelled and scored independently, and both the
  unique-sentence count and the item count are reported.
- **Stop rule:** states are taken in order until there are at least **220 items and 150
  unique sentences**, or until the list runs out. The set is then fixed:
  `data/eval/sets/trusted_realpage_r6.jsonl`, with the raw picks in `…_searches.json`.

## Labels (blind)

- The labellers see only `data/eval/sets/trusted_realpage_r6_items.jsonl`. Each item has:
  the plant, the month, our advice in plain words, what we know (pot or bed, soil,
  forecast, the problem found), and the page's sentence. They see **no model output**.
- The integrator labels with fresh subagents that read only that file, as in rounds 4 and
  5, with the same strict guide: does this sentence, on its own, tell the gardener to do
  our advice for this plant now, given what we know? Unsure means no.
- The labels are committed to `data/eval/labels/2026-10-19-realpage-r6-blind.jsonl` before
  scoring.

## Scoring (once)

- `score` reads each unique (sentence, plant) once with the reader above, and decides each
  item with `decide`. It refuses a second run.
- **The bar.** False agrees are items the code agrees on and the blind label says no,
  counted over all blind-negative items. The round **PASSES** if the Wilson 95% upper bound
  on that rate is **≤ 3%**. It is **INCONCLUSIVE** if there are fewer than 125 blind
  negatives, and that counts as not passing.
  - With 0 false agrees, about 125 negatives clear 3%.
  - With 1 false agree, about 200 negatives are needed. This is why the target is 220 items.
- **Reported, with no bar:**
  - recall, which is agrees over blind positives, with its Wilson interval;
  - each false agree's sentence;
  - failed reads;
  - latency p50 and p95;
  - the money spent.
- **Cost cap:** $1.00 of Token Factory for scoring. A run that hits the cap stops and is
  reported as incomplete.

## Known limits

- **One month only.** Every state is October, matching the live demo.
- **One labeller pool.** The integrator's labellers are blind to model output, but their
  guide spells out the strict reading used since round 4 (disclosed then as now).
- **Correlated items.** Items that share a sentence are not independent. The bar is
  computed per item, as pre-registered here. Unique sentences are reported beside it.
