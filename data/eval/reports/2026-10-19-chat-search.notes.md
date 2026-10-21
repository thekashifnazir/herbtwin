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
