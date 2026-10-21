# Pre-registration: NVIDIA Nemotron 3 Nano, Token Factory vs self-hosted on a Nebius job

Written 19 Oct 2026, before any run of this comparison. Kash approved the spend (via the integrator).

## Question
Does the same NVIDIA open model give the same advice when self-hosted on Nebius AI Cloud
(a Serverless AI Job, vLLM, open BF16 weights) as when served by Nebius Token Factory?

## Set, model, settings (held fixed in every arm)
- Set `actions_se`: 150 Stack Exchange herb questions, labels from expert answers.
- Model: Token Factory `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`; self-hosted
  `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16` (Hugging Face), served under the Token Factory name.
- Advice prompt hash `7ba44f01d95b` (unchanged since the 17 Oct `nano30b-se-150` run), one ask
  per question at temperature 0, thinking at the model's default (on) in both arms, 8 workers.
- Commands, from this branch:
  - Token Factory arm (twice: run A and run A2; A2 measures how much Token Factory varies with itself):
    `uv run python scripts/eval_advice.py --set actions_se --model nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B --backend tokenfactory --asks 1 --limit 150 --workers 8 --budget 1 --yes-paid --run-id nano30b-tf-p7ba` (then `--run-id nano30b-tf2-p7ba`)
  - Self-hosted arm, through `scripts/nano_selfhost/job.sh tunnel`:
    `HERBTWIN_OLLAMA_BASE_URL=http://localhost:18000/v1/ uv run python scripts/eval_advice.py --set actions_se --model nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B --backend ollama --think --asks 1 --limit 150 --workers 8 --run-id nano30b-selfhost-p7ba`
    (`--think` sends no reasoning switch, so the model's default, on, applies, as on Token Factory.)
  - Compare: `uv run python scripts/compare_advice.py --set actions_se --a data/eval/runs/nano30b-tf-p7ba.jsonl --b data/eval/runs/nano30b-selfhost-p7ba.jsonl --labels tokenfactory,selfhost --out data/eval/reports/2026-10-19-nano-selfhost.compare.json`, and the same with `--b …nano30b-tf2-p7ba.jsonl --labels tokenfactory,tokenfactory2` for the noise floor.

## Primary measure
**Agreement:** the share of questions, scored ok in both runs, where the self-hosted main action
equals the Token Factory run A main action (`primary_agreement`, 95% bootstrap interval over
questions, 2000 draws, seed 0).

Reading rule, fixed now: the self-hosted model **behaves like Token Factory** if its agreement
with run A is no more than 0.10 below run A2's agreement with run A (Token Factory against
itself). Otherwise it **behaves differently**, and the report says so.

## Secondary (reported, no claim rule)
- `primary_match` against the expert for each arm, and the self-hosted minus Token Factory
  difference with its 95% interval (scripts/compare_advice.py).
- Calls that failed or returned invalid advice, per arm.
- Wall-clock time per arm, with 8 workers.
- Cost:
  - Token Factory: from each run's recorded cost.
  - Self-hosted: the job's billed GPU minutes times the B300 price, from the Nebius billing page.
    That includes download and start-up, and the report splits out serving time from the job log.

## Limits, said now
- At temperature 0 the two engines can still differ in numerics; thinking text can differ too.
  That is what the noise-floor run is for.
- The self-hosted run uses spot capacity; a preemption means a new job. Rows are cached, so only
  unfinished questions re-run, and the report notes it.
- Cost cap: the job's platform timeout is 1 h (the minimum) on one B300 spot GPU. Even at the
  on-demand B300 price ($9.50/h), one job costs at most $9.50. Kash cancels it as soon as the eval
  ends (`job.sh done`, then `job.sh ended`).

## Amendment 1 (19 Oct, after both Token Factory runs, before any self-hosted run)
- **Thinking is OFF in every arm, not on.** The repo's settings list
  `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` as a no-thinking model (the live app runs the chat that
  way), so `eval_advice.py` sent `enable_thinking: false` in both Token Factory runs. That is the
  model as the app really uses it, so the comparison keeps it:
  - the self-hosted server now defaults to thinking off (`--default-chat-template-kwargs
    '{"enable_thinking": false}'`, scripts/nano_selfhost/serve.sh);
  - its eval command stays as written above, with `--think`. That flag only means the eval
    sends no reasoning switch; without it the eval would send `reasoning_effort: "none"`,
    which vLLM may refuse for this model. So the server's default (off) applies, matching
    Token Factory's `enable_thinking: false`.
  The primary measure and the reading rule are unchanged.
- Results so far, recorded before the self-hosted run:
  - run A `nano30b-tf-p7ba`: 148 of 150 scored, 2 failed (invalid advice output), $0.0139, 49 s wall;
  - run A2 `nano30b-tf2-p7ba`: 150 of 150 scored, $0.0115, 32 s wall;
  - **Token Factory against itself: 124 of 148 agree, 0.838 [0.777, 0.899]**
    (data/eval/reports/2026-10-19-nano-selfhost.noise-floor.json).
  So the fixed reading rule says the self-hosted model behaves like Token Factory if its
  agreement with run A is **0.738 or more**.
- The 17 Oct `nano30b-se-150` run (0.420, $0.19) predates the no-thinking setting and is not part
  of this comparison.

## Amendment 2 (19 Oct, after a review, before any self-hosted run)
- **Thinking off in every request, not only by the server's default.** The self-hosted eval
  command is now:
  `HERBTWIN_OLLAMA_BASE_URL=http://localhost:18000/v1/ uv run python scripts/eval_advice.py --set actions_se --model nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B --backend ollama --vllm-no-think --asks 1 --limit 150 --workers 8 --run-id nano30b-selfhost-p7ba`
  (`--vllm-no-think` replaces `--think`). It sends `chat_template_kwargs: {"enable_thinking":
  false}` with each request, as the app does for Token Factory, so the two arms get the same
  request. The server default stays as a second guard.
- **A check before the eval.** After READY and with the tunnel open, `job.sh check`
  (scripts/nano_selfhost/check.py) sends one real advise request exactly as the eval sends it
  (the advise prompt, its JSON schema, thinking off) and stops the run unless the first reply
  is valid advice (the Nemotron v3 reasoning parser with structured output could otherwise
  leave every answer empty).
- **Spend across preemptions.** At most one re-create, and only if the first job's billed cost
  (Nebius billing page) is $2.50 or less, so both jobs stay under the $12 cap even at the
  on-demand price. `job.sh create` enforces it: it logs each attempt before calling Nebius (so a job
  whose reply fails to parse still counts), refuses a second without `BILLED_USD` of at most
  2.50, and refuses a third. `compare_advice.py` refuses a run file that mixes model settings. If the cap stops the run, the report gives
  the partial result (rows are cached) and says so.
- A wording fix to amendment 1: the no-thinking setting is in the **local .env**
  (`no_thinking_models`), not the repo's settings.
The primary measure, the reading rule and the 0.738 threshold are unchanged.

## Amendment 3 (19 Oct, after a third review, before any self-hosted run)
- The spend rule is unchanged; its enforcement is stronger. `job.sh create` also counts the
  jobs named `nano-selfhost` that Nebius lists (any state) and refuses while one is live, so
  the cap holds from any checkout. It accepts only an SSH public key, and every Nebius call
  names a CLI profile (`NEBIUS_PROFILE`, default `kash`).
