# Eval reports

Summaries only: counts, metrics and ids. Raw per-item rows stay in `data/eval/runs/`
(gitignored; they can hold model text about test-only items). Each `<run-id>.md` has a
`<run-id>.summary.json` twin for diffing runs. One exception: the chat-search run keeps
its replies, scrubbed, in `<run-id>.rows.jsonl` (its questions are our own, not a test
set), so its citation and hand-check claims can be checked.

## The chat's Tavily search, on vs off, 19 Oct 2026

`2026-10-19-chat-search.*` (`scripts/measure_chat_search.py`). The metrics, rubric and
decision rule are in the header of `src/herbtwin/evals/chat_search.py`, committed before
the paid run (`f5eb9aa`). 30 factual herb questions, each with a key fact from the repo's
sourced data, through the real follow-up chat (Nemotron 3 Nano, thinking off). Search on
is Tavily alone; off is no search tool. Everything else is equal.
- **M1 correct (the pre-registered decision metric):** off 0.500 [0.333, 0.700], on 0.833
  [0.700, 0.967], difference **+0.333 [+0.133, +0.533]**. By the rule, **search makes
  the chat more correct.**
- **Rubric v2 (post-hoc, not pre-registered):** off 0.433, on 0.933, difference +0.500
  [+0.300, +0.667]. v2 reads the non-breaking hyphens Nano writes and rewrites the
  patterns of 15 questions, most of them too loose before. It was written after reading the replies, so it is a sensitivity check and
  M1 stays the result. A hand check of 25 replies agreed with v1 on 20 and with v2 on 25
  (the second is not independent, since v2 was written after the check).
- In-text citations 3 of 30 (all on-plant), but sources are listed under 29 of 30
  search-on replies. "Not sure": off 0.567, on 0.033. Most of the gain is the search-off
  chat declining: when it did answer, it was right 13 of 13 (v1).
- Follow-up: one search-on reply hit the 2048-token cap and came back empty.
- Cost: model $0.0092, 31 Tavily searches (about $0.25 at list price).

## Backup photo model: DeepSeek V4.1 Flash vs Nemotron 3.5 Super VL, 18 Oct 2026

Same 150 public photos (`species_gbif`) and live observe prompt `35b1b37a0ad4`, both run
on 18 Oct, so the two compare directly (DeepSeek's 0.799 of 13 Oct was on the earlier
prompt). Super VL with reasoning off.

| Run | Top-1 | Top-3 | Time a photo (p50 / p95 / max) | Cost |
|---|---|---|---|---|
| `2026-10-18-species_gbif-deepseek-ai-deepseek-v4-1-flash` | 0.776 [0.701, 0.837] (147 scored, 3 timed out) | 0.857 | 13.8 / 40.4 / 89.2 s | $0.419 |
| `2026-10-18-species_gbif-nvidia-nemotron-3-5-super-vl` | 0.627 [0.547, 0.707] | 0.813 | 1.6 / 1.9 / 2.1 s | $0.083 |

Paired on the 147 photos both scored: Super VL minus DeepSeek top-1 is **-0.150 [-0.231,
-0.068]** (bootstrap, 5,000 draws); DeepSeek right where Super VL is wrong on 31 photos, the
reverse on 9. Super VL never named garlic chives (0/10; DeepSeek 10/10) and got coriander
2/10 (9/10). **DeepSeek stays the backup**; Super VL is 8 to 21 times faster (p50, p95). Latency
percentiles come from the run rows (`data/eval/runs/`, gitignored).

## Problem check, in scope and out, 17 Oct 2026 (re-run)

`2026-10-17-problem-check.summary.json`, observe prompt `35b1b37a0ad4` (now recorded in the
file), GLM-5.3-Flash with no backup. Each class now also counts the photos "in scope": the
read named a herb the app knows, so a check could run at all. Powdery mildew was added to
mint's and oregano's checkable problems (sourced: Plant Disease host reports).

| Class | Right, all photos | Right, in scope |
|---|---|---|
| basil downy mildew | 8 / 24 | 8 / 21 |
| mint rust | 14 / 24 | 14 / 22 |
| powdery mildew | **10 / 24** (was 0) | **10 / 13** |
| aphids | 1 / 6 | 1 / 1 |
| slugs and snails | 0 / 24 | 0 / 0 (the photos show slugs on soil, no plant) |
| healthy, false alarms | **0 / 149** (1 error) | 0 / 139 |

All five classes: 33 of 102 named right (33 of 57 in scope); the 5 judge samples (2
right) are counted apart. Healthy: 149 is the 150 less 1 call error; 139 of them were in
scope. The earlier run's 10 downy mildew is within run-to-run noise of this run's 8.

## The twin test at scale, 18 Oct 2026

`2026-10-18-twin-at-scale.*` (`scripts/eval_twin_at_scale.py`). The metrics and the decision
rule are in the header of `src/herbtwin/evals/twin_at_scale.py`, fixed before any paid call;
the run started from `617a435`. 120 scripted cases: 10 herbs x 6 weather scenarios set
against each herb's damage line x pot or ground, in London, Edinburgh, Truro and
Manchester. Super's panel as live, 2 repeats, PLANT MODEL on vs off. The twin finds a risky
day in 42 cases. Reference: the twin's own better choice.
- **P1 (the pre-registered decision metric)**, main action is the twin's choice (n=240 per
  arm): off 0.946 [0.908, 0.979], on 0.958 [0.925, 0.988], difference +0.013 [-0.025,
  +0.054]. The interval includes 0: **no measurable overall change.**
- P2, a subset, where the twin finds a risky day (n=84): off 0.929, on 1.000, difference
  +0.071 [+0.012, +0.155]. **This rests on 4 of 42 cases, which moved to protect with the
  twin, none the other way** (basil frost in a pot and in the ground, basil at an ordinary
  frost in a pot, thyme dry in the ground; sign test p = 0.125).
- P3, leave it where the twin finds none (n=156): off 0.955, on 0.936, difference -0.019
  [-0.071, +0.026], no measurable change. P4, treatment on a healthy plant: 0 of 240 in
  both arms.
- About $1.93 in all. The reference comes from the same model the "on" arm reads: on risky
  days the advisor follows the twin's forecast; it does not show the twin is right.

## Plant model on vs off, 17 Oct 2026

`2026-10-17-plant-model-ablation.*` (`scripts/eval_plant_model.py`): 60 synthetic weather
items, Super's panel, 2 repeats, PLANT MODEL block on vs off with everything else equal.
Main action fits the rule: off 0.925, on 0.958, difference +0.033 [-0.033, +0.108] (no
measurable difference). Frost scenario, did not shelter: 0.200 vs 0.033 (all basil, a
tender herb, before a 7 °C night). No unwanted watering or treatment in either arm. $0.72
(the summary's `spent_this_run_usd` is 0: it was rebuilt from cached rows after a metric
fix). The right answers come from the same weather the model reads, so this shows the
model's forecast is used, not that advice is more expert-correct. Write-up:
`docs/reference/nvidia-models.md`.

## Nemotron 3.5 Super VL on the photo step, 17 Oct 2026

Observe prompt `35b1b37a0ad4` (live), reasoning off, public sets only.

| Run | Result | Time a photo | Cost |
|---|---|---|---|
| `2026-10-16-species_gbif-glm-5-3-flash-scene` | top-1 0.846 [0.785, 0.899], top-3 0.933 (149 scored, 1 failed) | 8.2 s | $0.134 |
| `2026-10-17-species_gbif-nemotron-3-5-super-vl` | top-1 0.627 [0.547, 0.707], top-3 0.820 | 1.6 s | $0.083 |
| `2026-10-17-decline_indoor-glm-5-3-flash-scene` | balanced accuracy 0.900 [0.842, 0.950] | 12.0 s | $0.104 |
| `2026-10-17-decline_indoor-nemotron-3-5-super-vl` | balanced accuracy 0.833 [0.774, 0.894] | 1.2 s | $0.050 |

GLM keeps the photo step. Write-up: `docs/reference/nemotron-super-vl-probe.md`.

## Nemotron 3 Ultra, 17 Oct 2026

Same prompt (`7ba44f01d95b`) and items as Super's `*-p7ba` runs, one ask each.

| Run | Main action | Over-treatment | Cost |
|---|---|---|---|
| `super-se-150-p7ba` | 0.440 [0.360, 0.520] | 0.020 [0.000, 0.047] | $0.41 |
| `ultra-se-150-p7ba` | 0.393 [0.313, 0.467] | 0.127 [0.080, 0.180] | $0.52 |
| `super-mirage-p7ba` | 0.435 [0.365, 0.505] | 0.010 [0.000, 0.025] | $0.55 |
| `ultra-mirage-p7ba` (196 of 200 valid) | 0.423 [0.352, 0.495] | 0.082 [0.046, 0.122] | $0.86 |

Ultra is no better on the main action and over-treats 6 to 8x as often: not adopted as
advisor or tie-breaker. As a judge (`2026-10-17-pairs_se-nemotron-ultra.*`, 750 verdicts,
7 unparseable): **0.750** [0.706, 0.789], level with Claude Sonnet (0.715) and qwen3:14b
(0.757); position consistency 0.908 over 368 pairs; preferred-later 0.687 [0.590, 0.778], preferred-shorter 0.665 [0.585,
0.748], so it passes D18. $1.73 in two invocations (the first spent $1.608 and stopped at its $1.60
budget; the summary's `spent_this_run_usd` is the second's share). Held-out rule (D11):
it may not grade Nemotron output, so not the live advisor's. Write-up:
`docs/reference/nvidia-models.md`.

## Phase B1 finer actions, 5 Oct 2026 (D43)

The advisor answers in 17 actions; scoring folds them back to phase A's nine
(`schemas.coarse`). Nemotron Super, 3 asks, coarse primary match; gate = phase A's lower
95% bound (SE 0.387, MIRAGE 0.375).

| Run | SE 150 | MIRAGE 200 | Cost |
|---|---|---|---|
| Phase A final (`2026-10-05-panel2-*`) | 0.467 [0.387, 0.540] | 0.445 [0.375, 0.515] | |
| `b1-*`: finer actions | 0.400 [0.327, 0.480] | 0.385 [0.320, 0.455] | $0.97 |
| `b1b-*`: and check_pests never primary (kept) | **0.427** [0.347, 0.500] | **0.410** [0.340, 0.475] | $0.87 |

In `b1-*` the advisor led with `check_pests` 18 times on SE (experts "check first" 6) and
treated less: the over-asking of plan 2d under a new name. Making `check_pests` a hedge
like `ask_first` (#45) recovered most of the gap; what is left (about 0.04 a set) is
inside one standard error. MIRAGE "treat" as primary stays rare (4; phase A 9; experts
25). Confidence weights were not refitted: they are keyed by the coarse classes, which
the runs keep.

## Findings, 4 Oct 2026

### Judge calibration on Stack Exchange preference pairs (plan 2b, D13 to D18)

`2026-10-04-pairs_se-claude-claude-sonnet-5-5.*`: Claude Sonnet 5.5 through the Claude
CLI, 375 pairs (226 tagged diagnosis, 167 herb; 18 carry both tags), both answer orders,
750 of 750 verdicts parsed.

- Overall agreement with the human-preferred answer **0.715** [0.672, 0.756]; position
  consistency 0.872; it never answers "tie".
- The human label is confounded with posting order: "pick the earlier answer" scores
  0.776 and "pick the longer" 0.680 with no model at all. So overall accuracy cannot
  be compared with those baselines (D18).
- On the pairs where people preferred the **later** answer: **0.744** [0.655, 0.821];
  where they preferred the **shorter** one: **0.608** [0.525, 0.688]. Both CIs are above
  0.5, so the judge is at least partly reading the advice rather than tracking order or
  length (the shorter-preferred lower bound, 0.525, is close to chance). **Claude Sonnet
  passes D18** and may grade free-text advice. D18 was written after these numbers were
  seen (the plan says so); later judges are held to it unchanged.
- **Local qwen3:14b, thinking off, also passes D18** (`2026-10-04-pairs_se-ollama-qwen3-14b-no-think.*`,
  750 of 750 parsed): overall **0.757** [0.716, 0.796]; later-preferred **0.756**
  [0.667, 0.839]; shorter-preferred **0.629** [0.550, 0.713]; position consistency 0.877.
  Its intervals overlap Claude's on every line, so a free local judge is as good as the
  subscription one here. It may not grade qwen output (held-out rule, D11).
- Codex (ChatGPT via the Codex CLI): 98 of 750 verdicts before the subscription limit
  (twice: until 06:40, then until 11:45). Not reported until complete.

### Action truth (plan 2b, D16 and D20)

`data/eval/sets/actions_se.jsonl` (774 accepted Stack Exchange answers, CC BY-SA) and
the private working repo's `actions_mirage.jsonl` (200 MIRAGE Plant Care answers, test-only) hold ids and the
action classes each answer recommends, extracted by Claude Sonnet. No answer text is
stored.

`2026-10-04-actions-handcheck.json`: 49 Stack Exchange answers, stratified by class,
read by the agent and labelled by hand. That is reading comprehension, not a care
judgement. The file holds ids, labels and a short note per item, no answer text.

| Labels | Primary agrees with hand | Primary and whole set agree | Mean Jaccard |
|---|---|---|---|
| qwen3:14b, thinking off | 34 / 49 | 13 / 49 | 0.63 |
| Claude Sonnet 5.5, check run | 38 / 49 | 26 / 49 | 0.86 |
| Claude Sonnet 5.5, final set | 40 / 49 | 28 / 49 | 0.88 |

Claude's own repeatability: the same primary on 45 of 49 between the two runs. Claude's
primary agrees with the hand labels on 38 to 40 of 49 (78 to 82%; about 4 hand verdicts
are judgement calls), so **roughly 80% is an approximate cap** for advice scores against
these labels: exact only if a model's errors are independent of the extractor's, so a
model that makes Claude's mistakes could score above it.

Expert primary actions:

| Set | Primary actions |
|---|---|
| Stack Exchange | other 183, treat or remove 160, leave it (normal) 150, stop watering 66, prune 62, ask first 59, move light 43, water 37, shelter 14 |
| MIRAGE | other 44, prune 34, leave it 33, water 26, treat or remove 25, ask first 20, shelter 11, stop watering 5, move light 2 |

"Leave it, this is normal" is the primary in about a fifth of expert answers. An advisor
that always finds something to fix will be wrong that often.

### Perception baseline: qwen2.5vl:7b on the v1 sets (plan 2a, PR 4)

Local Ollama, free, temperature 0, images capped at 1,024 px, prompt hash `23d006a5cd18`.
Reports: `2026-10-04-<set>-qwen2-5vl-7b.*`. 696 items: 694 scored, 2 failed, 0 call errors.

| Set | n | Headline | Reading |
|---|---|---|---|
| Droop, soybean (expert 0 to 5 mapped to 0 to 3) | 180 | droop 0 for **every** image | No signal: it calls field canopies "healthy leaves". QWK is 0 by construction. |
| Droop, recovery time-lapses (Fittonia 40, basil 23 frames) | 63 | droop 0 for every frame | No signal: Spearman against time is undefined in both clips. |
| Decline, indoor leaves (withering and tip necrosis vs healthy, 60 + 60) | 120 | balanced accuracy 0.692 [0.627, 0.754]; precision 1.00, recall 0.38 | Confounded: 67 photos were answered "not a plant" (50 healthy, 17 declining), and observe then zeroes decline. Among the 53 it called plants: decline found in 23 of 43, no false alarm in 10 healthy. |
| Species, GBIF iNaturalist photos (15 taxa x 10) | 150 | top-1 0.473 [0.392, 0.554]; top-3 0.601; genus 0.547 | Rosemary and lemon balm 10/10; basil, coriander, parsley, sage 8/10; ferns 0/10; garlic chives and spearmint 1/10; marjoram given for oregano. 35 answered "not a plant". Scored with the #34 scorer (0.426 under the first one, which missed "Garlic Chive" and "Sweet Basil"). |
| Garden crops, v1 condition score (transfer check only) | 183 | QWK 0.282 [-0.040, 0.538]; exact 0.536; within one 0.918 | Mostly 0 (145 of 183). Not distinguishable from the earlier dedicated wilting judges on these crops (0.33 to 0.48, different prompt, 146 crops); intervals overlap. |

What this says:

1. **qwen2.5vl:7b with the product's observe prompt is not usable for droop.** It never
   scores droop above 0 on public images. (A dedicated wilting prompt on the garden crops
   earlier gave it non-zero scores, kappa 0.38, so the prompt is part of the problem.) Droop needs a stronger vision model (the paid table, D12: GLM-5.3-Flash on
   Token Factory) or a dedicated classifier trained on the safe-to-train droop sets.
2. **The observe prompt's framing hurts on public data.** "A potted culinary herb in a
   UK garden" plus the not-a-plant reset sends detached leaves and wild or flowering
   plants to "not a plant" (102 of 270 decline and species photos). A follow-up should
   score is_plant separately and give the eval a neutral framing, or stop the reset
   from zeroing decline.
3. **Decline is visible to a small local model** when it does look (23 of 43, no false
   alarms), which matches the garden finding that dieback is easier than posture.

### Advice baseline: the advise stage on expert questions (plan 2c, D19)

`2026-10-04-advice-actions_*-qwen3-14b-no-think.*`. qwen3:14b, thinking off, local and
free. It sees the question text only, no photo. Truth is Claude-extracted expert actions
(D20), whose primary matches a careful reading about 80% of the time.

| Set | n | Primary matches expert | Our primary among expert's | Jaccard | Over-treatment | Watering conflict | Asked when expert asked |
|---|---|---|---|---|---|---|---|
| Stack Exchange | 774 | 0.283 [0.251, 0.315] | 0.465 | 0.294 | 0.114 [0.092, 0.137] | 0.043 | 0.619 (n 176) |
| MIRAGE | 200 | 0.350 [0.285, 0.415] | 0.575 | 0.302 | 0.055 | 0.010 | 0.514 (n 72) |

The main failure is visible in the primaries. On Stack Exchange the advisor chose **ask
first** for 356 of 774 questions, where the experts asked first for 59, and **leave it,
this is normal** for 81, where the experts chose it for 150. It hedges instead of
answering, and under-uses "nothing is wrong". The next prompt change should target
exactly those two classes and be measured on the same sets.

### Paid perception table: GLM-5.3-Flash on Token Factory (D12)

Approved by Kash on 4 Oct after a quote of about $0.30, with a worst case of about $1.60. Same five sets, same observe prompt (hash `23d006a5cd18`) and images capped at 1,024 px. Recorded cost **$0.44** for 696 images, about $0.0006 each. Timed-out calls may add a little more: some were retried after the timeout was made configurable (#38, 180 s). Reports: `2026-10-04-<set>-glm-5-3-flash.*`. 696 of 696 scored.

| Set | qwen2.5vl:7b (local, free) | GLM-5.3-Flash (paid) |
|---|---|---|
| Droop, soybean (QWK, 0 to 3) | 0.000 (every image 0) | **0.285** [0.000, 0.373]; within one 0.667; predictions 141 / 16 / 23 at 0 / 1 / 2 |
| Droop recovery (Spearman with time; negative = recovers) | undefined (flat) | basil **-0.772**, Fittonia **-0.353** |
| Decline (balanced accuracy) | 0.692, with 67 "not a plant" | **0.833** [0.765, 0.900]; precision 0.82, recall 0.85; 7 "not a plant" |
| Species (top-1) | 0.473 | **0.867** [0.813, 0.920]; top-3 0.947; weakest: soft shield fern 0.2, tarragon 0.6 |
| Garden v1 (QWK, transfer check) | 0.282 | **0.406** [0.178, 0.564]; within one 0.902 |

What this says:

1. **The product's observe model (GLM-5.3-Flash) does see droop**, but the evidence is
   modest: soybean QWK 0.285 with a lower bound of 0.000 (only 10 plots), and recovery
   tracked strongly in basil (-0.772) but noisily in Fittonia (-0.353, no CI with one clip). qwen2.5vl:7b sees neither.
2. **Species is close to app level** at 0.867 top-1. For comparison, the best phone ID app
   in Campbell et al. 2023 reached about 88%; PictureThis scored 94% in a 2022 tree study.
   Taxa differ, so this is only a rough yardstick. Ferns remain the gap.
3. **Decline is reliable** (0.83), and the "not a plant" problem nearly disappears with
   the stronger model (7 of 120, not 67). The framing issue is mostly a small-model
   problem.
4. On Kash's garden, GLM's QWK of 0.406 sits in the range of the dedicated wilting
   judges (0.33 to 0.48, scored on 146 crops with a judge prompt; this is 183 crops with
   the product prompt). Its interval [0.178, 0.564] also overlaps qwen's, so the garden
   check alone does not separate the two models.

### Advice with the question's photo (plan 2c follow-up)

The text-only advisor asks first far more than experts do. The hypothesis: the question came with a photo that the expert saw and the advisor did not. Test: the 546 Stack Exchange questions that have a photo (question photos only, never answer photos). Each photo goes through observe (qwen2.5vl:7b, local), then advise (qwen3:14b) sees what observe saw, as in the app. When observe answers "not a plant", the advisor gets the text alone. Paired on the 538 questions scored in both runs (`2026-10-04-advice-photo-paired.json`; per-run reports `2026-10-04-advice-actions_se-photo-subset-text-only.*` and `...-with-photo.*`).

| Same 538 questions | Text only | With photo | Difference [95% CI] |
|---|---|---|---|
| Primary matches expert | 0.249 | 0.268 | +0.019 [-0.007, +0.043] |
| Our primary among expert's | 0.433 | 0.457 | +0.024 [-0.004, +0.052] |
| Jaccard | 0.264 | 0.276 | +0.012 [-0.005, +0.030] |
| Over-treatment | 0.113 | 0.095 | -0.019 [-0.037, 0.000] |
| Watering conflict | 0.043 | 0.039 | -0.004 [-0.013, +0.006] |
| "Ask first" as primary | 301 | 255 | -46 |

The photo moves the five metrics in the table the right way: fewer questions asked back, less over-treatment. No difference clears zero; over-treatment's interval just reaches it. There is a trade-off. On the 147 questions where the expert did ask first, the advisor now asks first less often: 0.660 -> 0.551 (paired on the same 147). The fewer questions-back are not all in the right places.

The weak link is the small vision model, which answered "not a plant" for 112 of the 538 photos. GLM-5.3-Flash, which answered "not a plant" for 7 of 120 detached leaves and 0 of 150 species photos, is the obvious next observe model here: about $0.35 for these 546 photos at the measured rate ($0.44 for 696), after a quote and Kash's yes.

A first attempt at the same problem through the prompt alone ("answer first, ask only if needed") was **tried and dropped**. Stack Exchange 0.283 -> 0.280, MIRAGE 0.350 -> 0.305, and "ask first" barely moved. Its summaries are not tracked.

### Plan 2d: better eyes, a hosted advisor, few-shot, and "always give the best action"

Decisions D21 to D24 in the private working repo's `2026-10-04-plan2d-ask-less.md`. All
comparisons are paired on the same questions (`scripts/compare_advice.py`; files
`2026-10-04-*-paired.json`), difference = second minus first, 95% bootstrap interval over
questions. Token Factory spend for everything below: about $2.60.

**1. GLM-5.3-Flash as the eyes, local qwen3:14b as the advisor (546 photo questions).**
GLM said "not a plant" for 44 photos (qwen2.5vl:7b: 112). Cost $0.40.

| Same 546 questions | Text only | GLM photo | Difference |
|---|---|---|---|
| Primary matches expert | 0.249 | 0.278 | +0.029 [0.000, +0.060] |
| Over-treatment | 0.117 | 0.178 | **+0.060 [+0.037, +0.086]** |
| Asked when the expert asked (n 148) | 0.662 | 0.480 | -0.182 [-0.264, -0.108] |
| "Ask first" as primary | 304 | 220 | -84 |

Against the qwen2.5vl photo run (538 paired) GLM adds only +0.011 [-0.019, +0.041] on
primary match and raises over-treatment by +0.080. **Better eyes see more symptoms and
the advisor treats more.**

**2. Nemotron Super on Token Factory as the advisor.** On the same 150-question Stack
Exchange sample it matches the expert's primary 0.387 [0.307, 0.460] (qwen3:14b on all
774: 0.283); MIRAGE 0.410 [0.340, 0.480] (qwen3:14b 0.350). It still asks first far
more than experts (45 of 150 vs 9; 75 of 200 on MIRAGE), and those answers almost never
named the expert's action as well (1 of 26 on Stack Exchange, 0 of 47 on MIRAGE, where
the expert led with something else).

**3. Few-shot (six expert answers first) does not help** (Super): Stack Exchange
0.387 -> 0.340 (-0.047 [-0.120, +0.020]), MIRAGE 0.410 -> 0.395 (-0.015 [-0.065, +0.035]);
"ask first" 45 -> 42 and 75 -> 66. Dropped.

**4. A photo helps a hedging advisor commit** (Super, old prompt, 150 photo questions):
"ask first" 65 -> 29, primary match 0.260 -> 0.340 (+0.080 [-0.007, +0.167]),
over-treatment 0.020 -> 0.060 (+0.040 [+0.007, +0.080]).

**5. "Always give the best action" (D24, Kash's choice).** Super, paired with the old
prompt on the same questions:

| | Stack Exchange (150) | MIRAGE (200) |
|---|---|---|
| "Ask first" as primary | 45 -> 0 | 75 -> 0 |
| Primary matches expert | +0.007 [-0.073, +0.080] | +0.035 [-0.030, +0.100] |
| Over-treatment | 0.040 -> 0.033 | 0.015 -> 0.005 |
| Watering conflict | 0.040 -> 0.053 | 0.030 -> 0.055 |
| Asked when the expert asked | 0.375 -> 0.312 | 0.458 -> 0.306 |

About 30% of answers come back with `confidence: low` and a follow-up question (161 of
546 on the photo set; counted from the run rows, not in a tracked file).

**6. With an advisor that always answers, the photo adds nothing measurable** (Super,
546 photo questions, 543 paired): primary match 0.370 vs 0.363 (-0.007 [-0.044, +0.031]),
over-treatment 0.046 vs 0.059 (+0.013 [-0.006, +0.031]). The earlier photo gains (1 and
4) came mostly from making the advisor commit instead of asking; the always-answer rule
now does that on its own. Cost $0.80 for the photo run, $0.38 for the text run.

What this says:

1. **The advisor model matters more than anything tested here:** Nemotron Super beats
   local qwen3:14b by about 0.10 on Stack Exchange (0.387 on a 150 sample vs 0.283 on all
   774; not paired) and about 0.06 on MIRAGE (0.410 vs 0.350, intervals overlap); with
   the always-answer prompt Super reaches 0.445 on MIRAGE.
2. **The over-asking was a prompt and policy problem, not missing information.** Few-shot
   did not fix it; a photo fixed it at the price of more treatment; telling the advisor to
   always give its best action fixed it with no loss and no extra treatment.
3. **The photo's value is not in choosing the action class** on these questions. Its
   value for the app is elsewhere (species, decline, droop: see the GLM perception
   table). Note the truth here is the expert's text answer, which was written from the
   same text plus the photo; a set where the photo carries information the text lacks
   would test this better.
4. **Watch watering.** Committing moved watering contradictions up by 1 to 3 per 100
   questions (intervals touch zero, so a signal to watch rather than a proven harm).
   Pairing every watering answer with the finger-test question is the next refinement to
   test.

**7. The soil check with every watering answer (D25).** Super with the always-answer
prompt, plus: whenever the main action is water or stop watering, `ask` must hold the
finger test (how the soil feels 2 cm down). Paired with the always-answer runs on the same
questions (`2026-10-04-super-soilcheck-{se,mirage}-paired.json`). Cost $0.28.

| | Stack Exchange (150) | MIRAGE (200) |
|---|---|---|
| Watering conflict without a soil check (new metric) | 0.053 -> 0.013 (**-0.040 [-0.073, -0.013]**) | 0.040 -> 0.000 (**-0.040 [-0.070, -0.015]**) |
| Watering conflict, any | 0.053 -> 0.033 (-0.020 [-0.053, +0.007]) | 0.055 -> 0.015 (**-0.040 [-0.070, -0.010]**) |
| Primary matches expert | 0.393 -> 0.413 (+0.020 [-0.053, +0.093]) | 0.445 -> 0.445 (0.000 [-0.050, +0.050]) |
| Over-treatment | 0.033 -> 0.047 (+0.013 [-0.020, +0.053]) | 0.005 -> 0.010 (+0.005 [0.000, +0.015]) |
| Asked when the expert asked | 0.312 -> 0.375 (n 32) | 0.306 -> 0.417 (n 72) |

`unguarded_water_conflict` counts a watering contradiction only when the answer carries no
follow-up question, since a person who checks the soil first will not act on a wrong
watering call blindly. The rule also made the advisor choose watering as its main action
less often (37 -> 25 and 30 -> 27 of the answers), and every watering answer now carries
the check (25 of 25, 27 of 27; counted from the run rows). **The watering risk that
"always give the best action" introduced is closed, at no cost in accuracy.**
