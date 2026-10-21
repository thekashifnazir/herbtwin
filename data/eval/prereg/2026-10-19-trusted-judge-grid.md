# Pre-registration: the two-stage judge search (19 Oct 2026)

Written and committed **before any grid call**. Kash chose option 3 (a bigger model and a
better prompt, plus "other models that make sense") after the first judge failed its bar
(`2026-10-19-trusted-judge.md`: Nano P0, 42/248 false agrees). Many tries on one set would
pick the luckiest, so the search runs on a DEV split and only the one config it selects
meets the held-out TEST split, once.

## The set: `data/eval/sets/trusted_judge_v2.jsonl` (sha256 a3f22434ba44d196…)

- **496 items: 359 gold negatives and 137 gold positives.**
  - v1's 338, unchanged;
  - 158 new: 36 conditions, 20 likings or needs, 20 other seasons, 20 what-others-do or general facts, 7 negations, 8 other plants, 41 instructions and 6 month-matched instructions, after duplicates.
- **Labels are author-made** (the nvidia session), under v1's rule. Kash was never asked for a care judgment.
- **Split:** stratified by (category, gold), seed 2026, 50/50.
  - **DEV: 254 items (184 negatives, 70 positives).**
  - **TEST: 242 items (175 negatives, 67 positives).**
  - The split is committed here. Test results are never looked at before Stage B.
- **Disclosed:** about half of v1's items fall in TEST. Their outcomes under Nano + P0 were seen in the first run (that config is in the grid but can't be selected: it failed recall). P1's rules and examples were written after seeing which **categories** failed, never from the items. P1's examples are fresh sentences, and a test checks none is in the set.

## Stage A: the grid, on DEV only

- **Models, all on Token Factory:**
  - NVIDIA: Nemotron 3 Nano, Nemotron 3.5 Lightning, Nemotron 3 Super, Nemotron 3.5 Super VL, Nemotron 3 Ultra (thinking off);
  - others: gpt-oss-120b (reasoning effort low, 400-token budget) and Qwen3-235B-A22B Instruct.
  - **Excluded after a 3-call probe:** DeepSeek V4.1 Flash timed out at 30 s on both thinking-off settings; GLM-5.3 Flash kept reasoning past 400 tokens with thinking off, returning no JSON.
- **Prompts** (`stages/trusted_judge.py`, hash aba97fb524a3):
  - P0: the current prompt;
  - P1: P0 plus the traps spelled out and 8 worked examples;
  - P2: the kind of each sentence first; the code takes a support only from a sentence the model itself called instruction_now.
- **21 base configs (7 × 3) at temperature 0, plus 2 combos:**
  - an AND-vote of the 2 best eligible base configs (both must support the same sentence);
  - 3-sample self-consistency at temperature 0.7 on the best eligible base config (supports if 2 of 3 do).
- **Recorded per config:** false agrees (with Wilson 95%, and per category), recall, latency p50/p95 (wall time per answer, 4 calls in parallel), and $ per answer from the catalog prices.

## Selection rule (fixed now)

Among configs with **dev recall ≥ 50% and p95 latency ≤ 4 s**, pick the **lowest dev false-agree rate**. Ties go to an NVIDIA config, then to the cheaper one. If none is eligible, stop: no Stage B.

## Stage B: one run on TEST

- Only the selected config, **once**; the script refuses a second run.
- **The bar is unchanged: ship only if the test false-agree Wilson 95% upper bound is ≤ 3% AND test recall ≥ 50%.** With 175 test negatives, that means **no** false agrees at all (one gives an upper bound of about 3.2%).
- If it fails: report and stop, with no second test run, and Kash decides.

## Budget

Up to $5 for both stages. The script stops past $5. Expected well under $2.
