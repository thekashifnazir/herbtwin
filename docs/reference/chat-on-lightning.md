# Nemotron 3.5 Lightning for the follow-up chat? (15 Oct 2026)

**Result: keep the chat on `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` (reasoning off). Do
not switch to `nvidia/Nemotron-3_5-Lightning`.** Lightning is about twice as fast per
reply and ties Nano on the what-if check (50/50 each). But it fails cold "thanks!" every
time (Nano's known slip, now 5/5 instead of 1/5), it adds US wording ("Most extension
advice says...") to an answer Nano got clean, and under `tool_choice: "required"` it floods
tool calls until it runs out of tokens. That last one was seen on all 3 bare-request tries,
a small sample but the same every time at temperature 0. The chat's "not sure, search first" retry
(#142) depends on that setting. The speed gain is ~0.6 s a reply on replies that already
take ~1.3 s, so it doesn't pay for the regressions.

## The check

`scripts/compare_chat_models.py` runs both models through `chat.reply` with the live
chat's tools and prompt. Calls are interleaved case by case in one session (15 Oct),
reasoning is off for both (`chat_template_kwargs.enable_thinking = false`), and each
model does 5 runs.

- **Base: the 10 cases from `scripts/check_chat.py`**, the harness that chose Nano
  (`chat-on-nano.md`). Same records and pass rule (`run_scenario` with the right action and
  the plant model's verdict), search off.
- **Hard: 6 cases, search on.** Search used the free readers (Exa, TinyFish); Tavily was
  off.
  - `thanks`: "thanks!" after one what-if turn. Pass: no `run_scenario`.
  - `thanks_cold`: "thanks!" as the first message. Pass: no `run_scenario`.
  - `water_today`: "What if I water it today?" Pass: `run_scenario` with `water`.
  - `eat_leaves`: "Can I still eat the leaves that look healthy?" on a basil downy mildew
    answer. Pass: a grounded `search_web` call, either in the first round or through the
    "not sure" retry.
  - `ask_locally`: "Who could I ask locally to check it is downy mildew?" Pass: no US
    wording.
  - `prevent_next_year`: "How do I stop it coming back next year?" Pass: a grounded search.
- **US wording**: "extension", "master gardener", "USDA" or "land grant" in the reply's
  own prose fails any hard case. Citations such as `[extension.umn.edu/...]` don't count.
- **Answer quality**: the Nano doc had no LLM judge. It used the scripted pass rule plus a
  read of the replies, so this check does the same. The replies were read by hand against
  one rubric: does it answer the question, is it right, does it stay within the sources?

Reproduce: `HERBTWIN_BACKEND=tokenfactory HERBTWIN_SEARCH_ENABLED=1
HERBTWIN_TAVILY_ENABLED=0 uv run python scripts/compare_chat_models.py --models
nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B,nvidia/Nemotron-3_5-Lightning --runs 5 --yes-paid`.
Running with `--rescore data/eval/runs/compare_chat.json` re-scores saved replies without
any calls.

## Results (80 replies per model)

Every row except "Genuine 'I'm not sure' replies" comes from the script. Re-running
`--rescore data/eval/runs/compare_chat.json` prints it again from the saved replies (the
file is gitignored, so it lives only on the machine that ran the check). The "Genuine"
row is a hand-read of the replies the "not sure" pattern matched. The "ask locally" row
is the US-wording regex alone: that case has no other pass rule. The hand-read of answer
quality is in the next section.

| | Nano 3 (30B-A3B) | Lightning 3.5 |
|---|---|---|
| Base what-ifs (check_chat) | **50/50** | **50/50** |
| Hard cases | **24/30** | 15/30 |
| · thanks (after a turn) | 5/5 | 5/5 |
| · thanks (cold) | 4/5 | **0/5**: `run_scenario` water every time |
| · water today | 5/5 | 5/5 |
| · eat healthy leaves | 5/5 (all through the "not sure" retry) | 0/5: searched first unprompted, but "Most extension advice says..." |
| · ask locally | 0/5 "cooperative extension office" | 0/5 "university extension office, master-gardener clinic" |
| · prevent next year | 5/5 | 5/5 |
| Model time per reply, median / p90 | 1.28 s / 2.58 s | **0.67 s / 0.94 s** |
| One call, median / p90 | 648 ms / 992 ms | **327 ms / 515 ms** |
| "Not sure" retries fired (`required`) | 10 | 0 |
| Genuine "I'm not sure" replies | 2 | 0 (5 conditional "if you're unsure...") |
| Leaked tags / no answer / errors | 0 / 0 / 0 | 0 / 0 / 0 |
| Tokens in / out | 136k / 5.5k | 156k / 6.0k |
| Cost for 80 replies | $0.0095 | $0.0108 |

Wall time per reply, which includes the search, was 1.4 s median / 4.2 s p90 for Nano and
0.7 / 1.1 s for Lightning. That gap overstates the model difference. Lightning sent the
same query word for word every run (it is near-deterministic at temperature 0), so it
likely hit the search provider's cache. Nano's queries changed from run to run, and its
searches took up to 9 s. Read speed from the model-time rows.

The price per token is the same ($0.06 / $0.24 per M). Lightning used ~15% more input
tokens for the same messages, so it cost slightly more: about $0.00013 a reply against
$0.00012.

## What the replies say (hand-read)

- **What-ifs**: both are right and plain. Lightning: "Bringing it inside for the next few
  days is better than leaving it out..." / "Watering now would make the situation worse.
  The soil is already wet 2 cm down." Nano: "Better than leaving it out, since frost is
  forecast Thursday..."
- **Eat the healthy leaves**: neither answers well. Nano said "avoid them" or "not sure"
  in 4 of 5 runs, and only 1 said "you can pick off the unaffected leaves and eat them".
  Lightning contradicts itself in all 5 runs ("Healthy-looking leaves nearby are usually
  safe to eat... but it's best to... avoid eating any leaves"). In 2 of them it suggested
  "tasting a tiny piece". Lightning's plus: it searched before answering every time, so
  the #142 retry never had to fire.
- **Prevent next year**: Lightning is more specific and the same every run: resistant
  varieties, rotation, spacing, watering at the base. But it named varieties that are in
  none of the search results. "Prospera" is real. The other name changed between runs
  ("Thai Serata", "Thai Serene"), which looks invented. Nano is more generic but stays
  within its sources, and it cites them.
- **Ask locally**: both point a UK user to US services every time. This is a prompt gap
  (the chat is never told the person is in the UK), not a model choice.
- **"thanks!" in every passing reply** still gets the "Less sure: we couldn't check
  this..." line appended, on both models. That's a product nit: a thank-you reply needs no
  grounding.

## Friction (tool feedback material)

1. **Thinking is on by default, and it lands in `content`.** Without the flag, Lightning
   returned "Here's a thinking process: 1. **Analyze User Input:**..." as the answer text
   (512 `reasoning_tokens` reported, nothing in `reasoning_content`). A client that
   forgets `chat_template_kwargs.enable_thinking=false` shows the model's thinking to the
   user. The flag itself works (0 reasoning tokens), and it's the same flag as Nano's, but
   the catalog doesn't say it's needed.
2. **`tool_choice: "required"` runs away.** With 2 tools offered, Lightning made 18
   parallel calls (every `run_scenario` action, then a dozen searches) until `max_tokens`
   (`finish_reason: length`). It left a raw `<tool_call>` / `<function=...>` block in
   `content`, with a malformed `</parameter></parameter>`. This was the same on all 3
   tries. Nano made 1 call each time. `parallel_tool_calls: false` is silently ignored:
   still 18 calls. With only `search_web` offered (the chat's actual retry), it called
   `run_scenario` anyway, a tool that wasn't in the request, with an invented action
   (`eat_healthy_leaves`).
3. **Tool-call decoding is slow.** The runaway took 17–19 s for 512 tokens (~28 tok/s),
   while a plain 512-token reply took 2.5 s (~200 tok/s). At the chat's `MAX_TOKENS =
   2048`, one runaway retry could take ~70 s and hit the 60 s Token Factory timeout. That is an
   extrapolation from the 512-token rate, not measured.
4. Lightning bills ~15% more input tokens than Nano for the same messages and tools, so
   "same price" isn't quite the same cost.

## If it were switched later

Nothing changes in the code. The private working repo's `deploy.sh` would set
`HERBTWIN_FAST_MODEL=nvidia/Nemotron-3_5-Lightning` and put the same id in
`HERBTWIN_NO_THINKING_MODELS` (lines 31–32). Before doing that:
- make the "not sure" retry safe from the runaway (a low `max_tokens` on that call, and
  run only the first `search_web` call);
- skip `run_scenario` on small talk ("thanks!");
- tell the chat the person is in the UK.

Those three fixes would help Nano too. The UK-context fix is now on branch
`fix/chat-uk-context`. With it, live Nano named the RHS, a garden centre or an allotment
society on "who could I ask locally?" 5 times out of 5, with no mention of an extension
service.

## Cost

About $0.03 of Token Factory in total:
- 7 single-call probes of the request shape, about $0.001;
- a 1-run shakedown (30 replies), $0.004;
- the 5-run comparison (160 replies), $0.020;
- 4 calls probing the retry path in context, about $0.001.
