# Nemotron 3 Nano: Token Factory vs self-hosted on a Nebius job (2026-10-19)

**Self-hosted Nano agrees with Token Factory on 81% of answers (passes the pre-registered bar), but scored slightly worse against the expert answers** (main action matched 4.8 points less often, 95% CI -9.6 to -0.7). Cost: about $1.63 of GPU time, derived from the console's billed B300 preemptible rate (not a per-job line item).
n is 146 because each arm had 2 invalid replies, on different questions, so 150 - 4 pair up.

- Pre-registered in `2026-10-19-nano-selfhost.prereg.md` (fa701d0, before any run), with
  amendments 1-3, all written before the self-hosted run.
- Set `actions_se` (150 Stack Exchange herb questions), advice prompt `7ba44f01d95b`, one ask at
  temperature 0, thinking off in every arm.
- Self-hosted: one Nebius Serverless AI Job (`aijob-e03j4g4yag7nsqaffh`), one spot B300 SXM6
  (275 GB), vLLM 0.30.0, open BF16 weights `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16` served
  under Token Factory's model id, run from git `46602f8`. One job, no preemption.
- Paired files: `2026-10-19-nano-selfhost.compare.json` (Token Factory run A vs self-hosted) and
  `2026-10-19-nano-selfhost.noise-floor.json` (run A vs run A2).

## Primary result

| Pair | Agree on the main action | 95% CI | n |
|---|---|---|---|
| Token Factory A vs Token Factory A2 (noise floor) | 124 (0.838) | 0.777 to 0.899 | 148 |
| **Token Factory A vs self-hosted** | **118 (0.808)** | 0.740 to 0.870 | 146 |

**By the pre-registered rule: the self-hosted model behaves like Token Factory.** Its agreement
with run A, 0.808, is above the threshold of 0.738 (the noise floor minus 0.10). That is a
pass on agreement, not a finding that the advice is the same: see the secondary results.

## Secondary (reported; no claim rule)

| Metric (paired, n 146: 150 minus 2 invalid in each arm) | Token Factory | Self-hosted | Self-hosted minus TF (95% CI) | Same diff, TF vs itself |
|---|---|---|---|---|
| primary_match (vs the expert) | 0.363 | 0.315 | -0.048 (-0.096 to -0.007) | 0.000 (-0.034 to 0.034) |
| primary_in_truth | 0.555 | 0.534 | -0.021 (-0.068 to 0.021) | +0.007 (-0.034 to 0.047) |
| over_treatment | 0.185 | 0.233 | +0.048 (0.000 to 0.096) | +0.014 (-0.041 to 0.068) |
| water_conflict | 0.055 | 0.062 | +0.007 (-0.021 to 0.034) | |
| unguarded_water_conflict | 0 | 0 | 0 | |

- **A small, real-looking drop.** Self-hosted matched the expert's main action 4.8 points less
  often, and its interval just misses zero, while Token Factory against itself moved 0.0.
  It also over-treated a little more (+4.8 points, interval touching zero). Of the 28
  questions that differed, the commonest flips (Token Factory → self-hosted) were "leave it"
  → "treat or remove" (4) and "move to light" → "leave it" (3).
- So the two serving paths agree on the main action nearly as often as Token Factory does
  with itself (0.03 below the noise floor), but the advice is not the same: at temperature 0 the two
  engines differ in numerics, and here that shows as a slight lean to treating.
- Failed or invalid: Token Factory A 2 invalid, A2 0; self-hosted 2 invalid, 0 call errors.
- Wall-clock for 150 questions, 8 workers: Token Factory 49 s (A) and 32 s (A2);
  self-hosted 29 s.

## Cost and time (self-hosted)

| Step | Time (BST, 19 Oct) |
|---|---|
| Job created | 18:21:03 |
| Image pulling (first seen) / running | 18:23:54 / 18:27:12 |
| Weights downloaded (63 GB, 8 min 41 s) | 18:36:06 |
| vLLM ready | 18:38:46 |
| `job.sh check` (valid advice), then the eval | the eval 18:39:15 to 18:39:44 |
| `done`, then `ended`: COMPLETED, no live jobs | 18:39:52 / by 18:40:13 |

- Serving time was about 66 s of a 19-minute job; download and start-up were the rest.
- **Billed rate, derived:** the Nebius console's billing page (read 21 Oct) shows Preemptible NVIDIA
  B300 NVLink, uk-south1, 4.71 GPU-hours = $23.98, so **$5.09 per GPU-hour**. Those 4.71 hours
  cover more than this job (other GPU work in the same period), so the page has no line for
  this job alone: its cost is derived from its own log.
- **This job:** 1 GPU from created (18:21:03) to ended (18:40:13), 19 min 10 s, is **about $1.63**
  before VAT (about $1.95 with 20% VAT). If billing starts only at RUNNING (18:27:12), it is
  about $1.10. The earlier upper bound, 19 minutes at the on-demand $9.50/h, was $3.01.
- The public eval bucket on Nebius Object Storage costs under $0.01 on the same page.
- Token Factory, for the same 150 questions: $0.0139 (A) and $0.0115 (A2).

## What it means for the app

Nothing changes: the app keeps Nano on Token Factory. Self-hosting the open weights on Nebius
AI Cloud works and agrees with Token Factory on 81% of answers, though slightly worse against
the experts, and one 150-question run costs dollars of GPU time, almost all of it start-up, against about a cent on Token Factory.
