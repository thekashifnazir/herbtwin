# Chat search on vs off: 2026-10-19-chat-search

- Chat model `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` (thinking off), `chat.reply` at temperature 0; the run started from git `f5eb9aa`
- 30 questions x 2 arms; rows 60, 60 answered. Search on = Tavily alone on the app's trusted sites, with its plant filter; off = no search tool. Everything else is equal.
- Cost of the rows: model $0.0092 (summed from the adapters' recorded usage); 33 search_web calls, at most that many Tavily searches (about $0.26 at $0.008 a credit). This invocation spent $0.0092 on the model and sent 31 Tavily searches; cached rows are not re-paid.
- The metrics, rubric and decision rule are in the header of `src/herbtwin/evals/chat_search.py`, committed before any paid call. **M1 is the pre-registered decision metric.**

| Metric | Search off | Search on | On minus off (95% CI) |
|---|---|---|---|
| M1 Correct: has the key fact (decision metric) | 0.500 [0.333, 0.700] (n=30) | 0.833 [0.700, 0.967] (n=30) | +0.333 [+0.133, +0.533] (n=30) |
| M2 Cites a source | 0.000 [0.000, 0.000] (n=30) | 0.100 [0.000, 0.200] (n=30) | +0.100 [+0.000, +0.200] (n=30) |
| M3 Every cited source is an on-plant search hit (of replies that cite) | n/a | 1.000 [1.000, 1.000] (n=3) | n/a |
| M4 Says not sure, or declines | 0.567 [0.367, 0.733] (n=30) | 0.033 [0.000, 0.100] (n=30) | -0.533 [-0.700, -0.333] (n=30) |
| M5 App added its Less sure line (nothing grounds it) | 1.000 [1.000, 1.000] (n=30) | 0.000 [0.000, 0.000] (n=30) | -1.000 [-1.000, -1.000] (n=30) |

By the pre-registered rule: **search makes the chat more correct**.

Correct with search only: basil_plant_out, chives_divide, coriander_after_flower, mint_beetle, mint_rust, parsley_leaf_miner, parsley_sow_out, rosemary_beetle, rosemary_foam, rosemary_hardy, thyme_repot_october. Correct without search only: mint_after_flower.

Bootstrap: 2000 draws, seed 0, resampling questions; M3's paired row uses only questions where both arms cited.

**Rubric v2 (post-hoc, not pre-registered):** correct off 0.433 [0.267, 0.600] (n=30), on 0.933 [0.833, 1.000] (n=30), on minus off +0.500 [+0.300, +0.667]. Why: a review found some v1 patterns too loose (a bare "won't", "best" or "hardy" passed; "may" matched the verb) and v1 missed the non-breaking hyphens Nano writes ("leaf‑miner"). v2 normalises U+2010 and U+2011 to "-" and rewrites the patterns of 15 questions (`RUBRIC_V2` in `src/herbtwin/evals/chat_search.py`). It was written after reading the replies, so it is a sensitivity check; M1 above is the result.

## Per question

| Question | Off v1 | On v1 | Off v2 | On v2 | On cites | On on-plant | On searches |
|---|---|---|---|---|---|---|---|
| basil_hardy | yes | yes | yes | yes | no | – | 1 |
| basil_plant_out | no | yes | no | yes | no | – | 1 |
| basil_eat_flowering | yes | yes | yes | yes | no | – | 1 |
| basil_downy_mildew | yes | yes | yes | yes | yes | yes | 1 |
| basil_dm_cure | yes | yes | no | yes | yes | yes | 1 |
| basil_pot | yes | yes | yes | yes | no | – | 1 |
| parsley_life | yes | yes | yes | yes | no | – | 1 |
| parsley_sow_out | no | yes | no | yes | no | – | 1 |
| parsley_carrot_fly | no | no | no | no | no | – | 0 |
| parsley_leaf_miner | no | yes | no | yes | no | – | 1 |
| coriander_bolt | yes | yes | yes | yes | no | – | 1 |
| coriander_after_flower | no | yes | no | yes | no | – | 1 |
| coriander_pick_height | yes | yes | yes | yes | no | – | 1 |
| rosemary_hardy | no | yes | no | yes | no | – | 1 |
| rosemary_prune | no | no | no | no | no | – | 1 |
| rosemary_beetle | no | yes | no | yes | no | – | 1 |
| rosemary_foam | no | yes | no | yes | no | – | 1 |
| rosemary_pot | yes | yes | yes | yes | no | – | 1 |
| thyme_trim | yes | yes | yes | yes | no | – | 1 |
| thyme_mulch | yes | yes | yes | yes | no | – | 1 |
| thyme_repot_october | no | yes | no | yes | no | – | 1 |
| mint_spread | yes | yes | yes | yes | no | – | 1 |
| mint_rust | no | yes | no | yes | yes | yes | 5 |
| mint_after_flower | yes | no | yes | yes | no | – | 1 |
| mint_beetle | no | yes | no | yes | no | – | 1 |
| sage_speckles | no | no | no | yes | no | – | 1 |
| sage_prune | yes | yes | yes | yes | no | – | 1 |
| chives_after_flower | yes | yes | no | yes | no | – | 1 |
| chives_divide | no | yes | no | yes | no | – | 1 |
| chives_white_dots | no | no | no | yes | no | – | 1 |

## Hand check (25 replies)

The rubric agreed with the hand verdict on 20 of 25 (v1, pre-registered) and 25 of 25 (v2, post-hoc, written after this check, so not independent). Verdicts: `2026-10-19-chat-search.hand.json`; the replies: `2026-10-19-chat-search.rows.jsonl`.

| Reply | v1 | v2 | Hand | Note |
|---|---|---|---|---|
| parsley_carrot_fly on | no | no | no | no text: the model ran to the 2048-token cap; the app said it could not answer |
| mint_after_flower on | no | yes | yes | cut back to just above soil level: the cut-back fact |
| sage_speckles on | no | yes | yes | leafhopper damage, leaves safe to eat (written with U+2011 hyphen) |
| chives_white_dots on | no | yes | yes | allium leaf miner (written with U+2011 hyphen) |
| rosemary_prune on | no | no | no | says after flowering but usually late summer or early autumn; the fact is after the spring flowers fade |
| coriander_after_flower on | yes | yes | yes | stops producing new leaves, dies after seeding |
| thyme_repot_october on | yes | yes | yes | October not ideal; spring is best |
| basil_dm_cure on | yes | yes | yes | no simple cure; remove infected plants |
| basil_eat_flowering on | yes | yes | yes | yes; mostly about the flowers, leaf flavour milder |
| basil_plant_out on | yes | yes | yes | from early June |
| parsley_sow_out on | yes | yes | yes | mid-spring to late summer |
| coriander_bolt on | yes | yes | yes | bolting from warmth, sun, dry soil |
| rosemary_hardy on | yes | yes | yes | generally hardy in most of the UK |
| thyme_trim on | yes | yes | yes | mid to late spring, after flowering |
| thyme_mulch on | yes | yes | yes | grit or gravel |
| sage_prune on | yes | yes | yes | lightly in mid to late spring |
| chives_after_flower on | yes | yes | yes | snip the whole clump to about 5 cm |
| mint_rust on | yes | yes | yes | mint rust |
| basil_dm_cure off | yes | no | no | says not sure; 'no treatment mentioned' refers to the data, not a cure |
| basil_eat_flowering off | yes | yes | yes | yes, still edible, more bitter |
| coriander_bolt off | yes | yes | yes | bolting from warmth, light, stress |
| thyme_trim off | yes | yes | yes | late spring or early summer, before flowering |
| thyme_mulch off | yes | yes | yes | coarse sand or fine gravel |
| sage_prune off | yes | yes | yes | early spring (RHS: mid to late); counted as the fact |
| chives_after_flower off | yes | no | no | cuts the flower stems only, not the whole clump |

## Read with care (written after the run; not pre-registered)

- **Most of the gain is the off arm declining.** With search off the app tells the
  model to "answer from the blocks and tool results only", and Nano said "not sure" on
  17 of 30. When it did answer, it was correct on 13 of 13 by v1 (12 by v2). With
  search on it answered 29 of 30 and was correct on 25 of those (v1; 28 by v2). Search turns "not sure" into a sourced answer more than it makes the
  answers the chat would give anyway more accurate.
- **In-text citations are rare (M2, 3 of 30), but the page lists sources under 29 of
  30 search-on replies** (the chat's `sources`, shown under the reply). Every listed
  hit names the herb in its title, address or snippet (`names_herb` in the rows file).
  Two of the three in-text citations are US extension pages (trusted sites, but not UK).
- **Rubric v1 and v2 differ on 5 of 60 replies**, the same 5 where v1 and the hand
  check differ: v2 passes `sage_speckles`, `chives_white_dots` (U+2011 hyphens) and
  `mint_after_flower` ("just above soil level") with search, and fails `basil_dm_cure`
  ("I'm not sure ... no treatment mentioned") and `chives_after_flower` (cuts the
  flower stems, not the clump) without. No other reply changes.
- **Changed after the run:** `summarise` sorts rows by question before the bootstrap,
  so the draws do not depend on the order threads finished (paired M1 unchanged; the
  off-arm M1 interval moved from [0.333, 0.667] to [0.333, 0.700]). The runner's budget
  guard and error handling were tightened, and rubric v2 added; none touched the rows.
- 33 search_web calls but 31 Tavily searches sent: calls past the chat's 3-a-round
  limit get an error result with no search (`mint_rust` asked for 5).
- **The rows file** (`2026-10-19-chat-search.rows.jsonl`) holds each reply, its cited
  addresses, search queries, hit titles and addresses (no snippets), scores and cost. It
  has no keys or prompts. Region and state names in the replies and hit titles are
  written as "[place]"; it still holds "UK" and "British", plant names such as Thai
  basil and Japanese parsley, and the trusted sites' web addresses (one is a US state
  university's).

## Follow-ups

- **Product finding:** one search-on reply (`parsley_carrot_fly`) ran to the
  2048-token cap and came back empty, so the page said "I could not form an answer to
  that". The chat loop should catch a reply cut off at the cap and retry or answer
  without tools.
- The chat seldom cites in its text, though the prompt asks it to; and when it does it
  cites US pages. Worth a prompt change, measured on this same set.
