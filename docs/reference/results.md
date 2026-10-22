# Results, and how to rerun them

The rates carry 95% bootstrap intervals; the AUROC is one held-out value. Full reports,
with ids and labels but no answer text: [data/eval/reports/](../../data/eval/reports/README.md).
The same public reports and sets are also mirrored, read-only, on Nebius Object Storage at
`https://storage.uk-south1.nebius.cloud/herbtwin-public-eval/<path below data/eval/>`, for example
[reports/README.md](https://storage.uk-south1.nebius.cloud/herbtwin-public-eval/reports/README.md)
([how it is published](eval-bucket-public.md)). Results that failed are kept
too: the models we tested and dropped are in
[nvidia-models.md](nvidia-models.md), and the reports
directory holds the failed pre-registered rounds beside the passing ones.

| What | Set | Result |
|---|---|---|
| Photo: species, top-1 (GLM-5.3-Flash, live prompt) | 150 GBIF/iNaturalist photos, 15 taxa (149 scored) | **0.846** [0.785, 0.899]; top-3 0.933 (`2026-10-16-species_gbif-glm-5-3-flash-scene`) |
| Photo: is it declining? (balanced accuracy, live prompt) | 120 indoor-leaf photos | **0.900** [0.842, 0.950] (`2026-10-17-decline_indoor-glm-5-3-flash-scene`) |
| Photo: problem check, healthy plants flagged with a problem (GLM-5.3-Flash) | 150 healthy GBIF photos, 149 read (1 read failed) | **0 of 149** false alarms (`2026-10-17-problem-check.summary.json`) |
| Advice: main action matches the expert's (Nemotron 3 Super, 3 asks) | 150 Stack Exchange questions | **0.427** [0.347, 0.500] (`b1b-se-150`) |
| Advice: same | 200 MIRAGE plant-care questions | **0.410** [0.340, 0.475] (`b1b-mirage`) |
| Confidence: separates right from wrong main actions (AUROC on held-out cases: 624 Stack Exchange questions the weights were never fitted on, live advisor, reported alongside the pre-registered levels test, 19 Oct) | `actions_se` | **0.63** (0.74 was the 5 Oct cross-fit on the same 350 questions: fit on one set, scored on the other) |
| The twin: does the advisor take the twin's better choice? (Nemotron 3 Super's panel, twin on vs off) | 120 scripted cases, 42 with a risky day | Risky cases: **84 of 84** answers with the twin, **78 of 84** without; 4 of the 42 cases moved to the twin's choice, none the other way (p = 0.125). Pre-registered overall measure: no change, **+0.013** [−0.025, +0.054]. Over-treated a healthy plant: 0 of 240 in each arm (`2026-10-18-twin-at-scale`) |
| Chat: does Tavily search make the answer right? (Nemotron 3 Nano, search on vs off) | 30 factual herb questions | **25 of 30** right with search, **15 of 30** without: **+0.333** [+0.133, +0.533], pre-registered (`2026-10-19-chat-search`) |
| Advice: says "treat it" when the expert did not (one ask each) | 150 Stack Exchange questions | **Super 0.020** [0.000, 0.047]; Ultra 0.127 [0.080, 0.180] (`super-se-150-p7ba`, `ultra-se-150-p7ba`) |
| Trusted-page check on real pages: false agrees (Nemotron 3 Ultra reads, code decides; pre-registered round 6) | 192 items from trusted-site searches, 191 blind negatives | **0 of 191** (`2026-10-19-trusted-realpage-r6.json`) |
| Trusted-page check, round 8 (live since 22 Oct): whole pages and a last Ultra check | 444 items from 63 new plant states, 418 blind negatives, 26 positives | **3 of 418** false agrees [0.24%, 2.09%], PASS; recall **10 of 26** (target 0.5, missed) (`2026-10-22-trusted-realpage-r8.json`) |

The two advice rows are three asks on the 5 Oct prompt. On the live prompt, asked once,
Super scores 0.440 [0.360, 0.520] and 0.435 [0.365, 0.505] (`super-se-150-p7ba`,
`super-mirage-p7ba`).

How to read the advice rows: the expert's main action was extracted from free-text
answers, and a hand check agreed with that extraction about 80% of the time, so 0.8 is
roughly the ceiling. In about a fifth of expert answers the right advice is "leave it,
this is normal", which is why the app can say so.

How to read the twin row: the right answer in that test is the twin's own better choice,
so it shows the advisor follows the twin's forecast, not that the twin is right.

How to read the chat row: most of the gap is the chat without search saying it is not
sure (17 of 30). A stricter marking scheme, written after reading the replies, gives
+0.50; it is a check, not the result.

How to read the confidence levels: the answer says "our best read, about half the time" or
"not sure, check first, about 1 in 3". In the pre-registered check on the 624 held-out
questions, the old top level ("about 7 in 10") matched the expert 0.51 [0.45, 0.57], and
the middle level (0.31) was no better than the bottom (0.32), so the two lower levels were
merged (recorded in `src/herbtwin/confidence.py`, above `LEVEL_TEXT`).

## Rerun a number

Each command is the one the report was made with; run it from the commit the report
names (the reports record it). Every paid script quotes its cost and stops at a budget;
it spends nothing without `--yes-paid`, and `--dry-run` shows the quote only. Paid runs
need `HERBTWIN_NEBIUS_API_KEY` (and the chat test a Tavily key) in `.env`. The photo and
advice sets hold ids and labels only; the photos and question texts they point to are
not shipped and are read from `data/external/` (`scripts/build_eval_sets.py` documents
the layout). The twin and chat tests need no external datasets.

| Number | Command | Cost, about |
|---|---|---|
| Species 0.846 | `uv run python scripts/eval.py --set species_gbif --backend tokenfactory --model zai-org/GLM-5.3-Flash --yes-paid` | $0.13 |
| Declining 0.900 | the same with `--set decline_indoor` | $0.10 |
| Advice 0.427 | `uv run python scripts/eval_advice.py --set actions_se --model nvidia/nemotron-3-super-120b-a12b --backend tokenfactory --asks 3 --limit 150 --workers 8 --yes-paid` (at `f0b841c`) | $0.37 |
| Advice 0.410 | `uv run --with pyarrow python scripts/eval_advice.py --set actions_mirage --model nvidia/nemotron-3-super-120b-a12b --backend tokenfactory --asks 3 --workers 8 --yes-paid` (at `f0b841c`) | $0.50 |
| Advice 0.440 / 0.435 (live prompt) | the two commands above with `--asks 1`, at the current commit | $0.41 / $0.55 |
| Confidence 0.63 | `uv run python scripts/eval_advice.py --set actions_se --model nvidia/nemotron-3-super-120b-a12b --backend tokenfactory --asks 3 --run-id super-se774-p7ba`, then the shipped `data/confidence/weights.json` and cut points on the 624 questions not in the 5 Oct fit (rows not shipped) | about $2.14 |
| Twin 84 of 84 | `uv run python scripts/eval_twin_at_scale.py --repeats 2 --budget 4 --yes-paid` (at `617a435`) | $1.93 |
| Chat search 25 of 30 | `uv run python scripts/measure_chat_search.py --budget 3 --yes-paid` (at `f5eb9aa`; `--rescore` re-marks saved rows for free) | $0.01 model + $0.26 Tavily |

## What the paid runs cost

- **Paid evals cost cents, so the species and advice rates above carry 95% bootstrap
  intervals.** 696 photos (513 public, 183 from our own garden) through GLM cost $0.44 in total. A 150 to 200 question
  advice run on Nemotron 3 Super with one ask each took 2 to 6 minutes (8 workers) and
  about $0.08 to $0.19 on the early prompts; with three asks each it cost $0.37 and
  $0.50, so the full run over both sets (350 questions) cost $0.87.
  The same runs on a local 14B model took hours and scored lower (0.283 on all 774
  Stack Exchange questions against Super's 0.387 on 150 of them, both on the 4 Oct prompt).
- **A model is one id in `.env`.** The API is OpenAI-compatible, so the `openai` SDK with
  a `base_url` covers every model. On day one we compared five vision models on our own
  photos by changing the model id. When GLM went quiet on 13 Oct we scored four backups on the
  same 150 photos the same evening (DeepSeek V4.1 Flash won: 0.799 on the 144 photos scored; its run cost $0.44) and
  switched the live backup by id. Moving the chat from Super to Nano was the same kind of
  change, after a 10-case check that cost about $0.07.
- **One bill for the whole chain.** The photo read, the problem check, the three
  advisor asks and the chat all go through one Token Factory key, so a
  free public demo needed only a daily cap and one budget stop.
