# Pre-registration: the trusted-page judge (19 Oct 2026)

Written and committed **before any judge call**. The results go in
`data/eval/reports/2026-10-19-trusted-judge.json` and are compared against this file.
Kash chose a model judge ("the smart version") after the rules-only check (#283) was parked
for false agrees.

## Question

Does the judge (`stages/trusted_judge.py`) wrongly say a trusted page tells the gardener to
do our action now, when it doesn't? A false agree would put "Checked against RHS…" and a
quoted sentence beside advice the site never gave, on the judged site. That's the one
error that matters; a missed agree costs only a missing line.

## The set: `data/eval/sets/trusted_judge_v1.jsonl` (sha256 ac6b05194315a157…)

- **338 items, 248 gold negatives and 90 gold positives.** Each item is a sentence, a plant, a month, our action (one of the 7 judged coarse actions) and gold "supports".
- **Sources:**
  - all 223 sentences of the round-5 adversarial probe (one chemical sentence is left out; the candidates filter drops those before any judge);
  - the 108-sentence corpus (`tests/data/trusted_sentences.py` on #283's branch);
  - every reviewer sentence from rounds 1–5;
  - 8 "month mirror" positives: the same words in the month they name.
- **Composition (negatives):** condition 57, not this action or not an instruction 21, negation 19 (+12 with curly apostrophes), other season 19, removal that is not treating this plant 18, propagation/sowing/planting 16, what others do or a general fact 15, question or heading 12, negated or described hold-off 11, how or when to water 11, shelter not now or not cold 9, leave it not normal or mixed 8, water not ours 8, light as a liking 7, seed or crop storage 5. The positives: instructions 70, month-matched instructions 8, light as a move 7, leave it as normal 5.
- **Labels are author-made** (the nvidia session, 19 Oct), stated as such. Kash was never asked for a care judgment.
- **Labelling rule:** gold is true only if the sentence, read literally and on its own, tells the gardener to do our action to this plant now:
  - an instruction (an imperative, "should be …", or "is normal" for "leave it");
  - not negated, not conditional (if/when/unless/once/only/after/before/until, dry spells, hot weather), not a question or heading, not what other people do or a general fact;
  - no season named other than the item's month;
  - about this plant (not tomatoes, peas, seeds or cuttings).
  - When unsure, false.

## The judge (code at this commit; prompt hash 50e3315fac40)

- The chat's fast model (`settings.fast_model`, Nemotron Nano on Token Factory, thinking off). The run records the exact model id.
- Temperature 0, strict JSON schema `{"supports": bool, "sentence": int|null}`, max 60 tokens.
- One item per call: the item's sentence as the only candidate, after `candidates()`. If the filter drops it (no full stop, too short, a chemical), the prediction is "no".

## Metrics (pre-registered)

1. **Primary: the false-agree rate on gold negatives**, with a Wilson 95% interval, and per category.
2. **Recall on gold positives**, with a Wilson 95% interval.
3. **Stability:** 2 repeats of every item at temperature 0. Report the share of items whose prediction differs between them. A false agree in either repeat counts as a false agree (the worse of the two).

## Shipping rule (fixed now)

**Ship only if** the false-agree upper bound (Wilson 95%) is ≤ 3%, AND recall ≥ 50%. Otherwise **don't ship**: report, stop, and Kash decides. No prompt or set change after seeing results counts toward shipping; any change is a new pre-registration.

## Budget

2 × 338 Nano calls, expected under /bin/zsh.50. Cap ; stop and ask past it.
