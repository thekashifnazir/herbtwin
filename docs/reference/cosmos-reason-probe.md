# Cosmos Reason probe: NVIDIA Cosmos-Reason2-32B against GLM on the photo step (15 Oct 2026)

**Result: GLM-5.3-Flash keeps the live photo step.** Cosmos-Reason2-32B, the newest Cosmos
Reason model, named the species in 0.574 of 148 public photos, against GLM's 0.867. That is
level with Nemotron 3 Nano Omni (0.587). It is as good as GLM at spotting a declining plant
(balanced accuracy 0.892 against 0.883) and reads a photo 3x faster on its own GPU. The
older Cosmos-Reason1-7B scored 0.540. Eval only: nothing in the live product changed.

One line for the write-up: *we served NVIDIA Cosmos-Reason2-32B with vLLM in a preemptible
Nebius AI Cloud job on one B300 and scored it on our own 150-photo species set and
120-photo decline set, with the same prompt and scorer as our live model, for about $1 of
GPU time.*

## Which model

- **Cosmos-Reason2-32B** (`nvidia/Cosmos-Reason2-32B`, released on Hugging Face 29 Apr
  2026). This is the current Cosmos Reason release: Reason2 also comes in 2B and 8B (Dec
  2025), and Reason1-7B (Apr 2025) is the earlier one. It is post-trained from
  Qwen3-VL-32B-Instruct, 32B parameters, BF16 (about 64 GB of weights), text + image +
  video in, text out.
- **Licence:** NVIDIA Open Model License: commercial use allowed, no claim on outputs.
  Anyone who redistributes the model or ships a product built on it must include the
  notice "Licensed by NVIDIA Corporation under the NVIDIA Open Model License" and the line
  "Built on NVIDIA Cosmos".
- **Second arm:** Cosmos-Reason1-7B (Qwen2.5-VL-7B base, same licence), served in the same
  job, to see what the newer release gained.
- **Not tried:** the Cosmos 3 reasoner tower (`Cosmos3-Super-Reasoner`, a Token Factory
  dedicated-endpoint template, or Cosmos3-Edge/Nano through vLLM-Omni). It is a different
  serving stack and was outside this budget.

## How it ran

- **Where:** Nebius AI Cloud Serverless AI Jobs, `gpu-b300-sxm` / `1gpu-24vcpu-346gb`,
  preemptible at spot price, image `vllm/vllm-openai:v0.30.0`. B300 is the only GPU quota
  in this project. It costs $9.50 an hour on demand, so spot is the only way to stay
  inside the budget.
- **Serving:** `scripts/cosmos_reason/serve.sh` is the job's container command. It
  downloads the weights (no token: see the first snag), serves each model in turn with
  vLLM on port 8000 (`--max-model-len 16384`, up to 2 images a prompt) and exits after the
  last one, or after 50 minutes.
- **Scoring:** the laptop ran the repo's own `scripts/eval.py` through an SSH tunnel to the
  job (`scripts/cosmos_reason/probe.sh tunnel`), with `--backend ollama` pointed at the
  tunnel. So the observe prompt (hash `44ea8edaea55`), the JSON schema (vLLM structured
  output), the 1,024 px resize, temperature 0, the repair call and the scorer are the same
  as GLM's and Nemotron's 12 Oct runs. Reasoning was not asked for. Cosmos Reason only
  thinks when the prompt asks for `<think>` tags, so this matches the "reasoning off" runs.
- **Photos:** only the public eval sets went through the tunnel: `species_gbif` (GBIF,
  CC0/CC BY) and `decline_indoor` (Mendeley, CC BY 4.0). No garden photos, and no keys
  were sent to the job.

## Results

| Test | GLM-5.3-Flash (12 Oct) | Nemotron 3 Nano Omni (12 Oct) | **Cosmos-Reason2-32B** | Cosmos-Reason1-7B |
|---|---|---|---|---|
| Species top-1, `species_gbif` (150) | **0.867** [0.81, 0.92] | 0.587 [0.51, 0.67] | 0.574 [0.49, 0.66] | 0.540 [0.46, 0.62] |
| Species top-3 | **0.947** | n/a | 0.628 [0.55, 0.71] | 0.653 [0.58, 0.73] |
| Genus top-1 | **0.907** | n/a | 0.743 [0.67, 0.81] | 0.607 [0.53, 0.68] |
| Decline, balanced accuracy, `decline_indoor` (120) | 0.883 [0.82, 0.94] | **0.975** [0.94, 1.00] | 0.892 [0.84, 0.94] | not run |
| Mean time per photo | ~9.4 s (shared service) | ~1.6–1.9 s (own H100) | ~3.1 s (own B300) | ~1.2 s (own B300) |

All intervals are the harness's 95% bootstrap. Notes:

- **Species:** 2 of 150 Cosmos-Reason2-32B replies were invalid JSON even after the repair
  call, so the score is over 148. Counting those two as wrong gives 0.567. Cosmos-Reason1-7B
  returned valid JSON for all 150.
- **Where it misses:** it got none right for male fern, soft shield fern (it names other
  ferns) or thyme (it says *Thymus serpyllum* 8 times out of 10), and 1 of 10 for garlic
  chives (*Allium neapolitanum* 5 times). It sometimes gives a common name ("rosemary",
  "tarragon") where the schema asks for a Latin name. The scorer still matched rosemary;
  some others counted as wrong. GLM's weak spots were tarragon and soft shield fern
  (0.4 each).
- **Decline:** precision and specificity were both 1.000 (it never called a healthy
  plant declining). Recall was 0.783: it missed about 1 in 5 withering snake plants. That
  makes it level with GLM, and below Nemotron Omni.
- **Bigger and newer helped only a little:** Reason2-32B against Reason1-7B is +0.034 on
  species top-1, inside the noise, and +0.14 on genus. The Cosmos training data (driving,
  robots, warehouses, egocentric video) has little botany in it. This is the same lesson
  as the 12 Oct Cosmos 3 video probe: Cosmos is built for physical AI, not plant names.

Reports: `data/eval/reports/2026-10-15-{species_gbif,decline_indoor}-cosmos-reason2-32b.{md,summary.json}`
and `data/eval/reports/2026-10-15-species_gbif-cosmos-reason1-7b.{md,summary.json}`. The
run rows are gitignored, in the worktree's `data/eval/runs/`.

## Cost

| Job | Created → ended (UTC) | What happened | B300 minutes |
|---|---|---|---|
| Job 1 | 13:18:50 → ~13:48 | image pull, 64 GB download, ready 13:41, 88 photos scored, then **preempted** | ~29 |
| Job 2 | 13:59:32 → 14:37:12 (cancelled) | ready 14:20; 62 + 120 photos on 32B, then 150 on 7B | ~38 |

- **About 67 B300 spot minutes, about 1.1 GPU-hours: about $1.10** at the listed spot
  price ("from $0.99" an hour). Spot prices move and the CLI does not show the price, so
  the Nebius billing page has the exact figure. Even at twice that rate it stays under
  $2.50, well inside the $5 cap. Disks belonged to the jobs and went with them.
- **Token Factory: $0.** GLM's and Nemotron's numbers come from their 12 Oct runs on the
  same prompt hash, so nothing was re-run.
- **Useful work was about 22 of the 67 minutes.** The rest went to the image pull,
  downloading weights twice (once per job), loading the model, and the preempted half
  run.

## Setup snags (the tool feedback)

1. **Hugging Face gating is uneven across one model family.** Cosmos-Reason2-2B and 8B are
   gated: they return 401 without a token, and this account has not been granted 8B.
   Using them would have needed an HF token in MysteryBox, which is Kash's job. The 32B
   card shows the same licence click-through, but its weights download without a token.
   It took about 10 minutes of checks to find a size that needed no secret.
2. **Spot B300 was preempted 28 minutes in**, halfway through the eval. The first sign was
   the SSH tunnel dropping ("closed by remote host"). For about 3 minutes after that the
   job still said RUNNING, and only then changed to `FAILED: Preempted`. The eval cache
   kept the 88 finished photos, so only the 62 failed calls were retried. But a new job
   meant pulling the image and downloading 64 GB again: about 20 minutes and about $0.35
   lost. The 14 Oct fine-tune probe saw 2 preemptions in 5 B300 spot jobs.
3. **Startup dwarfs the work.** From create to a running container took 6–7 minutes
   (provisioning plus pulling the vLLM image). The 64 GB
   download took 13.5 minutes on the first job, where vLLM and a background prefetch were
   both fetching the same weights. With one download at a time it took 9.5 minutes.
   Loading and compiling took 5 minutes. Scoring 150 photos took 5–8 minutes. Jobs have
   no weight cache between runs unless you set up a shared filesystem, which would be
   worth it for a second run.
4. Smaller ones: only B300 quota, so the cheaper L40S and H100 rates can't be used; the
   only way back from a job is SSH (the container sits on a Docker bridge network, so
   the tunnel goes through the host to the container's IP); `--container-port` would
   open vLLM on the public IP with no auth; and the job's timeout can't be set below
   1 hour, so `serve.sh` has its own 50-minute cap.

What worked well: once it was up, vLLM 0.30 served Qwen3-VL-based Cosmos with no extra
flags, structured JSON output worked first time, and the OpenAI-compatible API meant the
repo's eval harness needed no code change.

## Verdict

Cosmos-Reason2-32B is a capable general vision-language model, not a plant identifier.
On our photos it is level with Nemotron 3 Nano Omni on species, level with GLM on decline,
and well below GLM on naming the plant, which is the step the app needs most. Serving it
live would also need an always-on GPU (about $24 a day even at spot price, and spot can be
taken back). So the live photo step stays on GLM-5.3-Flash per token. The honest story for
judges is that we tried NVIDIA's physical-AI reasoner, measured it on our own sets, and
kept the model that names plants best.

## Re-run

```bash
ssh-keygen -t ed25519 -N "" -f /tmp/cosmos-key
scripts/cosmos_reason/probe.sh create /tmp/cosmos-key.pub      # prints the job id
scripts/cosmos_reason/probe.sh log JOB /tmp/cosmos-key          # wait for READY
scripts/cosmos_reason/probe.sh tunnel JOB /tmp/cosmos-key &     # localhost:18000
ln -s "$MAIN/data/external" data/external                       # in a worktree
HERBTWIN_OLLAMA_BASE_URL=http://localhost:18000/v1/ uv run python scripts/eval.py \
  --set species_gbif --backend ollama --model nvidia/Cosmos-Reason2-32B
scripts/cosmos_reason/probe.sh next JOB /tmp/cosmos-key         # serve the next model
scripts/cosmos_reason/probe.sh cancel JOB                       # stop billing now, not at HOLD_MIN
```
