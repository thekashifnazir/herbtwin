# Photo model outage and the backup model (13 Oct 2026)

## What happened

On 13 Oct, during a walkthrough of the live site (revision `herbtwin-00014`), both photo
uploads (07:30 and 07:37 UTC) stuck on "Reading the photo" and never finished.

| Time (UTC) | Event (Cloud Run logs) |
| --- | --- |
| 07:30:21 | `POST /analyse` starts streaming the progress page |
| 07:33:23 | `retrying zai-org/GLM-5.3-Flash once after transport error` (180 s timeout) |
| 07:35:23 | `Truncated response body`: Cloud Run's 300 s request limit cuts the page |
| 07:37:06 → 07:42:09 | the second upload: the same sequence |

The page showed no error, and nothing reached My plants.

## Finding the cause

- The Token Factory gateway was up: `GET /v1/models` returned 401 (no key sent) in 0.07 s.
- A direct call to each model, one at a time, with the same key and endpoint:

  | Model | Result |
  | --- | --- |
  | `zai-org/GLM-5.3-Flash` | no reply, cut off at 60 s (HTTP 000) |
  | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | HTTP 200 in 0.18 s |

- At the same time, Ask about this plant and Check the advice again (Nemotron 3 Super) both
  worked. Only the photo model was down, on Token Factory's side.

Two faults in our own code turned that outage into a page that hung for ever:

1. A timed-out call was retried. Two waits of 180 s each (360 s) are longer than Cloud
   Run's 300 s limit, so the page could never show its own error. Fixed in
   `fix/photo-read-timeout` (#107): no retry after a timeout, and the progress page gives
   up at 270 s with "the photo read took too long" and a Try again link.
2. There was only one photo model. Fixed here: a backup model reads the photo when the
   first one fails.

## Choosing the backup

The candidate had to be a vision model on Token Factory (the hackathon rules count Token
Factory calls; NVIDIA Nemotron still writes all the advice). Token Factory lists no
per-token Nemotron vision model.

Risk gate (`scripts/risk_gate.py`): 6 garden herbs, species top-1, pass = 4 of 6.

| Model | 2 Oct zero / few-shot | 13 Oct zero / few-shot |
| --- | --- | --- |
| `zai-org/GLM-5.3-Flash` | 4 / 5 (3 Oct: 4 / 3; 12 Oct: 3 / 3) | down |
| `google/gemma-3-27b-it` | 4 / 4, no JSON errors | 3 / 3, no JSON errors |
| `openbmb/MiniCPM-V-4_5` | 2 / 3 | not run |
| `Qwen/Qwen3.8-27B` | 2 / 4, 1 JSON error | not run |

On 13 Oct, Gemma's misses were chives (it named common chives, not garlic chives; GLM
also missed this on 12 Oct), mint (read as basil) and lemon balm. The report is
the private working repo's `2026-10-13.json`.

Gemma through our own observe stage, on the judge sample photos:

| Photo | Gemma read | Time |
| --- | --- | --- |
| 1 parsley | Petroselinum crispum ✓ | 10.5 s (51 s on an earlier try) |
| 3 basil | Ocimum basilicum ✓ | 6.5 s |
| 4 rosemary | Thymus vulgaris ✗ (thyme) | 5.0 s |
| 5 coriander | Coriandrum sativum ✓ | 13.7 s |

Each read cost about $0.0001 and gave valid JSON on the first try. Gemma is a little
weaker than GLM at naming the species, so it is the backup, not the replacement. The
answer page already shows how sure the read is.

## How the backup works

- `FallbackAdapter` (`src/herbtwin/adapters/fallback.py`) asks the first model. On any
  model error (a timeout, an outage, a cut-off reply), it logs a warning and asks the
  backup once. For the next 5 minutes the backup goes first, so a silent model costs its
  timeout once, not on every JSON repair and every upload. After that, the first model
  is tried again; if it fails again, the skip triples (5, 15, 45 minutes, then an hour
  at most), and one good answer resets it. A reply cut off at max_tokens is a long
  answer, not an outage, so it always gets the flat 5 minutes. GLM stayed down all of
  13 Oct, and with a flat 5 minutes every upload after a quiet spell waited 90 s first. Each call is traced under the model that made it, so LangSmith and
  `traces.db` show which model read each photo.
- `HERBTWIN_OBSERVE_FALLBACK_MODEL` names the backup. `HERBTWIN_OBSERVE_TIMEOUT_S` is
  how long each photo model gets (90 s live). Local GLM photo reads took about 18 s, and
  spot reads up to 92 s, so a very slow spot read is handed to the backup rather than waited
  for.
- Live worst case after the DeepSeek switch: see
  [the new decision below](#switching-the-backup-to-deepseek-v41-flash-13-oct-evening).
  This depends on #107: a timed-out call is no longer retried.
- The photo read, the spot read and the "Did you do it?" photo comparison all use the
  same adapter, so all three get the backup.
- The private working repo's `test_deploy_scripts.py` checks that the live config has a backup and that two
  photo-model waits fit inside the request limit.

## Live check (13 Oct, revision `herbtwin-00015-d4h`)

Both fixes went live at 09:50 UTC, while GLM-5.3-Flash was still down.

| Time (UTC) | What happened |
| --- | --- |
| 09:51:01 | The deploy script's own check sends a test photo to `/analyse` |
| 09:52:32 | `zai-org/GLM-5.3-Flash failed (zai-org/GLM-5.3-Flash: Request timed out.); reading with google/gemma-3-27b-it for the next 300 s` |
| 09:52:33 | The check lands on an answer, 92 s after it started (90 s wait for GLM, then Gemma) |
| 09:53:06 | A real upload (judge sample 3, basil) goes straight to Gemma, because GLM is still in its 5-minute skip |
| 09:53:47 | The answer page opens: Sweet Basil (*Ocimum basilicum*), 41 s from upload |

Earlier the same morning, the same upload hung until Cloud Run cut the page at 300 s.

## Switching the backup to DeepSeek V4.1 Flash (13 Oct, evening)

Gemma called the rosemary-beetle photo thyme and marked it fine in all three judge runs.
GLM was still down, so live reads were already landing on the backup. DeepSeek read all
five judge-sample species in all three runs and got the rosemary beetles right. GLM
stays first; its GBIF top-1 reference is 0.867 (95% CI 0.813–0.920).

The GBIF set has 150 items: 144 DeepSeek reads scored, one photo was missing, and five
calls (3%) timed out at the eval's 60 s limit. The reports are in `data/eval/reports/`.

| Model | Top-1 (95% CI) | Top-3 (95% CI) | Mean / p50 / p95 / max latency | Run cost |
| --- | --- | --- | --- | --- |
| DeepSeek V4.1 Flash | 0.799 [0.729, 0.861] | 0.889 [0.840, 0.938] | 14.1 / 10 / 37 / 60 s | $0.435281 |
| Gemma 3 27B | 0.599 [0.517, 0.680] | 0.782 [0.714, 0.850] | 5.0 / 4 / 9 / 30 s | $0.018168 |
| Qwen3.8-27B | 0.577 [0.497, 0.658] | 0.664 [0.584, 0.738] | 6.0 / 5 / 14 / 20 s | $0.9023 |
| MiniCPM-V-4_5 | 0.396 [0.322, 0.477] | 0.570 [0.497, 0.644] | 2.4 / 2 / 3 / 3 s | $0.089952 |

The latency columns are mean, p50, p95 and maximum. The mean comes from each report;
the percentiles come from the run rows (`data/eval/runs/`, gitignored).

| Model | Judge-sample result | Read time |
| --- | --- | --- |
| DeepSeek V4.1 Flash | Named all five plants 3/3. On sample 4, read *Salvia rosmarinus* and beetles/damage 3/3; decline 1, not fine. | 6–60 s |
| Gemma 3 27B | Read sample 4 as *Thymus vulgaris* and fine, 3/3. | 7–11 s |
| Qwen3.8-27B | Named rosemary on sample 4 3/3, but saw beetles 1/3. | — |
| MiniCPM-V-4_5 | Read sample 5 coriander as *Valerianella locusta*. | — |

Kimi-K3 was dropped before the full run. It read sample 4 as lavender and costs $3/$15
per million input/output tokens. Kimi-K2.6 failed observe JSON validation: its species
items came back as strings. The sample-4 photo stays unchanged. Two of its 12 Wikimedia
CC images show the plant, and Gemma read both as thyme.

The live worst case is 90 s for a silent GLM read, up to 60 s for DeepSeek, then up to
about 60 s for the gated problem check's second vision call, followed by advice. This is
close to the page's 270 s limit. It happens only on the first read after a cool-off
pause. Live, each photo model gets 90 s, and 3% of DeepSeek's eval reads took over 60 s. A
read that slow after a silent GLM shows the page's "the photo read took too long" with
Try again. Gemma was much faster (p95 9 s), so this trades speed for a much better read.

### DeepSeek's spot read and problem check (14 Oct)

Run on Kash's Mac (the photos are only there), DeepSeek as the only photo model
(`HERBTWIN_OBSERVE_MODEL` set, no backup, 90 s), through shell variables so `.env` was not
edited. Summaries: `data/eval/reports/2026-10-14-spot-read.summary.json` and
`2026-10-14-problem-check.summary.json`. About $0.73 together.

| Spot read (226 photos) | Gemma 3 27B (13 Oct) | DeepSeek V4.1 Flash | GLM (reference) |
|---|---|---|---|
| Setting right (target 0.90) | 0.778 | **0.943** | 0.93 |
| Pots and troughs read right | 67/85 (0.79) | **80/83 (0.96)** | — |
| Pots read as open ground or a bed | 16 | **3** (all "raised bed") | — |
| Compost called soil (target 0) | 3 | 1 | 1 |
| Soil called compost | 0.127 | 0.045 | — |
| Failed reads | 1 | 3 | — |

**DeepSeek reads pots well enough that the spot page's "Is it in a pot or in the ground?"
check (asked when the backup read the photo, `FallbackAdapter.used_backup`, #116) is no
longer needed for it.** It was added because Gemma read pots as open ground. Dropping it
is a separate change, not made here.

| Problem check | Gemma 3 27B (13 Oct) | DeepSeek V4.1 Flash |
|---|---|---|
| Problems named right (of 102 photos in 5 classes) | 23 | 19 |
| Named wrongly | 7 | **1** (sage read as "leafhoppers") |
| False alarms on 150 healthy photos | 0 | 0 |
| Check failed (no JSON in the reply) | 0 | 2 |
| Judge sample 4, rosemary beetles | missed | **named** |
| Judge sample 6, basil downy mildew | named (live, 13 Oct) | **missed** |

By class (right / 24): downy mildew 11 → 6, mint rust 7 → 11, powdery mildew 4 → 0, aphids
1 → 2 (of 6), slugs 0 → 0. DeepSeek names fewer problems but is wrong far less often
(1 of 20 named vs 7 of 30). The miss that matters is sample 6: the judges' "Could be basil
downy mildew" demo photo gets no box on DeepSeek in this run. Re-check it live after the
deploy; if it stays missed, the judges' notes for sample 6 need changing (or GLM must be
back).
