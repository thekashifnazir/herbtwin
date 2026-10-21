# Nemotron vision probe: Nemotron 3 Nano Omni against GLM on the photo step (12 Oct 2026)

**Result: GLM-5.3-Flash keeps the live photo step.** Nemotron 3 Nano Omni spots a declining
plant better and reads a photo 5x faster, but names species far less well, does not see
wilting, and fails the two-photo "did it change?" check. Every other model call in the app
is already NVIDIA Nemotron (advice: Nemotron 3 Super; quick calls: Nemotron 3 Nano).

## How it ran

- **Where:** Token Factory has no Nemotron vision model per token (listing checked 12 Oct;
  `nvidia/Nemotron-3_5-Lightning` is new but text only). Its dedicated-endpoint templates do
  offer `nvidia/Nemotron-3-Nano-Omni` (FP8, text + image). We ran one on 1x H100 in
  eu-north1 with `scripts/dedicated_endpoint.py`, then stopped it.
- **Billing:** $4.70 per GPU-hour, charged per minute while the endpoint is ready; setting
  up, stopping and stopped are free ([billing policy][bp], [overview][ov], Token Factory
  Prices page). Ready 13:47:42, stop requested 13:55:23 BST: about 8 minutes, **about
  $0.60**. The fair-comparison GLM re-runs below cost $0.25.
- **Mode:** reasoning off (`HERBTWIN_NO_THINKING_MODELS`). With reasoning on, 6 of 12 gate
  calls returned no JSON within the gate's 1,024-token limit, and the species score did not
  improve.
- **Same instructions:** both models ran today on the same observe prompt (hash
  `44ea8edaea55`), the same photos and the same scorer. Only public photos were sent.

## Results

| Test | GLM-5.3-Flash | Nemotron 3 Nano Omni |
|---|---|---|
| Species top-1, `species_gbif` (150 photos) | **0.867** [0.81, 0.92] | 0.587 [0.51, 0.67] |
| Decline, balanced accuracy, `decline_indoor` (120) | 0.883 [0.82, 0.94] | **0.975** [0.94, 1.00] |
| Droop QWK, `droop_soybean` (180) | 0.28 (4 Oct) | 0.29 |
| Droop recovery, `droop_recovery` (63) | Spearman -0.77 / -0.35 (4 Oct) | droop 0 on all 63 (no signal) |
| Risk gate, 6 garden herbs (same run) | 3/6 zero-shot, 3/6 few-shot | 3/6, 3/6 (same misses) |
| Two-photo compare, public pairs (73) | passed 10/10 posture (C2 gate) | **fail**: posture 1/10 (5/10 reasoning on), colour 7/14, tissue 14/14 |
| Mean time per photo | ~9.4–10.9 s | **~1.6–1.9 s** |

Notes:
- **Species:** Nemotron never named lemon balm (0/10) or garlic chives (0/10), and got
  oregano, tarragon and male fern 2/10. GLM gets 0.9–1.0 on most of those.
- **Two-photo compare:** Nemotron says the second photo shows more change whichever order
  the photos come in. The app's order-swap check catches that and answers "can't tell", so
  it would not give wrong advice, just no answer.
- **Speed** is a dedicated GPU against GLM's shared per-token service, so it is not a like
  for like price comparison: the GPU costs $4.70 an hour whether or not anyone uses it.

## What it would take to switch

Keeping the endpoint up for the live site until judging ends (15 Dec) would cost about
$113 a day. A split (Nemotron for the health read, GLM for the species name) needs the same
always-on GPU. Neither is worth it for this submission.

## Files

- The private working repo's `2026-10-12.json` (both models, reasoning off) and
  the private working repo's `2026-10-12-omni-thinking-on.json`.
- `data/eval/reports/2026-10-12-*-{nemotron-omni,glm-5-3-flash}.{summary.json,md}`.
- `data/eval/reports/2026-10-12-pairs-public-nemotron-omni{,-thinking-on}.json`.
- Endpoint `herbtwin-omni-probe` is **stopped**, not deleted (free while stopped). Start it
  with `uv run python scripts/dedicated_endpoint.py start <id>` (about 5 minutes) if the
  video should show it; stop it the same day.

[bp]: https://docs.tokenfactory.nebius.com/ai-models-inference/dedicated-endpoints/billing-policy.md
[ov]: https://docs.tokenfactory.nebius.com/ai-models-inference/dedicated-endpoints/overview.md
