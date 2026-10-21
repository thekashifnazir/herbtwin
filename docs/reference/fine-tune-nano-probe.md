# Fine-tune probe: a LoRA-tuned Nemotron 3 Nano 4B against Nemotron 3 Super (14 Oct 2026)

**Result: on picking the main action, the tuned 4B is level with the live advisor; it still
over-treats more on one set.** Nemotron 3 Nano 4B, LoRA-tuned on 242 answers from the live
advisor (`nvidia/nemotron-3-super-120b-a12b`) that matched the experts, scored
**0.400 against Super's 0.440** on 150 held-out Stack Exchange questions and **0.420 against
0.435** on 200 MIRAGE questions. Both gaps are inside the noise. Tuning cut the untuned 4B's
over-treatment from 19% to 9% (Stack Exchange) and from 18% to 2% (MIRAGE). On Stack
Exchange it still over-treats more than Super (8.7% against 2.0%), so it fails the brief's
"no worse" bar there. The live advisor does not change: serving a tuned model needs a
dedicated GPU (see the last section). Total spend about $6 of the $25 cap.

One line for the write-up: *a 4B Nemotron tuned on 242 expert-matched answers matched
Nemotron 3 Super's main-action accuracy on 350 held-out questions (0.40 and 0.42 against
0.44 and 0.435) and cut its own over-treatment by more than half, trained and scored in one
Nebius GPU job for about $2.*

## How it ran

- **Probe first** (brief: the private working repo's `2026-10-12-fine-tune-small-model.md`).
  The prompt changed since the old baseline (`b1b-se-150`, prompt `114a377a8a65`), so Super
  was re-run on today's prompt (`7ba44f01d95b`) before any comparison.
- **Teacher data:** Super answered the 624 Stack Exchange questions outside the held-out
  150 (`--asks 3`, the app's panel). The 242 whose main action matched the expert became
  examples (`scripts/build_finetune_data.py`; `src/herbtwin/evals/finetune_data.py`). An
  example is the exact eval prompt (system + user, no photo) and Super's JSON reply.
  The held-out 150 and every MIRAGE id are excluded (a test checks it). Class mix:
  leave_normal 74, treat_or_remove 55, change_soil 22, prune 18, move_light 16, others 57.
- **Training:** one Nebius Serverless AI job, `gpu-b300-sxm` / `1gpu-24vcpu-346gb`,
  preemptible (B300 is the only GPU quota in the project). Image `vllm/vllm-openai:v0.30.0`
  (torch 2.13 cu130, transformers 5.17), native transformers NemotronH (no remote code),
  PEFT 0.21 + TRL 1.13 SFT, completion-only loss. LoRA r=16, alpha 32, on q/k/v/o, up/down
  and the Mamba `in_proj`; not `out_proj` (the fused kernel reads it directly, so NVIDIA's
  own recipe leaves it out). 3 epochs, batch 1 x 8 accumulation, lr 2e-4 cosine: 93 steps,
  32 minutes, loss 1.14 to 0.59. Scripts: `scripts/finetune/{train,run,boot,pack,ship}.*`.
- **Scoring:** in the same job, vLLM served the untuned 4B, then the merged tuned 4B, on
  localhost with thinking off (the model's chat template with `enable_thinking` defaulting
  to false). The repo's own `scripts/eval_advice.py` scored each (`--asks 3`), so prompt,
  repair call, panel vote and metrics are the ones Super was scored with. Reports were
  rebuilt locally from the job's rows (all cache hits). Paired differences are b minus a
  with a 95% bootstrap interval over questions (`scripts/compare_advice.py`).

## Results

Main action matched the expert (`primary_match`), 95% interval:

| Model | Stack Exchange, 150 | MIRAGE, 200 | Cost to run the eval |
|---|---|---|---|
| Nemotron 3 Super (live advisor) | **0.440** [0.36, 0.52] | **0.435** [0.37, 0.51] | $0.41 + $0.55 |
| Nemotron 3 Nano 30B-A3B | 0.420 [0.34, 0.50] | not run | $0.19 |
| Nemotron 3 Nano 4B, untuned (vLLM) | 0.367 [0.29, 0.45] | 0.337 [0.27, 0.40] | in the GPU job |
| Nemotron 3 Nano 4B, **tuned** (vLLM) | 0.400 [0.32, 0.48] | 0.420 [0.35, 0.49] | in the GPU job |

The untuned 4B on Ollama (bf16, free on the laptop) scored 0.380, close to its vLLM 0.367.

Paired differences (b minus a):

| Comparison | Set | primary_match | over_treatment | unguarded_water_conflict |
|---|---|---|---|---|
| Super → tuned 4B | SE 150 | -0.040 [-0.127, +0.047] | **+0.067** [+0.027, +0.113] | +0.007 [0, +0.020] |
| Super → tuned 4B | MIRAGE 200 | -0.015 [-0.080, +0.050] | +0.010 [-0.010, +0.030] | 0.000 [-0.015, +0.015] |
| untuned → tuned 4B | SE 150 | +0.033 [-0.047, +0.113] | **-0.107** [-0.173, -0.047] | +0.007 [0, +0.020] |
| untuned → tuned 4B | MIRAGE 199 | **+0.080** [+0.005, +0.156] | **-0.156** [-0.206, -0.111] | +0.005 [0, +0.015] |
| Super → Nano 30B | SE 150 | -0.020 [-0.087, +0.047] | **+0.053** [+0.020, +0.093] | +0.007 [0, +0.020] |

Notes:
- **Against the brief's bar** (within 0.05 of Super with an interval containing 0, and
  over-treatment and unguarded water conflicts no worse): main action passes on both sets.
  Over-treatment passes on MIRAGE and fails on Stack Exchange. Unguarded water conflicts:
  one extra question on Stack Exchange (1 of 150), none extra on MIRAGE.
- **What tuning bought** is mostly restraint: the untuned 4B reaches for a treatment on
  about 1 question in 5. The tuned one learned Super's "leave it" more often.
- **Distillation ceiling:** the tuned model can at best copy Super. With 242 examples it
  got most of the way there on the main action.
- **Valid output:** a few single asks (about 4% for the untuned model) came back without
  JSON even after the repair call; the three-ask panel absorbed them. One untuned MIRAGE
  question failed outright (counted invalid).

## Spend

- **Token Factory: $3.08.** Nano 30B probe $0.19; Super re-runs $0.41 (SE) and $0.55
  (MIRAGE); teacher run $1.07 + $0.86 (two shards, each under the $2 rule; about $0.20
  of that re-bought already-paid rows by mistake).
- **AI Cloud GPU: about $2 to $3** (estimate: about 2.1 B300 spot-hours at roughly $1.06
  an hour, the rate implied by the 12 Oct Cosmos jobs; the Nebius billing page has the
  exact figure). Six jobs: one CPU SSH test (cancelled), three smoke jobs (one preempted
  during the image pull, one lost to a `python` vs `python3` slip), one full job preempted
  at training step 1, and the full job that finished (about 51 minutes).
- **Nothing left running:** every job cancelled or finished, no endpoints, no disks, no
  instances (checked 14 Oct 02:20 UTC).

## Gotchas, for the next GPU job

- `--inject-file` is limited to **64 KiB for all files together**, not each. The payload
  (code + eval questions + training file, 0.68 MB) went in over SSH instead: the job's
  host VM has a public IP, `sudo` and docker, so `ssh nebius@IP` then `docker cp` into the
  job container works (`scripts/finetune/ship.sh`). Results came back the same way.
- Spot B300 was preempted 2 times in 5 GPU jobs. The adapter (80 MB) is copied off as soon
  as training ends, and `run.sh` merges a shipped-in adapter instead of retraining.
- The vLLM image has `python3` but no `python`, and no `git`.
- TRL 1.13 dropped `warmup_ratio` (use `warmup_steps`). The base model's
  `generation_config.json` (top_p without do_sample) will not save under transformers 5:
  set `do_sample=True` before saving the merged model.
- Without `mamba-ssm` kernels, transformers runs the reference PyTorch scan: slow (about
  20 s a step) and memory-hungry. A batch of 4 long prompts tried to allocate 77 GB; batch
  1 with gradient accumulation was fine.
- The eval's local adapter sends `reasoning_effort: "none"`, which vLLM may reject; run
  `eval_advice.py --think` and turn thinking off in the served chat template instead.

## What it would take to switch

Token Factory cannot serve a tuned Nemotron per token (no Nemotron fine-tune bases; custom
weights go on dedicated endpoints billed per GPU-hour). Serving the 4B live until judging
ends (15 Dec) on an always-on GPU would cost hundreds of dollars against the live advisor's
about $0.0025 a question. Not worth it for this submission; the result stands as an
eval-only finding.

## Files

- Reports: `data/eval/reports/{super-se-150-p7ba,super-mirage-p7ba,nano30b-se-150,
  nano4b-base-se-150,nano4b-{base,tuned}-vllm-{se-150,mirage}}.{md,summary.json}` and
  `data/eval/reports/compare-*.json`.
- Code: `src/herbtwin/evals/finetune_data.py` (+ `tests/test_finetune_data.py`),
  `scripts/build_finetune_data.py`, `scripts/finetune/`.
- Gitignored: run rows in `data/eval/runs/` (worktree), the training file
  `data/train/advice-se.jsonl`, and the adapter plus the job log in the main checkout's
  `data/external/analysis/nano4b-lora/`.
