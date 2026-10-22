# Pre-registration: the trusted-page check, round 8: whole pages, and a last gate with our advice in view (22 Oct 2026)

Committed before any search or model call for this round's set.

## Why

Round 7 (searching for the action we advise) **failed**. It had 4 false agrees in 205
blind negatives (upper bound 4.9%, against a 3% bar) and recall 0/11
(`data/eval/reports/2026-10-21-trusted-realpage-r7.json`).

- **The 4 false agrees** were two sentences, each counted twice:
  - a whole-plant cut, "cut the whole plant down to just above the base";
  - "Save the trimmings…".
- **The 11 misses** were mostly:
  - treating where only the page names the pest (4);
  - sentences the claim-blind form could not place (description vs instruction, a plant
    group, a hedge).

Kash chose to try again (22 Oct, relayed by the integrator: "Yes go fit it", meaning go
for it). Round 7's data is now tuning data. Every rule below was chosen on it, so this round
uses **new answer states** that no round has searched.

## What is frozen

- **Product code:** `src/herbtwin` at the commit named as `FROZEN` in
  `scripts/trusted_realpage_r8.py`. The harness refuses to collect or score if
  `git diff FROZEN -- src/herbtwin` is not empty.
- **The change under test:** round 7's, plus:
  1. **Whole pages:** the first 3 trusted pages about the plant are read whole with Tavily
     Extract, a problem's own page first. Sentences come from the page body with their
     headings; the snippet is the fallback.
  2. **Only sentences that could back this answer's action** are read
     (`could_agree(s, action)`), at most 6, from the first page that has any.
  3. **Two pruning rules** that can only remove agrees:
     - the nouns "cuttings / trimmings / clippings / prunings" are not "cut back";
     - a cut of the whole plant, or to the ground or base, is not a trim.
  4. **A page whose address names the problem** we found (`/rosemary-beetle`) counts as
     naming it for a treat-or-remove sentence (`trusted_page.on_page`). This rule adds
     agrees.
  5. **The last gate** (`stages/trusted_backs.py`):
     - for each sentence the code agrees with, Nemotron 3 Ultra (thinking off,
       temperature 0) sees our advice, what we know, the sentence and its heading;
     - it answers backs true or false;
     - a quote needs **both** the code and the gate. The gate can only remove agrees.
- **The reader:** as in rounds 5–7, Nemotron 3 Ultra, E0 then the condition pass.

## Sampling (fixed now, before any search)

- **Answer states:** 64 new states, listed in order in `STATES`.
  - 16 plants that rounds 6 and 7 never searched: lavender, strawberry, tomato, chilli,
    lettuce, kale, chard, fennel, marjoram, sorrel, lovage, chamomile, winter savory,
    hyssop, rocket and blueberry.
  - The 6 checked actions, and common UK problems for each plant.
  - The order is round robin: each plant's first care action, then a problem, then a
    second care action, then more problems and care.
- **What each state knows:** October, outdoors, and round 6's `WEATHER` per action.
- **Search:** one per unique query, using the product's round-8 reading. That is 1 search
  credit plus 1 Extract credit per state, so at most 128 Tavily credits.
- **Items:** each picked sentence becomes two items, as in round 7: soil as fixed, and soil
  not known.
- **Stop rule:** states are taken in order until there are at least **400 items and 200
  unique sentences**, or 64 searches, or the list runs out. The set is then fixed:
  `data/eval/sets/trusted_realpage_r8.jsonl`.

## Labels (blind)

- The labellers see only `data/eval/sets/trusted_realpage_r8_items.jsonl`, which has the
  same fields as round 7: plant, month, our advice, what we know, and the page's sentence.
  They see **no model output and no heading**: they judge the sentence on its own, as a
  reader of the quote would.
- The labellers are not this session: two fresh integrator subagents, with round 6's strict
  guide. The final label is yes only when both say yes. Their agreement and kappa are
  reported.
- The labels are committed unchanged, with their sha256, to
  `data/eval/labels/2026-10-22-realpage-r8-blind.jsonl` before scoring.

## Scoring (once)

- `score` reads each unique (sentence, plant) once. Each item is decided with `decide` on
  its page (`on_page`), and each code agree is put to the gate with that item's state. An
  item agrees only when both do. `score` refuses a second run.
- **The bar (as rounds 6–7).** False agrees over blind negatives.
  - The round **PASSES** if the Wilson 95% upper bound is **≤ 3%**.
  - It is **INCONCLUSIVE** below 125 blind negatives, and that does not pass.
- **Recall target: 50%**, reported with its Wilson interval. It is not a bar. If it is
  missed, the report says so, and the ship call goes to Kash and the integrator.
- **Reported, with no bar:**
  - the code alone, before the gate: false agrees and agrees;
  - each half (soil as fixed, soil not known);
  - each false agree's sentence;
  - failed reads;
  - latency;
  - money.
- **After scoring, only if PASS:** `scripts/trusted_hit_rate.py` on the 6 judge samples.
- **Cost cap:** $0.50 of Token Factory for scoring, and 128 Tavily credits for collection.

## Known limits

- **One month** (October). **One labeller pool**, with the strict guide disclosed since
  round 4.
- **Correlated items.** Every sentence is in two items.
- **The gate's prompt was written after round 7 failed.** It was checked only on 10 of
  round 7's states (a dev probe: it blocked planting-time watering and spraying), never on
  this set.
- **The labellers judge the sentence alone, but the gate also sees its heading.** A
  heading can only make the gate stricter in what it accepts. It is still a difference from
  what the labellers see, and it is disclosed.
