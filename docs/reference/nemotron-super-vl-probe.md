# Nemotron 3.5 Super VL on the photo step (17 Oct 2026)

**Result: GLM-5.3-Flash keeps the live photo step.** `nvidia/Nemotron-3.5-Super-VL`, a
Nemotron vision model now on Token Factory per token, named the species in **0.627** of
150 public photos against GLM's **0.846** on the same prompt (GLM: 149 scored, 1
failed). The intervals do not overlap. It is the best NVIDIA vision model we have
measured (Nemotron 3 Nano Omni 0.587, Cosmos-Reason2-32B 0.574), and it is 5x faster than
GLM on the species set at about 60% of the cost, but naming the plant is the step
everything else hangs on. Eval only: nothing live changed.

## How it ran

- **Model:** `nvidia/Nemotron-3.5-Super-VL`, Token Factory per token, image + text in,
  $0.30 / $0.90 per 1M tokens (GLM $0.15 / $0.50). Added to the adapter's price table so
  runs record cost.
- **Reasoning must be off.** With reasoning on, one photo's call and its repair both ran
  to the 4,096-token output cap with no JSON (about 10 s and $0.004 each). Off
  (`HERBTWIN_NO_THINKING_MODELS=nvidia/Nemotron-3.5-Super-VL`), it answered in 1.7 s with
  171 output tokens.
- **Same everything else:** `scripts/eval.py`, observe prompt `35b1b37a0ad4` (the current
  "scene" prompt), 1,024 px, temperature 0, one repair call, the same scorer. Only the
  public sets were sent (`species_gbif`: GBIF, CC0/CC BY; `decline_indoor`: Mendeley, CC
  BY 4.0); no garden photos. GLM's decline run was redone today on the current prompt so
  the pair is like for like.

## Results

| Test | GLM-5.3-Flash (live) | Nemotron 3.5 Super VL |
|---|---|---|
| Species top-1, `species_gbif` (150) | **0.846** [0.785, 0.899] (16 Oct; 149 scored, 1 failed) | 0.627 [0.547, 0.707] |
| Species top-3 | 0.933 [0.893, 0.966] | 0.820 [0.760, 0.880] |
| Decline, balanced accuracy, `decline_indoor` (120) | **0.900** [0.842, 0.950] | 0.833 [0.774, 0.894] |
| Decline recall / specificity | 0.950 / 0.850 | 0.667 / **1.000** |
| Mean time per photo | 8.2 s (species), 12.0 s (decline) | **1.6 s**, **1.2 s** |
| Cost per photo (species, decline) | $0.00089, $0.00087 | **$0.00055**, **$0.00042** |

- **Species:** it never named garlic chives, tarragon or soft shield fern (0/10 each)
  and got coriander 2/10 and lemon balm 3/10. GLM gets 0.8 to 1.0 on all of those except
  tarragon (0.44) and soft shield fern (0.3). It was perfect on basil, sage, rosemary,
  Japanese maple and male fern.
- **Decline:** it never called a healthy plant declining (precision and specificity 1.0)
  but missed a third of the declining ones (recall 0.667). GLM catches 95% and raises
  more false alarms. For a care app a missed problem is the worse error.
- **As the backup photo model:** the current backup, DeepSeek-V4.1-Flash, scored 0.799
  [0.729, 0.861] on the species set (13 Oct, earlier prompt), above Super VL's whole
  interval. So no change there either.

Not run, as the brief made them conditional on a close species score: the problem check
on the judge samples (`scripts/eval_problem_check.py`) and the garden condition set.

## Spend

About $0.25 of Token Factory: step 0 $0.01, species $0.083, decline $0.050, GLM decline
re-run $0.104.

## Files

- Reports: `data/eval/reports/2026-10-17-{species_gbif,decline_indoor}-nemotron-3-5-super-vl.*`,
  `data/eval/reports/2026-10-17-decline_indoor-glm-5-3-flash-scene.*`; GLM species:
  `2026-10-16-species_gbif-glm-5-3-flash-scene.*`.
- Reproduce (from a checkout with `data/external`, `HERBTWIN_ENV_FILE` set):

```
HERBTWIN_NO_THINKING_MODELS=nvidia/Nemotron-3.5-Super-VL uv run python scripts/eval.py \
  --set species_gbif --backend tokenfactory --model nvidia/Nemotron-3.5-Super-VL --yes-paid
```
