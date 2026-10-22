# Chat search on vs off: 2026-10-22-chat-search-before-414

- Chat model `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` (thinking off), `chat.reply` at temperature 0; the run started from git `f3297172`
- 30 questions x 2 arms; rows 60, 60 answered. Search on = Tavily alone on the app's trusted sites, with its plant filter; off = no search tool. Everything else is equal.
- Cost of the rows: model $0.0099 (summed from the adapters' recorded usage); 63 search_web calls, at most that many Tavily searches (about $0.50 at $0.008 a credit). This invocation spent $0.0099 on the model and sent 37 Tavily searches; cached rows are not re-paid.
- The metrics, rubric and decision rule are in the header of `src/herbtwin/evals/chat_search.py`, committed before any paid call. **M1 is the pre-registered decision metric.**

| Metric | Search off | Search on | On minus off (95% CI) |
|---|---|---|---|
| M1 Correct: has the key fact (decision metric) | 0.467 [0.300, 0.667] (n=30) | 0.867 [0.733, 0.967] (n=30) | +0.400 [+0.233, +0.600] (n=30) |
| M2 Cites a source | 0.000 [0.000, 0.000] (n=30) | 0.000 [0.000, 0.000] (n=30) | +0.000 [+0.000, +0.000] (n=30) |
| M3 Every cited source is an on-plant search hit (of replies that cite) | n/a | n/a | n/a |
| M4 Says not sure, or declines | 0.367 [0.200, 0.533] (n=30) | 0.067 [0.000, 0.167] (n=30) | -0.300 [-0.467, -0.133] (n=30) |
| M5 App added its Less sure line (nothing grounds it) | 1.000 [1.000, 1.000] (n=30) | 0.000 [0.000, 0.000] (n=30) | -1.000 [-1.000, -1.000] (n=30) |

By the pre-registered rule: **search makes the chat more correct**.

Correct with search only: basil_plant_out, chives_divide, coriander_after_flower, mint_beetle, mint_rust, parsley_carrot_fly, parsley_leaf_miner, parsley_sow_out, rosemary_beetle, rosemary_foam, rosemary_pot, sage_speckles. Correct without search only: none.

Bootstrap: 2000 draws, seed 0, resampling questions; M3's paired row uses only questions where both arms cited.

**Rubric v2 (post-hoc, not pre-registered):** correct off 0.433 [0.267, 0.633] (n=30), on 0.900 [0.767, 1.000] (n=30), on minus off +0.467 [+0.267, +0.633]. Why: a review found some v1 patterns too loose (a bare "won't", "best" or "hardy" passed; "may" matched the verb) and v1 missed the non-breaking hyphens Nano writes ("leaf‑miner"). v2 normalises U+2010 and U+2011 to "-" and rewrites the patterns of 15 questions (`RUBRIC_V2` in `src/herbtwin/evals/chat_search.py`). It was written after reading the replies, so it is a sensitivity check; M1 above is the result.

## Per question

| Question | Off v1 | On v1 | Off v2 | On v2 | On cites | On on-plant | On searches |
|---|---|---|---|---|---|---|---|
| basil_hardy | yes | yes | yes | yes | no | – | 1 |
| basil_plant_out | no | yes | no | yes | no | – | 1 |
| basil_eat_flowering | yes | yes | yes | yes | no | – | 1 |
| basil_downy_mildew | yes | yes | yes | yes | no | – | 2 |
| basil_dm_cure | no | no | no | yes | no | – | 1 |
| basil_pot | yes | yes | yes | yes | no | – | 1 |
| parsley_life | yes | yes | yes | yes | no | – | 1 |
| parsley_sow_out | no | yes | no | yes | no | – | 1 |
| parsley_carrot_fly | no | yes | no | yes | no | – | 1 |
| parsley_leaf_miner | no | yes | no | yes | no | – | 22 |
| coriander_bolt | yes | yes | yes | yes | no | – | 1 |
| coriander_after_flower | no | yes | no | yes | no | – | 1 |
| coriander_pick_height | yes | yes | yes | yes | no | – | 1 |
| rosemary_hardy | yes | yes | no | yes | no | – | 1 |
| rosemary_prune | no | no | no | no | no | – | 1 |
| rosemary_beetle | no | yes | no | yes | no | – | 1 |
| rosemary_foam | no | yes | no | yes | no | – | 2 |
| rosemary_pot | no | yes | no | yes | no | – | 2 |
| thyme_trim | yes | yes | yes | yes | no | – | 1 |
| thyme_mulch | yes | yes | yes | yes | no | – | 1 |
| thyme_repot_october | no | no | no | no | no | – | 1 |
| mint_spread | yes | yes | yes | yes | no | – | 1 |
| mint_rust | no | yes | no | yes | no | – | 10 |
| mint_after_flower | yes | yes | yes | yes | no | – | 1 |
| mint_beetle | no | yes | no | yes | no | – | 1 |
| sage_speckles | no | yes | no | yes | no | – | 1 |
| sage_prune | yes | yes | yes | yes | no | – | 1 |
| chives_after_flower | yes | yes | no | yes | no | – | 1 |
| chives_divide | no | yes | yes | yes | no | – | 1 |
| chives_white_dots | no | no | no | no | no | – | 1 |
