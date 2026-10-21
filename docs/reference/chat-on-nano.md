# The follow-up chat on Nemotron 3 Nano (14 Oct 2026)

**Result: "Ask about this plant" runs on `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` with
reasoning off; the advice stays on Nemotron 3 Super.** Super does the slow, careful part
(three asks per photo, their agreement feeds the confidence). The chat is a short tool loop
(`run_scenario` on the plant model, then `search_web`), where speed matters more and Nano
holds up.

## The check

`scripts/check_chat.py`: 10 scripted what-ifs (5 herbs with a frost night ahead asked "what
if I bring it inside?", the same 5 on wet soil asked "should I give it a good water?").
Pass = every case calls `run_scenario` with the right action and the plant model's verdict
(better / worse) is in the reply. Search off, synthetic weather, Token Factory.

| Model | Runs | Pass | Wall time (10 cases) | Cost per run |
|---|---|---|---|---|
| Nemotron 3 Super (live advisor) | 2 | 10/10, 10/10 | 32 s, 24 s | $0.007, $0.017 |
| Nemotron 3 Nano, reasoning on | 1 | **8/10** | 43 s | $0.008 |
| Nemotron 3 Nano, reasoning off | 3 | 10/10, 10/10, 10/10 | 15 s, 14 s, ~15 s | $0.009–0.018 |

Cost per run came out about the same as Super's, even though Nano is cheaper per token:
these runs used more tokens, and a run's cost varies a lot from one run to the next (Super:
$0.007, then $0.017). The gain is speed, not money.

With reasoning on, Nano answered 2 wet-soil cases from the prompt alone ("no, the soil is
already wet") without calling the plant model: right words, but not grounded in the model,
so the check fails them. With reasoning off it called the tool every time. Its replies are
shorter and plainer than Super's ("Better than leaving it out, since frost is forecast
Thursday and moving it indoors avoids that risk.").

## Settings

- `HERBTWIN_FAST_MODEL` names the chat's model; unset, the chat uses the advise model.
- The live deploy lists the same id in `HERBTWIN_NO_THINKING_MODELS`
  (`chat_template_kwargs.enable_thinking = false`). A test pins both.

## Not measured

The check runs with search off; the live chat also has `search_web` (Tavily). A live check
after deploy covers one search turn. Total spend on this probe: about $0.07.
