# Pre-registration: the trusted-page check, round 4 (19 Oct 2026)

Round 3 (`2026-10-19-trusted-extract.md`) failed its one test run: 9/328 false agrees
against blind labels, with a Wilson upper bound of 5.1%. Of those 9:
- 3 were model errors: a fact was read as an instruction.
- 6 were the blind labeller reading more strictly than our rules.

Kash said to keep going, using option 1: write the stricter reading into the rules,
choose on DEV only, then score once on a fresh TEST set that a new blind labeller labels.

This file has two parts:
- **Part 1** is committed before any round-4 model call.
- **Part 2** is added after the DEV run, before the new test set is built and before any
  test label is seen.

## Part 1: before any call

### What changed (code, DEV-only evidence)

Changes in `stages/trusted_check.py`:
- **Strength and plant-quality words → unsure.** A strength word, or a quality of the
  plant that the state can't confirm, makes the check unsure. Strength words: heavy, hard,
  severe, harsh, sharp, bitter, very, extreme, torrential. Plant qualities: leggy, young,
  established, mature, woody, old, newly, pale, straggly, overgrown.
  - Code reads these from the sentence itself as well as from the form.
  - "Prolonged" is not a strength word: the labeller counted "prolonged dry weather" as
    met by a dry spell.
- **Pots vs ground.** "Beds", "borders" or "open ground" when the plant is in a pot is
  unsure. So is "pots", "containers" or "tubs" when it is in the ground, or when we don't
  know which.
- **New actions that never match ours:**
  - `water_less`: water less, sparingly, keep just moist, let it dry between waterings.
    It never matches "hold off watering".
  - `deadhead` and `thin`: neither matches "cut back".
- **Seasons with early/mid/late** narrow to one month ("late autumn" is November).
- **Groups:** "tender herbs" no longer includes coriander.
- **Treat or remove** agrees only if the sentence names the problem we found.
- **New condition kind** `plant_trait`; it is never checkable.

Changes in the extractor prompt (`stages/trusted_extract.py`, E0 and E1):
- the new actions;
- condition values keep the sentence's own words, strength words included;
- what an action guards against or targets counts as a condition;
- pots and beds become container conditions;
- E0 says "a sentence saying what an action does or causes is a description, not an
  instruction";
- E1 adds 4 fresh worked examples: two fact-vs-instruction pairs, a strength word, and
  water_less.

### DEV (`data/eval/sets/trusted_judge_v5_dev.jsonl`)

- sha256 `6d720e8d52e0de5ca643c2031da573faca2333fa867034171d360b90ed963fd2`, built by
  `scripts/build_judge_v5.py dev`.
- Contents: everything round 3 has spent.
  - **v4 TEST**, with devpost-submission's blind labels as gold. Labels:
    `data/eval/labels/2026-10-19-v4-test-blind.jsonl`, sha256 `c872bb81…1693`. This set
    is no longer held out.
  - **v4 DEV**, with our labels re-read the strict way.
  - **The red team**, as its own split.
- **dev:** 486 items, 177 sentences, 414 negatives, 72 positives.
- **redteam:** 16 items, 11 negatives.
- **Rule check with hand-written forms:** 0/414 false agrees on dev and 0/11 on the red
  team. It differs from the gold only on 2 positives, so recall drops but nothing wrongly
  agrees:
  - "Leave chives alone…": the rule never agrees on "leave it".
  - "Water mint in pots more often than in the ground.": the sentence names both pots and
    ground.

### Stage A: DEV only (`HERBTWIN_ROUND=4 scripts/trusted_extract_grid.py dev`)

- **Grid:** Super-VL E0, Super-VL E1, Super E0, Ultra E0, Nano E0, all with thinking off
  and temperature 0.
  - Dropped to fit the budget: Super E1 and Ultra E1 (in round 3, neither beat its E0).
  - Dropped: Stage 3 (in round 3, it cut recall without cutting false agrees).
- **Recorded per config:** false agrees vs the DEV gold (Wilson 95%, by kind); recall;
  Stage-1 field accuracy; latency p50 and p95; $ per answer; forms that failed to parse.
- **Selection rule (unchanged):**
  - Eligible: dev recall ≥ 50% and p95 ≤ 4 s.
  - Pick the lowest dev false-agree rate; ties go to fewer stages, then the cheaper config.
  - If none is eligible, stop.
- **Red team:** the selected config runs the red-team split. Any false agree there blocks
  shipping.
- **Rule fixes after the DEV run:**
  - Allowed only from DEV evidence, before Part 2 is committed.
  - Any such fix re-runs the selected config on DEV, and Part 2 reports it.
  - After Part 2, the code and prompt are frozen until the test run.

### Stage B: TEST once (`HERBTWIN_ROUND=4 … test <config> <labels>`)

- **The test set is fresh:** `data/eval/sets/trusted_judge_v5_test.jsonl`.
  - **Sentences:** 160, written by a fresh agent that was told not to read the checker's
    code, prompts or pre-registrations, to quotas fixed in its brief.
  - **Disjoint:** the builder refuses any sentence shared with v1, v2, v4 (every split) or
    the extractor's examples.
  - **Unopened:** it is in the scratchpad, and I have not opened it.
  - **Sequence:** after Part 2, I add states and my own labels, send the items to the
    integrator without labels or forms, and a NEW blind labeller labels them.
  - **Size:** at least 300 negatives under my reading. If the blind labels give fewer than
    300 negatives, the result is reported as is, with its interval.
- **Primary gold:** the new blind labeller's labels, handed over only after Part 2 is
  committed.
- **Secondary gold:** my labels. Kappa between the two labellers is reported, with every
  item where they differ.
- **The bar (primary gold), unchanged:**
  - Wilson 95% upper bound on test false agrees ≤ 3%;
  - AND recall ≥ 50%.
- **Ships only if:** it passes the bar AND the red team is clean.
- **If it fails:** report and stop.

### Budget

At most $0.50 for round 4, DEV and TEST together. The DEV run stops at $0.45.

## Part 2: after DEV, before the test set is built (any test label unseen)

DEV run: `data/eval/reports/2026-10-19-trusted-extract-r4-dev.json`. Spent $0.321, more
than the $0.27 estimate.

| config | dev false agrees (of 414) | Wilson 95% upper | recall | p95 |
| --- | --- | --- | --- | --- |
| super-vl+E0 | 0 | 0.9% | 48.6% (ineligible) | 0.92 s |
| **super-vl+E1** | **0** | **0.9%** | **58.3%** | **0.91 s** |
| super+E0 | 7 | 3.5% | 58.3% | 1.64 s |
| ultra+E0 | 3 | 2.1% | 68.1% | 1.05 s |
| nano+E0 | 6 | 3.1% | 56.9% | 1.13 s |

- **Selected by the rule: super-vl+E1** (Nemotron 3.5 Super-VL, the prompt with worked
  examples). On the red-team split it made 0/11 false agrees and found 3 of 5 positives.
- **No rule fixes** after the DEV run. None of the selected config's errors called for
  one, so nothing was re-run.
  - Other configs' false agrees, for the record: "Pinching out encourages side shoots."
    read as an instruction (Super, Ultra); a heading, "Watering basil in pots" (Super);
    "Thyme is at its best in full sun." (Super); and condition or plant misses (Nano).
- **Frozen for the test run:** the code and prompts at commit 08609ac
  (`stages/trusted_check.py`, `stages/trusted_extract.py`). This part-2 commit changes
  only this file and the DEV report.
- **Test budget left:** $0.50 − $0.32 = $0.18. The selected config costs about $0.0004
  per sentence, so about $0.07 for 160 sentences.
