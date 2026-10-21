# Sponsor and tooling facts

What Nebius Token Factory, Nebius AI Cloud, NVIDIA Nemotron and NeMo, Tavily and LangSmith
actually offer, from their own docs, fetched 3 Oct 2026. "UNVERIFIED" marks anything not
confirmed from a fetched page. The Token Factory model list was checked live with the
project key the same day.

## 0. What Token Factory serves (verified live, 25 models)

- **Nemotron, all text-only:** `nvidia/Nemotron-3-Ultra-550b-a55b`, `nvidia/nemotron-3-super-120b-a12b`, `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, `nvidia/Nemotron-3_5-Lightning`.
- **Not hosted:** Nemotron 3 Nano Omni (the vision-capable one) and every Nemotron content-safety model. Running either means self-hosting on a Nebius AI Cloud Serverless endpoint.
- **Vision-capable candidates present:** `google/gemma-3-27b-it`, `zai-org/GLM-5.3-Flash` (current observe model), `zai-org/GLM-5.1` / `5.2` / `5.3`, `Qwen/Qwen3.8-27B`.
- **Others:** `Qwen/Qwen3-235B-A22B-Instruct-2507`, `Qwen/Qwen3-30B-A3B-Instruct-2507`, `Qwen/Qwen3.5-397B-A17B`, `Qwen/Qwen3-Embedding-8B`, `deepseek-ai/DeepSeek-V4-Pro` (+ `-0813`), `DeepSeek-V4-Flash-0731`, `DeepSeek-V4.1-Flash`, `openai/gpt-oss-120b`.

## 1. Nebius Token Factory and AI Cloud

- **Structured output:** `response_format` takes `json_schema` or `json_object`; support is per model (a "JSON mode" tag on the model card). Docs advise putting the schema in the prompt too and checking `message.refusal`. docs.tokenfactory.nebius.com/ai-models-inference/json
- **Function calling:** OpenAI-format `tools`; `tool_choice` auto or a forced function. .../ai-models-inference/function-calling
- **Vision:** standard `image_url` content parts, URL or base64. .../api-reference/examples/vision-capabilities
- **Rate limits:** dynamic. Example baseline 60 requests and 400k tokens a minute; rises 20% when a 15-minute window averages 80% usage, falls by a third at 50% or less, capped at 20× base. 429s carry `Retry-After`. .../ai-models-inference/rate-limits
- **Batch inference:** no `/v1/batches`. It is a Data Lab operation: `POST /v1/operations` with `type: "batch_inference"`, `params {model, completion_window}` and a source dataset; "significantly higher limits". Discount UNVERIFIED. api.tokenfactory.nebius.com/openapi.json, .../data-lab/overview
- **Data Lab:** inference logs are stored automatically unless Zero Data Retention is on; filter with SQL into datasets; reuse for batch and fine-tuning. Processing in eu-north1 (Finland). .../data-lab/data-processing
- **Fine-tuning:** supervised, LoRA or full, context 8k to 131k. LoRA and full: Qwen3 0.6B to 235B, Qwen2.5, Llama 3.1 / 3.2 / 3.3, gpt-oss 20b and 120b. Full only: Gemma 4, Qwen3.5 and 3.6-27B, DeepSeek V3 and V4-Flash. **No Nemotron base is listed.** Cost UNVERIFIED. .../post-training/models
- **Embeddings and rerank:** `/v1/embeddings`, `/v1/rerank`, `/v1/responses`, `/v1/images/generations` exist in the OpenAPI spec; `Qwen/Qwen3-Embedding-8B` is served.
- **Prompt caching:** "context caching" is listed and usage carries `cached_tokens`; a discount is UNVERIFIED.
- **Flavours:** append `-fast` to a model id for lower latency at a different price.
- **Dedicated endpoints:** per GPU-hour with per-minute granularity, no standard rate limits, custom weights incl. merged LoRA, not billed at zero replicas. .../ai-models-inference/dedicated-endpoints/overview
- **Pricing page** is JS-rendered (tokenfactory.nebius.com/organization/prices); prices UNVERIFIED here. Measured in this repo: a full pipeline run costs under $0.015.
- **AI Cloud Serverless AI:** any container image; three types: Devlab, Job (runs to completion), Endpoint (public URL). The quickstart creates the endpoint with a bearer `--token`. Billed per second at VM and disk rates; a stopped endpoint costs nothing but stop and start are manual (no automatic scale-to-zero documented). Provisioning retries 30 minutes then fails with `NotEnoughResources`. docs.nebius.com/serverless/overview, /pricing-quotas, /quickstart/endpoints, /lifecycle

## 2. Nemotron 3 family (model cards)

- **Ultra (550B, 55B active):** text only, context up to 1M (serving default 256k), released 4 Jun 2026. Reasoning toggle is `extra_body={"chat_template_kwargs": {"enable_thinking": true|false}}` plus `"medium_effort": true`; there is no `/think` flag. Sampling `temperature=1.0, top_p=0.95`. Tool calls in OpenAI format. huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16
- **Licence:** the Ultra card says **OpenMDW-1.1** (openmdw.ai/license/1-1/), not the NVIDIA Open Model License. Correct any write-up that says otherwise.
- **Super (120B, 12B active):** text, up to 1M context, same sampling, a `low_effort` flag and a documented two-step reasoning-budget recipe. huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16
- **Nano Omni (30B, 3B active, Reasoning):** images and video in (mp4 up to 2 minutes), 256k context. Sampling `temperature=0.2, top_k=1` with thinking off, `0.6 / top_p 0.95` with thinking on. huggingface.co/nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-BF16
- **Also in the nvidia org** (cards not read): Nemotron-3.5-Lightning-30B, Nemotron-Nano-12B-v2-VL, Nemotron-3-Embed-1B and 8B, llama-nemotron-rerank-1b-v2, Nemotron-Parse-2.0, Nemotron-3-Ultra-GenRM (a reward model).
- UNVERIFIED: whether Token Factory passes `chat_template_kwargs` through. This matters: the handoff records that Ultra "reasons before answering" and overran 1024 tokens; turning thinking off or to medium effort may be the proper fix. Test it.

## 3. NVIDIA evaluation and safety tooling

- **NeMo Evaluator** (Apache-2.0, github.com/NVIDIA-NeMo/Evaluator): `nel` CLI, 17 built-in benchmarks incl. judge-scored ones (simpleqa, healthbench, xstest). Takes `--model-url` and `--api-key` for any OpenAI-style endpoint, so it should run against Token Factory (not tested). Bring-your-own-benchmark with `@benchmark` and `@scorer`. `nel compare` gives deltas with statistics; `nel gate` gives GO or NO-GO from a policy file. Exports to Inspect, W&B, MLflow.
- **NeMo Guardrails** (Apache-2.0, `pip install nemoguardrails`, Python 3.10 to 3.13, github.com/NVIDIA-NeMo/Guardrails): input, dialog, retrieval and output rails; built-in self-check, fact-check, hallucination and jailbreak rails; engines include `openai` and `nim` (custom base-URL config UNVERIFIED). Sends anonymous telemetry; opt out with `DO_NOT_TRACK=1`.
- **NeMo Agent Toolkit** (Apache-2.0, `pip install nvidia-nat`): profiling, evaluation, observability, native LangSmith integration, MCP. github.com/NVIDIA/NeMo-Agent-Toolkit
- **NeMo Curator** (Apache-2.0): data curation at scale; overkill here.
- **Safety models:** `nvidia/Nemotron-3.5-Content-Safety` (4B, text plus one image, optional custom safety policy with a reasoning trace; outputs user safety, response safety, categories). Not on Token Factory; servable on vLLM on a Nebius Serverless endpoint.

## 4. Tavily

- **Endpoints:** Search, Extract, Map, Crawl, Research (async cited report); SDK `tavily-python`. docs.tavily.com/llms.txt
- **Credits:** 1,000 free a month. Search basic 1, advanced 2. Extract 1 per 5 URLs (2 advanced). Map 1 per 10 pages. Research 4 to 110 (mini) or 15 to 250 (pro) per request. Pay-as-you-go $0.008 a credit. docs.tavily.com/documentation/api-credits
- **Rate limits:** 100 requests a minute on dev keys, 1,000 production; Crawl 100; Research 20. docs.tavily.com/documentation/rate-limits
- **Grounding parameters:** `search_depth` (ultra-fast, fast, basic, advanced), `chunks_per_source`, `max_results` (default 10, max 20), `include_domains` with `include_domains_mode` `restrict` or `prefer`, `exclude_domains`, `time_range`, `start_date`, `end_date`, `topic`, `country`, `include_raw_content`, `include_answer`, `exact_match`. Keep queries under 1,500 characters. docs.tavily.com/documentation/best-practices/best-practices-search
- **Agent defaults:** `search_depth="advanced"`, `chunks_per_source=3`, `max_results=5`; Search then Extract on chosen URLs; Map before Crawl. docs.tavily.com/agents
- Results carry url, title and published date; a recommended citing pattern was not read (UNVERIFIED).

## 5. LangSmith

- **Tracing without LangChain:** set `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`; use `@traceable` (`run_type="llm"` or `"tool"`), the `trace` context manager, or `RunTree`. Flush before exit. docs.langchain.com/langsmith/annotate-code
- **`wrap_openai`:** `from langsmith.wrappers import wrap_openai`. That it works with a Token Factory `base_url` is an inference, not stated on the page. docs.langchain.com/langsmith/trace-openai
- **Datasets and experiments:** `client.create_dataset`, `client.create_examples`, `client.evaluate(target, data=..., evaluators=[fn], experiment_prefix=..., max_concurrency=...)`; evaluators take `(inputs, outputs, reference_outputs)`; `aevaluate` for large jobs. docs.langchain.com/langsmith/evaluate-llm-application
- **Feedback:** `client.create_feedback(key=..., score=..., trace_id=...)` or `run_id=`. docs.langchain.com/langsmith/attach-user-feedback
- **Comparing experiments:** a comparison view with regressions per feedback key. docs.langchain.com/langsmith/compare-experiment-results
- **Free tier:** 1 seat, 5,000 base traces a month then pay-as-you-go; base traces kept 14 days, extended 180. langchain.com/pricing
- **EU region:** UI at eu.smith.langchain.com; API host `https://eu.api.smith.langchain.com` via `LANGSMITH_ENDPOINT` (from memory, UNVERIFIED).
- Note for this repo: env names are namespaced (`HERBTWIN_LANGSMITH_API_KEY`), so pass the key to `Client(api_key=...)` explicitly rather than relying on the bare variables.

## 6. Non-obvious uses that fit a four-week build

1. **A Nemotron judge panel with the reasoning knob as a variable.** Super at low effort, Lightning, and Nano as three judges (Ultra, tested 17 Oct, agrees with people as well as Claude Sonnet and Qwen3-14B: [nvidia-models.md](nvidia-models.md)); report agreement and cost per verdict against effort level.
2. **Batch the eval run through Data Lab** instead of live calls and report the cost and limit difference.
3. **Distillation loop:** filter judge-approved Ultra outputs from Data Lab logs with SQL, LoRA fine-tune a small model, serve it on a dedicated endpoint, compare against Ultra. Token Factory's managed fine-tuning offers no Nemotron base, but Nemotron can be tuned on Nebius AI Cloud: a LoRA-tuned Nemotron 3 Nano 4B scored within noise of Super on the main action (0.400 against 0.440; 14 Oct, [fine-tune-nano-probe.md](fine-tune-nano-probe.md)).
4. **NeMo Guardrails around the recommend stage** with a plant-care harm policy (pesticide dosing, ingestion claims, toxic-to-pets advice) and the fact-check rail against Tavily chunks. This is the "harm avoidance" rubric line implemented as a guard.
5. **Nemotron Nano Omni as the observe model on a Nebius Serverless endpoint.** It is the only way to make the pipeline Nemotron end to end, and it spends the Nebius AI Cloud credit on something the judges can see. Compare it against GLM-5.3-Flash on the risk gate first.
6. **A NeMo Evaluator quality gate:** a bring-your-own-benchmark of the plant cases pointed at Token Factory, with `nel gate` beside the existing risk gate.
