# Model speed and cost, as measured

What each way of running a model actually cost in time and money during the plan 2
evaluations (2 to 4 Oct 2026), on an M4 Max with 128 GB. Use it to pick where a run goes
before starting it. Figures are from our own run files in `data/eval/runs/` (gitignored)
and process wall times; nothing here is a vendor claim. Re-measure when a model, prompt
or machine changes.

## In one line each

- **Local Ollama (qwen2.5vl:7b, qwen3:14b):** free, but one request at a time, and it
  slows the whole Mac. Fine for a 50-item check; hours for a full set.
- **Token Factory with parallel workers:** a 150 to 200 question advice run takes 2 to 6
  minutes for about $0.10 to $0.20. The fastest route by far, and cheap.
- **Subscription CLIs (Claude, Codex):** no per-call cost, but slow per call and, for
  Codex, capped at about 100 calls per usage window. Good for judges on small samples.

## Photo reading (observe stage), per photo

| Model | Where | Median time | Slow tail (90th %) | Cost |
|---|---|---|---|---|
| qwen2.5vl:7b | Ollama, local | 11 to 12 s (27 s on large time-lapse frames) | 12 to 36 s | free |
| GLM-5.3-Flash | Token Factory | 7 to 9 s | 13 to 19 s, up to 58 s | $0.0006 to $0.0007 |

- GLM is a reasoning model: about 800 to 1,100 output tokens a photo. On Stack Exchange
  question photos at the client's 60 s default timeout, many calls timed out; **set
  `HERBTWIN_TOKENFACTORY_TIMEOUT_S=180` for photo runs.** Timed-out calls may be billed
  without being recorded.
- GLM is better as well as faster: species 0.87 vs 0.47 top-1; it rarely says "not a
  plant" (7 of 120 detached leaves vs 67).

## Advice (advise stage), per question

| Model | Where | Throughput seen | Cost |
|---|---|---|---|
| qwen3:14b, thinking off | Ollama, local | sequential; about 1 question a minute when sharing Ollama with a photo run (41 few-shot questions in 47 min) | free |
| Nemotron Super (`nvidia/nemotron-3-super-120b-a12b`) | Token Factory, 8 workers | 150 questions in 1.5 to 2.5 min; 200 in 4 to 6 min | $0.0006 a question plain; $0.0009 with six few-shot examples |
| GLM photo + Nemotron Super | Token Factory, 8 workers | 150 questions in under 8 min | about $0.0013 a question |
| GLM photo + local qwen3:14b | 4 parallel processes | about 4 questions a minute in total; 546 questions took about 2.5 hours | GLM only, about $0.0007 a photo |

- Super answers in about 400 to 520 output tokens (the "always give the best action"
  prompt runs about 30% longer than the old one).
- Quality differs as well as speed: Super's main action matched the expert 0.387 of the
  time on a 150-question Stack Exchange sample; local qwen3:14b 0.283 on all 774.

## Judges (pairwise preference, Stack Exchange pairs)

- Claude Sonnet via the Claude CLI and qwen3:14b via Ollama both judged the 375 pairs
  (750 calls each: every pair in both orders);
  per-call times were not recorded.
- Codex CLI: about 100 calls per usage window (limits hit at 04:40, 11:45, 16:53, 21:56
  on 3 to 4 Oct); 170 of 375 pairs done. Small samples only.

## What we learned about running them

- Four local processes sharing one Ollama model do not run four times faster: Ollama
  served one request at a time here, so local parallelism mostly queues.
- Quotes from a rate measured on one kind of input can be off for another: GLM's rate
  from the perception sets quoted $0.0006 a photo; early Stack Exchange photos ran at
  $0.0011 (timeouts included) before settling at $0.0007. Quote with a margin and keep
  the hard budget stop.
- Test on a sample of about 150 first (an interval of roughly ±0.07 on a rate near 0.4);
  run the full set only when the sample is promising.
