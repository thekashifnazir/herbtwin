# Pre-registration: the trusted-page check, round 5 (19 Oct 2026)

**Round 4** (`2026-10-19-trusted-extract-r4.md`) passed on safety but failed on recall in
its one test run (blind gold):

| | Round 4 result | Bar | |
| --- | --- | --- | --- |
| False agrees | 3/369, Wilson upper 2.4% | ≤ 3% | passed |
| Recall | 20/44 = 45.5% | ≥ 50% | failed |

- With perfect forms the rules would have found 39 of the 44 positives. The loss came
  from Stage-1 conditions: only 41% of sentences had the right condition kinds.
- Kash: "keep going". The aim is recall, without giving back safety.

Two parts, as in round 4:
- **Part 1** is committed before any round-5 model call.
- **Part 2** is added after the DEV run, before the v6 test sentences are opened and
  before any test label is seen. The writer agent has already written them, unread, to
  the scratchpad.

## Part 1: before any call

### Rule changes (`stages/trusted_check.py`)

- **More strength words.** "Bone dry", "parched", "soggy" and "waterlogged" now count, so
  the state can't confirm them and the answer is unsure.
- **Whole-plant removal is its own action, `remove_plant`.** "Pull it up and bin it" is
  not "remove the affected parts".
  - It backs only a no-cure "remove the plant" advice. The app gives no such advice yet,
    so today it never agrees.
  - Like treat-or-remove, it must name the problem we found.
- **Extractor prompt.** The action list gains `remove_plant`. Nothing else in E0 or E1
  changes, so any gain from the second pass can be credited to that pass.
- **New condition-only second pass** (`trusted_extract.with_conditions`). It runs only
  when the first pass found at least one condition, and re-reads just the conditions.
  - The prompt lists each condition kind with examples.
  - It also says what is NOT a condition: how, how often, how much and why.
  - Any trouble gives None, which means unsure.

### DEV (`data/eval/sets/trusted_judge_v6_dev.jsonl`, `scripts/build_judge_v6.py dev`)

Round 4's DEV, re-read the round-5 way: the whole-plant sentences get the `remove_plant`
hand form, and "Bin basil plants that show downy mildew." becomes a no in my labels.
- The blind labels on the old v4 test stay unchanged, so where the stricter rules
  disagree with them, the cost is recall (3 positives), never a false agree.
- **dev:** 486 items, 415 negatives, 71 positives.
- **redteam:** 16 items, 11 negatives.
- With hand-written forms: 0/415 false agrees, recall 93%.
- The spent v5 test is not used in round 5.

### Stage A: DEV only (`HERBTWIN_ROUND=5 scripts/trusted_extract_grid.py dev`)

**Configs:**
- (baseline) `super-vl+E1`: round 4's selection, re-run under the round-5 rules;
- (a) `ultra+E0`: Ultra as the extractor. It uses E0 because in round 3 E1 did no better
  for Ultra, and Ultra is the expensive model;
- (b) `super-vl+E1+cond:super-vl` and `super-vl+E1+cond:ultra`: Super-VL forms plus the
  condition pass;
- (c) `ultra+E0+cond:ultra`: both.

**Recorded per config:**
- false agrees with Wilson 95%, by kind;
- recall;
- condition accuracy after Stage 1 and after the condition pass (`fields_stage1`,
  `fields`);
- latency p50 and p95, counting both passes;
- $ per answer.

Stage-1 forms are shared between configs within the run.

**Selection rule (round 5, from the integrator):**
- Eligible: DEV false agrees with Wilson upper ≤ 3%, and p95 ≤ 4 s.
- Pick the **highest DEV recall**.
- Ties go to an NVIDIA config (every config is one), then the cheaper.
- If none is eligible, stop.

**Red team:** the selected config also runs the red-team split. Any false agree there
blocks shipping.

**Rule fixes after the DEV run:** allowed only from DEV evidence, and only before Part 2.
After Part 2, the code and prompts are frozen.

### Stage B: TEST once (`HERBTWIN_ROUND=5 … test <config> <labels>`)

- **Set:** fresh, `data/eval/sets/trusted_judge_v6_test.jsonl`.
  - 200 sentences from a new writer agent. It was told not to read the checker's code,
    prompts or pre-registrations.
  - Its brief weighted plain instructions of our actions (90 of 200) so that there are
    enough positives. The aim is ≥ 60.
  - The builder refuses any sentence shared with v1, v2, v4, v5 or the prompt examples.
- **Labels:** I add the states and my own labels after Part 2. A NEW blind labeller then
  labels the items, with the same guide as v5; the integrator discloses this, as in
  round 4.
- **Primary gold:** the blind labels. **Secondary:** mine. Kappa between them is
  reported.
- **The bar, unchanged:** Wilson 95% upper bound on false agrees ≤ 3%, AND recall ≥ 50%.
  It ships only if it passes the bar and the red team is clean.
- **Also reported:** condition accuracy per stage, latency and cost.
- **If it fails:** report and stop.

### Budget

About $0.50 for round 5 (inside Kash's standing $2-per-run rule).
- The DEV run stops at $0.32.
- The test costs about $0.10 for a Super-VL config and $0.22 for an Ultra config.

## Between the parts: the DEV run hit its cap (no change to the rules, configs or selection)

- **The first DEV run stopped at the $0.32 cap** after 3 of the 5 configs. It was partway
  through `super-vl+E1+cond:ultra`: Ultra's condition pass cost more than estimated.
- **The 3 finished configs** (each complete, kept in this commit's history):
  - `super-vl+E1`: 0/415 false agrees, recall 50.7%;
  - `ultra+E0`: 0/415, recall 66.2%;
  - `super-vl+E1+cond:super-vl`: 0/415, recall 63.4%.
- **Decision (the integrator, relaying Kash's standing $2-per-run rule):** finish the
  pre-registered grid, with **$1.00 for round 5**, DEV and test combined.
- **The rerun:** the whole grid runs again in one go, so every config comes from one run,
  with a $0.48 cap ($0.32 already spent).
  - Stage-1 forms are now saved to disk (`HERBTWIN_FORM_CACHE`), so a stopped run never
    pays for them twice.
  - The DEV report is now written after each config.
  - Selection uses the rerun's full report.

## Part 2: after DEV, before the v6 test sentences are opened (no test label seen)

DEV rerun: `data/eval/reports/2026-10-19-trusted-extract-r5-dev.json`, $0.41. Round 5
has spent $0.73 so far: $0.32 in the first run and $0.41 in the rerun.

Every config made 0/415 false agrees (Wilson upper 0.9%), so every one is eligible on
safety.

| config | recall | conditions right: after Stage 1 → final | p95 | $ per answer |
| --- | --- | --- | --- | --- |
| super-vl+E1 | 50.7% | 55% | 0.82 s | 0.00039 |
| ultra+E0 | 64.8% | 70% | 1.09 s | 0.00086 |
| super-vl+E1+cond:super-vl | 63.4% | 55% → 61% | 1.39 s | 0.00053 |
| super-vl+E1+cond:ultra | 64.8% | 55% → 64% | 1.47 s | 0.00086 |
| **ultra+E0+cond:ultra** | **71.8%** | **70% → 73%** | **1.90 s** | **0.00127** |

- **Selected by the rule: `ultra+E0+cond:ultra`** (Nemotron 3 Ultra extracts, then
  re-reads the conditions). On the red team it made 0/11 false agrees, recall 80%.
- **Recall gain:** the condition pass adds recall on top of either extractor, and Ultra
  plus its own pass is the best (+21 points over the baseline).
- **No rule fixes after DEV.** The code and prompts are frozen at 9e10b99. Later commits
  change only the runner's cache, the cap and this file.
- **Test budget:** $1.00 − $0.73 = $0.27. The test run's own cap is $0.27, about 200
  sentences at about $0.0013 each.
