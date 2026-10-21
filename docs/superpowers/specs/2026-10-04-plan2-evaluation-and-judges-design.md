# Plan 2: evaluation and judges — design note

- Date: 2026-10-04
- Status: decided under Kash's autopilot grant of 4 Oct ("take the recommendations you
  make"). Every choice below is the recommended option. Kash can reopen any of them: each
  decision has an id (D1 to D12) so it can be named.
- Supersedes: §4 of `2026-10-02-herb-digital-twin-design.md` where they differ, and the
  unapproved design sections 1 to 4 shown in chat on 2 Oct.
- Inputs: `data/external/INDEX.md` (59 holdings, licence tags, clean subsets),
  `data/external/analysis/public-first-eval-map.md` (targets a to k),
  `docs/reference/evaluation-methods.md` (§7: what plan 2 borrows), and the judge findings
  in the private working repo's `HANDOFF.md`.

## 1. What plan 2 has to produce

A harness that answers, with confidence intervals, "how good is each stage of the
pipeline, and how much can we trust the judges that grade it?" on **public data first**,
with Kash's garden crops as the real-garden check. It must run free in the dev loop (local
Ollama, subscription CLIs) and switch to Token Factory only for the final table and demo.

Out of scope for plan 2 (plan 3 territory): twin v2 (seasonal expectation, surface layer,
risk rules), indoor mode, deployment.

## 2. Two tracks

| Track | Measures | Stage under test | Truth | Targets |
|---|---|---|---|---|
| **Perception** | what the vision model sees | `observe` | public labels (expert or class), garden labels as a check | (a) species, (b) droop, (c) decline, (d) colour |
| **Advice** | what the pipeline tells the user | `recommend` (and the free text) | expert answers (MIRAGE, Stack Exchange accepted), literature rules, LLM judges validated against human preference | (f) action, (k) judge calibration |

Perception is built first (D10): its truth is cheap, mechanical and already on disk, and it
gives the first real numbers. Advice needs an extraction step and a validated judge before
its numbers mean anything.

## 3. Decisions

**D1. The harness lives in the package, at `src/herbtwin/evals/`.** The product and the
eval call the same stage functions (the original "eval-native" architecture). No copy of a
prompt exists outside `stages/`.

**D2. An eval set is a tracked JSONL file of item rows, never images.**
`data/eval/sets/<set>.jsonl`, one row per item:

```json
{"id": "droop_soybean/3-106_12_08_2019_06_30_40", "set": "droop_soybean",
 "path": "s4/data/full_data/3-106_12_08_2019_06_30_40.jpg", "root": "external",
 "label": {"droop": 0, "raw": 0}, "cluster": "3-106", "licence": "CC BY 4.0",
 "tag": "safe-to-train", "source": "Zenodo 8256382"}
```

`path` is relative to a named root (`external` = `data/external/`, `photos` =
`data/photos/`). Items whose file is missing are counted and reported as `missing`, never
silently dropped, so the harness runs on any machine and says how much of the set it saw.
Sets are built by `scripts/build_eval_sets.py` from local holdings with a fixed seed;
rebuilding on the same holdings gives the same file (tested).

**D3. Licence tags travel with every item.** `tag` is `safe-to-train`, `test-only` or
`owner`. A report shows counts per tag. Nothing marked `test-only` is ever copied into
the repo, a page or a few-shot prompt that ships.

**D4. The first perception sets (v1):**

| Set | Holding | Items | Label | Metric |
|---|---|---|---|---|
| `droop_soybean` | `s4` soybean wilt (S) | 180, stratified 30 per raw level 0 to 5, cluster = plot (10 plots) | expert 0 to 5, mapped 0→0, 1–2→1, 3–4→2, 5→3 | quadratic-weighted kappa (QWK) on the mapped 0 to 3, plus exact and within-one accuracy and MAE |
| `droop_recovery` | `s10` Fittonia watered, `s9` basil (S) | all usable frames (40 + 23), one clip per cluster | frame order after watering | Spearman of predicted droop against time (expected negative), per clip, **no CI** (two clips cannot carry a bootstrap) |
| `decline_indoor` | `s11` Mendeley indoor diseases (S) | withering 86 (snake plant) + tip necrosis 91 (spider plant) vs those species' healthy classes (89, 92), sampled to 60 per side, cluster = image (one photo per leaf) | decline present yes/no | precision, recall, specificity, balanced accuracy |
| `species_gbif` | `s6` GBIF (S) | 10 per species x 15 = 150 from rows with `status == ok`, cluster = species | accepted name (WCVP synonyms) | top-1, top-3, genus top-1 |
| `garden_v1` | owner crops, root `external`: `garden_crops/img/` and `garden_crops/pass_20261003/img/` | 183 (186 scored in v1, minus the 3 calibration crops c033, c038, c046) | v1 condition score | QWK as a transfer check only; **never tuned against** (v1 mixes droop and decline) |

Each later set (colour from AgEval and PlantInquiryVQA, pests from `herb_pd_refs`, garden
v2 once Kash has scored it) is one builder function and one row in this table.

**D5. Observation gains two fields: `decline` (0 to 3) and `leaf_colour`
(`green` / `some_yellow` / `mostly_yellow` / `not_visible`).** The garden rubric v2 and the
decline sets need them; without them a droop score has to carry dieback too, which is the
v1 labelling mistake again. `water_stress` keeps its name and is defined as posture only
(droop). Both fields are `required` in `OBSERVE_SCHEMA`, so a live model must answer them; the
pydantic defaults (`0`, `not_visible`) exist only so recorded responses still parse. The
runner marks a live reply that omits either field as `failed`, never as "no decline":
silently defaulting would inflate specificity and hide misses.

**D6. Metrics are implemented in-house in `evals/metrics.py`, pure Python.** QWK, exact
and within-one accuracy, MAE, Spearman, precision and recall, top-k, and a **cluster
bootstrap** CI (resample clusters, 2,000 draws, fixed seed, percentile 95%). Sets are a few
hundred items; no numpy dependency is earned yet. Parse failures and model errors are
their own counted outcome (`failed`) and are reported beside every metric, never dropped. The
bootstrap also reports how many draws it skipped because the statistic was undefined
(kappa on a one-level sample); a large share is flagged in the report.

**D7. A run is resumable and cached by key.** Key = set item id + model id + backend +
prompt hash (system, user and schema of the stage). Raw per-item results go to
`data/eval/runs/<run-id>.jsonl` (gitignored; they may hold model text about test-only
images). The summary (`<run-id>.summary.json`) and a short markdown report are tracked
under `data/eval/reports/`. A prompt edit changes the hash, so stale results are never
mixed in.

**D8. Backends for the dev loop: an Ollama adapter (OpenAI-compatible, local, free).**
`HERBTWIN_BACKEND=ollama`, model from the same `HERBTWIN_*_MODEL` settings, base URL
`HERBTWIN_OLLAMA_BASE_URL` (default `http://localhost:11434/v1/`). First baseline:
`qwen2.5vl:7b`, the local model already used for the garden judge. Subscription CLI
adapters (Claude, Codex) are ported from the marker eval repo when the advice track needs
a judge from another family. Token Factory runs only for the final table, with a cost
quote first (D12).

**D9. The run reports the human ceiling beside every judge figure where one exists.**
Garden: Kash's round 2 self-agreement (around 10 Oct). Soybean: no published rater
agreement is recorded; Bock 2015's rater spread is cited as context only. A model whose
CI sits inside the ceiling is reported as "at human level", never "better".

**D10. Build order.** (1) eval core: item schema, set loader, metrics, report;
(2) Observation fields (D5); (3) Ollama adapter and the run CLI; (4) set builders and the
tracked v1 sets; (5) first free baseline run on `qwen2.5vl:7b`, report tracked;
(6) advice track (D11); (7) final paid table (D12).

**D11. Advice track design (built after the perception baseline).**
- *Action truth:* extract an action class from each MIRAGE Plant Care answer and each
  Stack Exchange accepted diagnosis answer with a local model: `water` / `dont_water` /
  `move_light` / `shelter` / `treat_or_remove` / `prune` / `leave_normal` / `ask_first`.
  Hand-check a stratified 50 by the agent against the answer text (not by Kash: an
  extraction check is reading comprehension, not a care judgement) before trusting it.
  MIRAGE is test-only until its licence is confirmed.
- *Free-text rubric:* the six lines from the 2 Oct spec rewritten as weighted checklists
  with three anchors (yes / partly / no) and negative items for over-treatment and
  confident error, per evaluation-methods §7. The 1 to 5 per line is derived from points.
- *Judge validation first:* every judge is scored on the Stack Exchange preference pairs
  (3,990; 228 diagnosis), both orders, before its rubric scores count. Report pairwise
  accuracy, position-swap rate and repeat agreement. A judge below 0.6 pairwise accuracy
  on diagnosis pairs is dropped, not averaged in.
- *Held-out rule:* a judge never shares a model family with the model under test.

**D12. Paid runs.** The final table runs the v1 sets once on the Token Factory models in
`.env` (observe on GLM-5.3-Flash). A cost line is printed before any paid run by
`--dry-run`, from the adapter's price table and the mean tokens of the free run, and the
run waits for Kash's yes. LangSmith experiments and the Toloka lay panel are modules for
week 3, not plan 2's critical path.

## 4. Report shape

One header block (run id, set, git SHA, backend, model id, prompt hash, temperature, n
total / scored / missing / failed, licence tag counts), then one row per metric with its
95% cluster-bootstrap CI and the human ceiling where known, then the five largest
disagreements by id. Markdown for reading, JSON for diffing runs.

## 5. Testing

- Metrics: hand-computed cases (perfect agreement QWK = 1, reversed scale < 0, a known
  2x2 kappa), bootstrap determinism under a fixed seed, cluster resampling keeps clusters
  whole.
- Sets: builder determinism on a tiny fixture tree under `tests/fixtures/external/`;
  missing-file accounting.
- Runner: a mock adapter run over a 5-item fixture set produces the expected summary;
  a second run hits the cache and makes no calls; a prompt change misses it.
- Ollama adapter: request shape tested with respx, like the Token Factory adapter.

## 6. Risks

- `qwen2.5vl:7b` scored the garden nearly two-level (0 or 2). Expect a low soybean QWK;
  that is a finding, not a harness bug. The harness must make that visible (score
  histogram in the report).
- Soybean is a top-down field canopy. A good soybean score does not prove potted-herb
  droop; the garden check and the recovery clips are what test transfer.
- Ten soybean plots make the cluster CI wide. That is honest; report it.
