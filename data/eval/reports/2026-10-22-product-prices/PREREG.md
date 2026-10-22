# Pre-registration: Nemotron 3 Nano reads a product's price from Tavily text (22 Oct 2026)

Written before any Nano call. Scratchpad probe only; no repo change.

## Data (fixed now)
- 21 product pages, 6 retailers (pages.json): 15 from 7 Tavily searches ("<item> £ price",
  include_raw_content markdown, country united kingdom, basic), range pages dropped; plus the
  tag probe's 5 Harrod and 1 Homebase pages. Pages with no raw text got advanced Extract
  (query "price £", 3 chunks). 2 pages have the search snippet only.
- Truth: a fresh subagent, blind to Nano, labels each page from the same text Tavily gave
  (file + snippet): one GBP price for this product as listed (the current price on a sale),
  "several" (options at different prices, no single default), or "none" (no price for this
  product in the text). truth.json; its sha256 is recorded in this file before Nano runs.
  JSON-LD from the tag probe (Harrod, Homebase) is a cross-check only.

## Nano run
- Model nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B via the app's TokenFactoryAdapter, temperature 0,
  JSON reply {name, price_gbp or null, pack_size or null, retailer, is_single_product}.
- Input: the title, the snippet, and the page text trimmed to 250 chars either side of each
  "£" (merged, at most 4000 chars). Prompt says: null if not sure; never a delivery threshold,
  filter, "from" or instalment price.
- One run per page. Scored once.

## Scoring
- Nano says a price: right if it equals the truth's single price (to the penny); WRONG if the
  truth is a different price, "several" or "none". is_single_product false -> treated as null.
- Coverage = right / 21. Snippet rule baseline: shops.listed_price(url, snippet) on the same
  pages, scored the same way.
- Bar to build: Nano coverage >= baseline + 30 points AND 0 wrong. Otherwise do not build.
- Reported too: latency per call (median), tokens and cost, JSON-LD agreement.

## Truth recorded
- truth.json sha256 a7b2e031a5b60df3c94fdbd912aab0b5d0a1aba75a7ce8bd511b520e9b5cd5c0, before any Nano call (2026-10-22T15:02:07Z).
