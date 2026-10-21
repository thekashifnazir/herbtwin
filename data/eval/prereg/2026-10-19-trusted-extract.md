# Pre-registration: the extract-then-decide trusted-page check (19 Oct 2026)

Written and committed before any model call on this design. Kash chose it (option b, from
the pattern where a model fills a form and code decides) after two yes/no judges failed the bar
(`reports/2026-10-19-trusted-judge-grid-test.json`: 6/175 false agrees, Wilson upper 7.3%).

## The design

- **Stage 1, extract** (`stages/trusted_extract.py`). An NVIDIA model reads ONE page
  sentence, with the plant's name for context, and fills a fixed form: action, do or
  don't, which plants it applies to, its conditions, whether it is hedged, and whether it
  is an instruction. It never sees our advice or the plant's state.
- **Stage 2, decide** (`stages/trusted_check.decide`). Plain code. It agrees only when the
  form is an unhedged instruction to do our very action, for this plant, and every
  condition holds against the plant's known state. Anything it can't check is "unsure".
- **Stage 3, verify** (optional). A second call checks the form against the sentence.
  Any doubt means unsure.

## The set

`data/eval/sets/trusted_judge_v4.jsonl`, sha256 `6b292023923477c286068642cdb483c1c6a2dd628c45a7478fb826c49a52caa9`,
built by `scripts/build_judge_v4.py`. Its sentences are all new: none appears in v1, v2,
v3 or the #283 corpus, and the builder refuses any repeat.

| split | items | sentences | negatives (our gold) | positives (our gold) |
| --- | --- | --- | --- | --- |
| dev | 101 | 37 | 78 | 23 |
| test | 385 | 140 | 311 | 74 |
| redteam | 16 | 6 | 11 | 5 |

- **Gold:** a direct "does this sentence back our advice for this plant, in this state?"
  label per item.
- **Red-team set:** the 6 errors the last judges made, each with state variants.
- **Our rule vs our direct labels:** they disagree on 4 items, all `leave_normal`
  ("is normal"). The rule never agrees on these, so their recall is 0 by design.
- **Offline check of Stage 2:** with the hand-written forms, Stage 2 makes 0 false agrees
  on every split. So every false agree in the runs below comes from Stage 1 or Stage 3.

## Stage A: DEV only (`scripts/trusted_extract_grid.py dev`)

- **Grid:** Stage 1 on Super-VL, Super, Nano and Ultra (thinking off, temperature 0,
  220 output tokens), each with E0 (plain) and E1 (E0 plus 7 worked examples on fresh
  sentences): 8 configs.
- **Stage-3 configs:** the best eligible Stage-1 config, checked first by its own model,
  then by Ultra.
- **Reading cost:** a form depends only on the sentence, so each config reads each
  sentence once. Stage 2 then decides every state from that form.
- **Recorded per config:**
  - false agrees vs the direct gold, with Wilson 95%, split by kind;
  - recall;
  - Stage-1 field accuracy vs the hand-written forms;
  - latency p50 and p95 (wall time per sentence, with Stage 3 included, 4 calls in
    parallel);
  - dollars per answer;
  - forms that failed to parse.
- **Selection rule:**
  - Eligible: dev recall ≥ 50% and p95 latency ≤ 4 s (the advisors run alongside, so
    this keeps the answer from waiting).
  - Pick the lowest dev false-agree rate.
  - Ties go to fewer stages, then to the cheaper config.
  - If no config is eligible, stop: there is no Stage B.
- **Red team:** the selected config also runs the red-team set. Any false agree there is
  reported and is a **ship blocker**, whatever the test result.

## Stage B: TEST once (`scripts/trusted_extract_grid.py test <config> <labels>`)

- Only the selected config runs, **once**. The script refuses a second run.
- **Primary gold:** blind labels from the devpost-submission session. It saw only the test
  items (sentence, plant, our advice in plain words, and the state). It never saw the
  rule, the prompts, our labels or this branch, and it labelled by hand.
  - Labels: 57 yes, 328 no.
  - Its borderline-case notes stay unread until after this commit.
- **Secondary gold:** our direct labels.
- **Agreement between labellers:** Cohen's kappa, with every item where they differ
  listed by id.
- **The bar (primary gold):**
  - Wilson 95% upper bound on test false agrees ≤ 3%;
  - **AND** recall ≥ 50%.
  - With 328 negatives, that means at most 3 false agrees.
- **Also reported:** results vs the secondary gold, field accuracy, latency and cost.
- **If it fails:** report and stop. No second test run, no tuning against test. Kash
  decides what happens next.
- **If it passes and the red team is clean:** it goes to the UI as an exact-sentence
  quote, reusing #283's plumbing, in its own PR.

## Budget

At most $3 for Stage A and Stage B together. The runner stops at a $3.00 running total.
Spend on the trusted-page judges so far is about $0.70.
