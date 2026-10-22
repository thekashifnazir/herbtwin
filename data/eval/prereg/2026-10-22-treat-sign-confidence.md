# Pre-registration: should a seen problem sign lower a "treat it" answer? (22 Oct 2026)

Committed before the run.

## Why

Site walk part B: a clear rosemary-beetle photo, "Treat it.", was rated "Not sure, check
first". The season factor lowers every answer whose photo shows one of the month's
problem signs (`confidence._season`, −0.5), whatever the action. That −0.5 was set by hand
and never measured (`data/confidence/weights.json`: "other factors hand-set").

For "leave it", a sign is evidence against the advice. For "treat it", it is the evidence
for it. The proposed change: **for treat_or_remove, a sign hit is neutral, not lowering.**
It would raise those answers' level. Because it loosens confidence, it ships only if this
measurement passes (the integrator's rule).

## Data (fixed now)

- **Photos:** the 17 Oct problem-check set's sampler (`scripts/eval_problem_check.items`,
  seed 7):
  - 24 photos per labelled disease or pest class from `data/external/s16/herb_pd_refs`:
    basil downy mildew, mint rust, powdery mildew, aphids (6 exist) and slugs;
  - 48 healthy species photos from `species_gbif.jsonl`, fewer than the 150 there, to cut
    cost.
- **Run:** the app's own `read_photo` then `decide`, once per photo. The place is the
  home default (UK) and the month is October. Tavily is off, because the trusted page
  never changes confidence.

## What is measured

- For each answer: the shown action (`do[0]`), its level and score, and whether the
  season factor lowered it for a problem sign.
- **Right** means a "treat it" answer on a photo labelled with a disease or pest. A
  "treat it" answer on a healthy photo is wrong.
- **Counterfactual:** a treat answer whose season factor lowered it for a sign gets the
  −0.5 back, so the factor is neutral. Its level is recomputed with the calibrated cut-offs
  (below −0.4 not sure, below 0.2 fairly sure, else sure).
- **Moved:** treat answers whose level the change raises.

## The bar

- **PASS** (build the change) if all of these hold:
  - at least **20** answers moved;
  - their accuracy is **≥ 70%**, the "sure" level's measured 7 in 10;
  - its **Wilson 95% lower bound is ≥ 50%**, the "fairly sure" level's 5 in 10.
- **INCONCLUSIVE** below 20 moved, and that does not pass.
- **FAIL** otherwise.
- **Reported, with no bar:**
  - accuracy of treat answers with a sign hit and without one;
  - how many moved answers are on healthy photos (raised false alarms);
  - the action mix;
  - errors;
  - money.
- **Cost cap:** $2.00 of Token Factory (estimate about $1.50). One run only; the script
  refuses a second.

## Known limits

- **"Right" means a treat answer on a labelled sick photo.** It is not an expert's
  judgment of the best first step (isolating, or removing the plant, can be right too).
  Problem photos come from iNaturalist and are not all UK or October.
- **This measures one factor's direction, not a refit of all the weights.**
- If the change passes, it is built with a test, and the levels it raises are reported
  as a post-measurement change.
