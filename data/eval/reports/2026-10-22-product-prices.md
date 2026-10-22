# Prices for the things to buy: four ways tried, none good enough (22 Oct 2026)

"Where to get it" and "Handy to have" link UK garden retailers' product pages found with
Tavily (#429). Kash asked for prices. We tried four ways to read one. The bar for every
way was **zero wrong prices**, because a wrong price is worse than none. None passed, so
the card shows the item and the shop, not a price (#434). Kash, 22 Oct: "sounds like
pricing isn't working so we should just find items and places and just keep it in our
testing to show it wasn't working well".

| Way | Pages | Clean price | Wrong | Cost |
|---|---|---|---|---|
| 1. The Tavily search snippet, one clear £ figure (live in #429) | 21 | 3 | **2** | in the search |
| 2. Tavily Extract of the whole page | 3 live fleece pages | 1 | 0 | about 4 Tavily credits |
| 3. Our own fetch of the shop's product tags (JSON-LD, meta) | 15 | 6 | 0 | 7 Tavily credits |
| 4. Nemotron 3 Nano reads Tavily's page text | 21 | 11 | **9** | 12 Tavily credits, $0.0011 of Nano |

## 1. The search snippet (live from #429 until #434)

The rule is in `shops.listed_price`. It takes a price only when the snippet holds exactly
one £ figure. It refuses a range page, a delivery threshold, a price filter, a saving, an
instalment, a per-unit price, a "from" price, and a figure cut off at the end of the text.

On the 21 pages of probe 4, scored against the same blind truth labels, it gave 5 prices:
**3 right and 2 wrong, both on B&Q**. B&Q's snippet holds a carousel of a different
product: "Plant Fleece Covers with Zip 4 pcs … £96.65 Free home delivery" on a fleece
that costs £255.99, and £23.65 on one that costs £10.99. That figure is the only one in
the text, so it looks clear. The price display was removed in #434; the two snippets are
kept as test fixtures (`tests/test_handy_to_have.py`, `BQ_CAROUSEL`).

## 2. Tavily Extract (basic and advanced)

Extract was run on the 3 fleece pages from the live search: Harrod Horticultural, B&Q and
Crocus.

- **Crocus:** a clean price (basic: "£12.99 In stock").
- **Harrod:** the page text holds only related products' "From £8.95", P&P charges and
  "Gift Ideas Under £25". Its own price is not in the text, even with advanced Extract.
- **B&Q:** a range page, with no prices.

That is **1 of 3 clean**, against a bar of 2 of 3.

A second Crocus page was clean too. Dobbies failed basic Extract. Advanced Extract read
it ("Current price £9.59, was £11.99"). A whole page always holds many figures, so each
retailer would need its own parse.

Cost: about 4 credits (2 basic calls, 1 advanced call).

## 3. Our own fetch of the shop's product tags

This method is the common one for Google Shopping data:

- Tavily finds a product page, and we drop range pages.
- Our server makes one GET per page, after checking robots.txt, with a 5 s timeout and an
  honest User-Agent (herbtwin, what it does, the repo).
- It reads schema.org Product JSON-LD `offers.price` in GBP, or the
  `product:price:amount` / `og:price:amount` meta tags.

Results, on 15 product pages from 7 searches and 6 retailers:

- **6 clean (40%)**, against a bar of 60%: Harrod 5 of 5 from JSON-LD, Homebase 1 of 1
  from meta.
- **9 blocked, from 4 of 6 retailers**: Crocus 403 on 4 of 4, Dobbies 403 on 2 of 2,
  Thompson & Morgan 403 on 1 of 1, B&Q 503 on 2 of 2 within 15 ms. The bar was that no
  retailer blocks us.
- robots.txt allowed every page, so the blocks are the sites' bot walls. Getting past
  them would mean pretending to be a browser, which we won't do.
- 0 timeouts. Median fetch 104 ms over all 15, 653 ms on the 6 that returned a page.
- Harrod's JSON-LD gives one price for a page that sells several sizes, probably the
  smallest.

Cost: 7 Tavily credits; the fetches are free.

## 4. Nemotron 3 Nano reads the price (pre-registered)

The pre-registration is `2026-10-22-product-prices/PREREG.md`, written before any Nano
call. The truth labels' sha256 was recorded before Nano ran:
`a7b2e031a5b60df3c94fdbd912aab0b5d0a1aba75a7ce8bd511b520e9b5cd5c0`.

**Pages.** 21 product pages from 6 retailers: B&Q 10, Harrod 5, Crocus 4, Dobbies 1,
Homebase 1, Thompson & Morgan 1.

- 15 came from 7 Tavily searches (`"<item> £ price"`, `include_raw_content` markdown,
  country united kingdom).
- 6 came from probe 3 (Harrod and Homebase).
- 12 pages with no page text got advanced Extract (query "price £", 3 chunks).
- 2 had the snippet only.

**Truth.** A fresh subagent, blind to Nano, labelled each page from the same text: 11 had
one price, 2 sold "several" sizes, and 8 showed no price for the product.

**Nano.** NVIDIA Nemotron 3 Nano (30B-A3B) on Token Factory, through the app's adapter,
thinking off, temperature 0, with a JSON schema. It was told: "null if not sure; never a
delivery threshold, filter, 'from' or instalment price". Its input was the page text
trimmed to 250 characters around each £. One run, scored once.

**Result: 11 of 21 right (52%), 9 wrong.** The bar was zero wrong, plus 30 points of
coverage over the snippet rule.

- It **invented prices** where the text has none: Homebase £1.50 from no page text at
  all, and three B&Q pages (£14.99, £6.92, £11.49).
- It **took a delivery charge or another product's price**: Harrod Nemaslug £3.95 (P&P;
  JSON-LD £19.95), Harrod insect mesh £55.00, Harrod fleece £19.95 (JSON-LD £13.95).
- It gave **one price for a page that sells several sizes** (£6.95, £4.45). Both match the
  JSON-LD default, but they are wrong under the pre-registered rule.

The snippet rule on the same pages: 3 of 21 right (14%), 2 wrong. Nano's coverage is 38
points higher, but its wrong prices fail the bar outright.

Speed and cost: median 854 ms added per page; $0.0011 of Nano for 21 calls; 12 Tavily
credits (7 searches, 5 Extract).

## Files

In `2026-10-22-product-prices/`:

- `PREREG.md`: the pre-registration.
- `truth.json`: the blind labels, with a short quote for each.
- `nano_out.json`: Nano's replies, latency and tokens.
- `score.json`: each page scored for Nano and the snippet rule, with JSON-LD where known.
- `tag_fetch.json`: probe 3, one row per page.

The page text itself is not committed; it is the retailers' content.
