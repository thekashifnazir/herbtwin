# Feedback: Nebius Token Factory, Nebius AI Cloud and NVIDIA models

For the Devpost feedback field (Most Valuable Feedback). Written from herbtwin's logged
runs, 2 to 22 Oct 2026 (our friction log, the probe write-ups in `docs/reference/` and the
eval reports in `data/eval/reports/`), plus Kash's own account of the consoles, credits
and the outage, given on 19 Oct. Every result below was measured by us; prices are Token
Factory's and Nebius's list prices, except where Kash's estimate is named. Each problem
says what happened, why it matters, and what would fix it.

The short version is the next section.

## The short version (paste this if space is tight)

1. **Serve accurate Nemotron vision models per token, and say which are per token.**
   Nemotron 3.5 Super VL arrived per token mid-October, thank you. On our 150 photos it
   was 5x faster than GLM-5.3-Flash but named the species 0.627 against 0.846, so the
   photo is still read by another vendor's model. Nemotron 3 Nano Omni is only a
   dedicated-endpoint template ($4.70 an hour, about $113 a day to keep up for judging).
2. **Fail fast when one model is down.** On 13 Oct GLM-5.3-Flash hung for a day with no
   error while the gateway and other models answered in under 0.2 s. We only found out by
   timing out.
3. **Put prices and cost in the API.** Prices are only on a JavaScript-rendered page, so
   every budget cap needs a hand-kept price table.
4. **Serverless Jobs need a CPU default, a schedule, and clear image errors.** A job that
   works for under a second takes about 3.5 minutes; a Mac-built image fails with
   `StartFailed` and no reason.
5. **GPU jobs: show the spot price, cache weights, and give more than one GPU type.**
   Our project had only B300 quota; spot jobs were preempted 2 times in 5, and one
   restart downloaded 64 GB of weights again.

## What we used

- **Token Factory**, for every language and vision model call in the app:
  - NVIDIA Nemotron 3 Super (`nvidia/nemotron-3-super-120b-a12b`): the advisor, asked
    three times per photo read, plus refine.
  - NVIDIA Nemotron 3 Nano (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, reasoning off): the
    follow-up chat's tool loop.
  - GLM-5.3-Flash reads the photo, with DeepSeek V4.1 Flash as the backup.
  - All our paid evals: 696 public photos through GLM for $0.44; advice runs on 350
    expert questions for under $1 each; four backup photo models scored on the same 150
    photos in one evening.
  - One dedicated endpoint, to test Nemotron 3 Nano Omni on our photos.
- **AI Cloud Serverless Jobs and Container Registry**: the daily reminder email job,
  started each morning by GitHub Actions. GPU jobs (B300, preemptible) for four probes:
  Cosmos 3 image-to-video and Qwen-Image-Edit (the "in about a week" pictures in the
  app), Cosmos Reason on the photo step, a LoRA fine-tune of Nemotron 3 Nano 4B, and
  Magpie TTS.
- A spoken plant voice ran on ElevenLabs until we dropped the feature on 21 Oct: Token
  Factory serves no speech model, and Magpie did not install on a job (below).

## What worked well

- **The OpenAI-compatible API meant no adapter work.** The `openai` SDK with a
  `base_url`, standard `image_url` parts and `response_format` for JSON. On day one
  (2 Oct) we compared five vision models on our own photos without changing the SDK
  code. Swapping a model is one id in config; we did it twice in production (photo
  backup Gemma to DeepSeek, chat Super to Nano), each after a cheap scored check.
- **Price made honest evaluation affordable.** A 150 to 200 question advice run on
  Super with one ask each took 2 to 6 minutes with 8 workers and about $0.10 to $0.20 on
  our early prompts; with three asks each it costs $0.37 to $0.50. So the species and
  advice rates in our README carry 95% bootstrap intervals instead of resting on a
  handful of examples, and a free public demo with a daily cap was affordable.
- **Wide choice.** 25 models were live when we started, chat models from 27B to 550B
  plus an embedding model, including four Nemotrons. That let us run the photo-backup comparison with no setup.
- **Dedicated endpoints are fair to try.** Billed per minute only while ready; setting
  up, stopping and stopped are free. Our Omni test was ready for about 8 minutes and cost
  about $0.60.
- **Billing in the console was clear,** and the extra event credits paid for far more
  experiments than we would otherwise have run, especially on AI Cloud machines.
- **It works well with a coding agent.** The `nebius` CLI and Token Factory's
  OpenAI-compatible API let a coding agent (Claude Code) run our Serverless Jobs, Object
  Storage syncs and evals end to end. The person only typed the commands that create or
  change something (a key, a job, a bucket).
- **Serverless Jobs run a container to completion and bill per second.** The reminder
  job costs under $0.01 a day. `--env-secret` from MysteryBox worked first time. A
  preemptible B300 for about $1 an hour made the GPU probes cheap: the Nemotron 4B LoRA
  fine-tune and its scoring ran in one job for about $2 to $3.

## What needs work, most valuable first

### 1. Nemotron vision per token came late, and is not yet accurate enough for plant names

- **What happened.** On 12 Oct `/v1/models` listed four Nemotrons, all text only.
  Nemotron 3 Nano Omni, marketed as vision-capable, appears only as a dedicated-endpoint
  template. Then `nvidia/Nemotron-3.5-Super-VL` appeared per token. We tested it at once
  on the same 150 photos and prompt: species top-1 0.627 [0.547, 0.707] against GLM's
  0.846 [0.785, 0.899], decline 0.833 against 0.900, 1.6 s a photo against 8.2 s, about
  $0.0006 a photo. It only returned JSON with reasoning off: with reasoning on it ran
  to the 4,096-token cap without an answer.
- **Impact.** The first step a user sees, reading the photo, has to use another
  vendor's model, in a hackathon about Nemotron. We tested Omni on a dedicated endpoint
  (1x H100, FP8, $4.70 a GPU-hour): species top-1 0.587 against GLM's 0.867 (earlier prompt) on 150
  public photos. It was better at spotting decline (balanced accuracy 0.975 against
  0.883) and five times faster (about 1.7 s a photo against 10 s). With a per-token
  price we could have used it for the health read and kept GLM for the name. Keeping
  the endpoint up until judging ends would cost about $113 a day, so we could not.
- **Ask.** Keep Super VL per token and tune it for fine-grained naming (species, not just
  "a herb"); serve Nemotron 3 Nano Omni per token too, since it read decline best. Say
  on the hackathon page which Nemotrons are per token and which are endpoint-only, and
  when that changes.

### 2. A model can hang while the gateway looks healthy

- **What happened.** From early on 13 Oct, GLM-5.3-Flash stopped replying:
  requests stayed open past 60 s with no bytes, even a 4-token text ping. At the same
  moment `/v1/models` answered in 0.07 s and Nemotron Nano in 0.18 s. GLM was back on
  14 Oct. No status page or error said anything was wrong. From Kash's side: runs kept
  failing with no clear reason for about a day, then it came back (Kash did not go looking
  for a status page). The upside: it pushed us to benchmark backup models we otherwise
  would not have tried.
- **Impact.** Live uploads hung until Cloud Run cut the page at 300 s. We added a
  backup model, a 90 s cut-off and a skip after a failure (5 minutes, tripling on each
  failure in a row, up to an hour). Our model docs also
  warn that timed-out calls may be billed without being recorded on our side.
- **Ask.** Return an error fast when a model has no capacity, with a clear reason. A
  visible per-model status or incident notice (or a status field in `/v1/models`). Say whether a client-side timeout is billed.

### 3. Prices are not in the API

- **What happened.** Prices are on the catalogue page, which is JavaScript-rendered,
  and not in `/v1/models` or in the response `usage`.
- **Impact.** Our site's budget cap ($20 for the live demo) and every eval's cost
  report need a hand-kept price table in the code, which goes stale without warning
  when a price changes.
- **The same for jobs.** The billed cost of our self-hosted Nano job (one spot B300, 19
  minutes, 19 Oct) was not something we could get from the CLI, and the billing page has no
  line per job: it showed 4.71 B300 GPU-hours for the period ($23.98), so we derived the
  job's cost from its own log at that rate (about $1.63).
- **It now shows on our page.** Each answer lists which model did each step, its time and
  its cost, against the same tokens at Nemotron 3 Ultra's price (#374, 21 Oct): one
  example read was $0.0040 against about $0.0177. Every one of those figures comes from
  our hand-copied table, so a price change on your side would make our page wrong.
- **Ask.** Prices in `/v1/models` or a pricing endpoint, and cost in `usage`; for jobs,
  the billed cost of a finished job from the CLI or API.

### 4. Reasoning models and `max_tokens`

- **What happened.** GLM-5.3-Flash reasons before it answers. With `max_tokens=1024`
  the JSON came back cut off mid-list or empty: 1,024 tokens used, no visible text.
  Nemotron 3 Nano Omni with reasoning on returned no JSON in 6 of 12 calls at the same
  limit. Nemotron's thinking switch (`chat_template_kwargs.enable_thinking=false`) is
  passed through, and it matters: Nano with reasoning off passed our tool-use check
  10/10 in three runs, with it on 8/10. We found that by trying it; the docs did not say
  it would work.
- **Ask.** Document per model whether it reasons, how many tokens that typically
  takes, and which switches (`chat_template_kwargs`, `reasoning_effort`) are passed
  through.

### 5. `response_format=json_schema` is ignored by some models on image calls

- **What happened.** Qwen3.8-27B and DeepSeek V4.1 Flash sometimes returned prose
  despite `json_schema` on image calls. Kimi-K2.6 returned list items as plain strings
  where the schema asked for objects.
- **Impact.** Every model needs a repair call and validation; DeepSeek, now our photo
  backup, still returned no JSON on 2 of about 250 problem-check calls.
- **Ask.** A 400 instead of silent prose when the schema cannot be enforced, or a
  per-model "JSON mode works with images" flag in the catalogue.

### 6. Nemotron 3.5 Lightning tool calling

- **What happened.** We tested the new `nvidia/Nemotron-3_5-Lightning` against Nano for
  the chat (80 replies each, about $0.03). Thinking is on by default and lands in
  `content`, not a separate field. `tool_choice: "required"` produced 18 parallel tool
  calls in one turn. `parallel_tool_calls: false` was ignored.
- **Impact.** It is twice as fast (0.67 s against 1.28 s a reply) but got 15 of 30
  hard cases right against Nano's 24 (it ran the plant model on "thanks!" 5 times in 5).
  We stayed on Nano.
- **Ask.** Put reasoning in a separate field (as `reasoning_content`), and honour
  `parallel_tool_calls`.

### 7. Serverless Jobs: rough edges for small CPU work

From the reminder job probe (11 Oct):

- The default platform is a GPU; a CPU job must pass `--platform cpu-d3`.
- `--timeout` has a 1 hour minimum, so a job that runs for under a second cannot be
  capped tightly.
- A sub-second job takes about 3.5 minutes wall-clock: about 1 minute provisioning,
  2 minutes starting, 30 s pulling.
- There is no schedule. We start the job from a GitHub Actions cron.
- An image built with Docker on a Mac (colima, legacy builder) has a mixed OCI/Docker
  manifest. It pushed fine, then failed 4 times with `StartFailed` in IMAGE_PULLING and
  no message saying why. The same app built with BuildKit on GitHub
  (`provenance: false`) runs.
- Service-account keys are public keys you generate and upload; that was not clear from
  the console. Ours expires on 30 Dec 2026, after which the workflow's sign-in fails,
  with no warning ahead.

**Ask.** A CPU default for jobs, a cron option, an error that names the manifest
problem, a console path that makes the key pair for you, and an expiry warning.

### 8. GPU jobs: quota, preemption, cold starts and price

From the Cosmos, Cosmos Reason, fine-tune and Magpie probes (12 to 15 Oct):

- **One GPU type.** Our project had quota only for B300: no L40S or H100. A 4B or 7B
  model does not need a B300.
- **Preemption with no weight cache.** Spot B300 jobs were preempted 2 times in 5 on
  the fine-tune. The Cosmos Reason run was preempted at photo 88 of 150, and the restart
  downloaded the 64 GB of weights again.
- **Cold start.** 5 to 7 minutes from create to a running container, billed.
- **Spot price hidden.** The GPU page says "from $0.99" but the price calculator
  showed $6.30 for the setup we picked, so we estimated each job's cost and checked
  the billing page afterwards.
- **Small file limit.** `--inject-file` allows 64 KiB for all files together, not each.
  Our payload (0.68 MB of code, questions and training data) went in over SSH to the
  job's host VM and `docker cp`. That works, but only because the host happens to have
  a public IP, `sudo` and Docker.
- **Base images.** The vLLM image has `python3` but no `python`, and no `git`. The
  PyTorch base image is now "externally managed" (PEP 668), so `pip install` fails
  without `--break-system-packages` or a venv. Two of Magpie's NeMo dependencies have no
  Linux wheel and the image has no compiler, so both Magpie jobs failed during install.
  Cosmos 3 image-to-video took 4 failed jobs before a green one (a 403 on the
  bootstrap, no `git`, no C compiler for Triton, then our own output bug).

**Ask.** More than one GPU type in a hackathon project; a weight cache or volume that
survives preemption; the real spot price before you start; a larger inject limit; and a
job template per NVIDIA model (Magpie, Cosmos, NeMo fine-tune) that installs cleanly.

### 9. Fine-tuning Nemotron

- **What happened.** Token Factory's fine-tuning lists Qwen, Llama, gpt-oss, Gemma and
  DeepSeek bases, but no Nemotron. We LoRA-tuned Nemotron 3 Nano 4B ourselves in one
  AI Cloud job (242 examples, 93 steps, 32 minutes), and it matched Super's main-action
  accuracy within the noise (0.400 and 0.420 against 0.440 and 0.435 on 350 held-out
  questions) while cutting its own over-treatment by more than half.
- **Impact.** Serving that tuned model would need an always-on dedicated GPU, so it
  stayed a probe.
- **Ask.** Nemotron bases in Token Factory fine-tuning, with per-token serving of the
  LoRA.

### 10. NVIDIA models we tried and did not ship (and what would change that)

- **Cosmos-Reason2-32B** on the photo step: species top-1 0.574 against GLM's 0.867 (earlier prompt),
  decline 0.892 against 0.883, 3.1 s a photo. About $1.10 of spot time. Hugging Face
  gating differs between the Cosmos Reason sizes.
- **Cosmos 3 Edge and Nano, image to video**, for "your plant in a week": 0 of 6 clips
  moved the way the prompt asked ("after watering", "a week without water"), at both
  sizes. Qwen-Image-Edit got 5 of 6 on the same cases, so the app's pictures use it.
  `Cosmos3OmniPipeline` was only on diffusers' main branch, not a release.
- **Nemotron 3 Nano Omni** on two photos ("did it change?"): it said the second photo
  showed more change whichever order we sent them in (posture 1 of 10). Our order-swap
  check caught it, but it means no answer.
- **Magpie TTS Multilingual 357M** for the plant voice (a feature since dropped): on a Mac CPU, word error rate
  3.1% on raw text but 0.35% with text normalisation; numbers and "°C" 0 of 15 right
  raw, 15 of 15 normalised. Normalisation is off by default and nothing warns you.
- **Nemotron 3 Ultra as the advisor**: on 150 Stack Exchange questions (one ask each)
  its main action matched the expert 0.393 against Super's 0.440, but it told people to
  treat when the expert did not 0.127 of the time against Super's 0.020, so it is not
  used live. As a judge it agrees with people 0.750 [0.706, 0.789], as well as the other
  judges we tested.

**Ask.** Text normalisation on by default in Magpie (or a warning when it is off), a
released Cosmos pipeline, and a note on Omni's two-image order bias in its model card.

### 11. Object Storage: a key for one bucket takes six steps and more access than it needs

- **What happened.** To sync our public eval reports to one bucket with the AWS CLI, we
  made a service account, looked up the tenant, looked up the `editors` group, added the
  account to it, created an access key and copied it into `aws configure`: six CLI steps
  ([docs/reference/eval-bucket-public.md](../reference/eval-bucket-public.md)). The only route we found
  puts the account in `editors`, which reaches far more than one bucket.
- **Impact.** We delete the key after every sync, and make a new one next time.
- **Also.** That path calls `nebius iam project`, and the CLI (0.12.287) now warns the
  command "is deprecated and will be removed on 2026-12-16" in favour of `iam v2 project`.
- **The console.** Kash could not tell from the console whether the bucket was public
  (it is: an anonymous GET returns 200 and an unsigned PUT 403). With London (uk-south1)
  picked, some options were greyed out and there was no choice among the three storage
  tiers, with no reason given; we assume they are region-locked.
- **Ask.** An access key scoped to one bucket (read, or read and write), made in one
  command. In the console, show a bucket's public or private state plainly, and say when
  an option is unavailable in the chosen region.

### 12. More models as a service, and more guidance on what each one is for

- **What happened.** Trying a model that Token Factory does not serve meant an AI Cloud
  machine: about $20 to $30 to stand one up, load the model and run it, in Kash's
  estimate, against $1 to $2 a test on Token Factory.
- **Ask.** More models per token on Token Factory, especially the larger and more
  expensive ones, so they can be tried quickly without paying for a machine. Token
  Factory's model cards carry capability tags (its docs point to a "JSON mode" tag); more
  guidance on what each model is good for (vision, tool calling, reasoning) would save
  trial runs.

### 13. Rate limits: nothing to size against, and no retry guidance

- **What happened.** Before judging we planned for several judges at once: 5 answers in
  flight are 15 advisor calls. We had no per-key or per-model rate limit to plan against,
  and no guidance on whether a 429 carries `Retry-After`. Our client ran with the SDK's
  retries off on purpose (a second long wait could pass Cloud Run's 300 s page limit), so
  a 429 would have dropped an advisor, and three would have dropped the answer. On 21 Oct we added one retry
  on a 429 or 5xx after a jittered 0.5 to 1.5 s wait, or the server's `Retry-After` if
  sent, never more than 3 s (#375).
- **Ask.** Publish each key's limits per model (requests and tokens per minute), show
  them in the console, send `Retry-After` on every 429, and say whether a rejected call is
  billed.

### 14. Model ids: inconsistent, and no display name

- **What happened.** `/v1/models` (28 models on 22 Oct) gives only `id`, `created`,
  `object` and `owned_by`. The Nemotron ids mix casing and separators:
  `nvidia/nemotron-3-super-120b-a12b`, `nvidia/Nemotron-3-Ultra-550b-a55b`,
  `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, `nvidia/Nemotron-3.5-Super-VL` and
  `nvidia/Nemotron-3_5-Lightning`.
- **Impact.** To say "Decided by NVIDIA Nemotron 3 Super" on the page, and to name each
  step's model in the receipt, we keep our own id-to-name map. An id typed from memory
  is easy to get wrong ("3.5" or "3_5").
- **Ask.** One id style, plus `display_name`, `family`, `modality` and price fields in
  `/v1/models`.

## Zero to hello world

- **Credits and onboarding:** smooth. Credits came first through the AI Builder programme,
  then more at the London Nebius × NVIDIA event, which Kash attended in person. The event
  itself was worth it: Kash had not known how many NVIDIA models were available on Token
  Factory and on AI Cloud.
- **Token Factory:** the same day. Key, first call, and a five-model vision comparison
  on our own photos on 2 Oct.
- **Serverless Job:** one evening (11 Oct), most of it spent on the manifest problem in
  item 7.
- **GPU job with an NVIDIA model:** 4 failed jobs before the first green one (Cosmos 3),
  each a 5 to 7 minute wait before the error showed.

## Would we build on it again?

In Kash's words: "So far, the experience I've had in Nebius has been pretty good. The only
issue is that one time when we had one of the models down. Other than that, it's been
pretty good to use. It's been easy using it via Claude to be able to get it to run stuff
for us."

Yes, for language models: the price, the model choice and the OpenAI-compatible API made
a properly evaluated multi-step agent affordable for one person in four weeks. For a
photo-first app we would want a per-token Nemotron vision model that names plants as
well as GLM, and fail-fast errors first. For GPU work we would want a cached model volume and more than one GPU type.
