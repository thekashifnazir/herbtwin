# UK crop calendar (compiled, with per-row provenance)

Sow, plant and harvest month windows for {{n}} crops grown in UK gardens, allotments and
containers. Each row records where its facts came from. It fills the gap named in
`docs/reference/soil-area-and-what-to-grow.md` §4–6: no open dataset gives UK month windows
per crop.

- Compiled: 2026-10-12. Pages were fetched the same day.
- Calibrated to mid-England: last frost about 11 April, first frost about 14 November.

## Files

| File | What |
|---|---|
| `calendar.json` | List of {{n}} records: the full schema below, including `sources` and `cross_checks`. |
| `calendar.csv` | The same rows flattened. Months are space-separated integers; source URLs are space-separated. |
| `disagreements.md` | Crops where two sources differ by more than one month in a window. Generated from `cross_checks`. |

Coverage by group: {{n_vegetable}} vegetables, {{n_herb}} herbs, {{n_fruit}} fruit and {{n_edible_flower}} edible flowers. Tulips and
other non-food plants are excluded.

## Record schema

| Field | Meaning |
|---|---|
| `id`, `common_name`, `scientific_name`, `group` | Identity. `group` is one of vegetable, herb, fruit, edible_flower. |
| `life_cycle` / `grown_as` | Botanical life cycle, and how UK gardeners grow it (for example, beetroot is a biennial grown as an annual). |
| `sow_indoors` | Months to sow in modules, pots or trays under cover (windowsill, greenhouse or cold frame), for transplanting later. |
| `sow_outdoors` | Months to sow direct into the final spot or an outdoor seedbed. Sowing under a cloche or fleece counts as outdoors. |
| `plant_out` + `plant_out_material` | Months to plant transplants, plugs, sets, cloves, tubers, crowns, bare-root or pot-grown plants, or divisions. |
| `harvest` | Months to harvest. |
| `hardiness_rhs` + `hardiness_source` | RHS H-rating from the RHS plant page, or from grow-your-own text. Some ratings come from a named cultivar page. Species ratings can mislead for overwintering cultivars such as winter lettuce or round peas (lettuce and pea are H2); `notes` says so where it applies. |
| `container` | `ground_only`, `min_litres`, `min_depth_cm`, `min_width_cm`, `note`. |
| `sun` | One of full, full_or_part, part_or_shade. |
| `soil` | `clay_ok`, `needs_drainage`, `ph` (acid_required, acid_to_neutral, neutral_to_alkaline, lime_tolerant, any), `note`. |
| `days_to_harvest` | `{min, max, basis, source}`, or null. |
| `overwinters_outdoors` | One of y, n, with_protection. |
| `mild_areas_only` | Which windows are only for mild or sheltered areas. Those months stay in the lists. |
| `sources` | `[{url, publisher, tier, used_for}]`. |
| `evidence_tier` | C if the calendar months come from RHS or Garden Organic; otherwise D. |
| `heuristic_fields` | Fields filled by our own horticultural judgement rather than a cited source. Treat these as tier D. |
| `cross_checks` | The raw month lists each source published, before calibration: `rhs_raw`, `garden_organic`, `real_seeds`, and others where used. |
| `notes` | One or two sentences in our own words. |

Months are whole-month integers. A month is included if the activity is advised for any
part of it, so "mid-October to November" becomes `[10, 11]`.

## Method

1. **Crop list.** The RHS grow-your-own sitemap lists 107 crop pages. Variety types whose
   windows differ were split into separate rows:
   - cabbage: summer/autumn, winter, spring;
   - onion: seed, spring sets, autumn sets;
   - peas: main, round-seeded;
   - potato: first early, second early, maincrop;
   - lettuce: summer, winter;
   - radish: summer, winter;
   - raspberry: summer, autumn;
   - savory: summer, winter;
   - chard and perpetual spinach.

   We added 37 crops with no RHS grow-your-own page (winter salads, oriental greens,
   garlic chives, minor herbs, edible flowers, cranberry and lingonberry, and unusual
   crops). The Plant Variety Database (`data/external/s1/pvd_varieties.csv`, CC BY 4.0)
   served as a cross-check of which food species to cover. It is US-centred, so it was not
   used for months.
2. **Calendars.** The month blocks on RHS grow-your-own pages ("Sow", "Plant",
   "Plant out", "Harvest") were parsed from the HTML. RHS gives a single "Sow" row, so the
   page text was used to split it into indoor and outdoor sowing.
3. **Cross-checks.** Two sources were compared against the RHS calendars:
   - Garden Organic growing guides, whose "Growing calendar" separates indoor and outdoor
     sowing;
   - the Real Seeds monthly sowing guide and product pages.

   For crops without a page from RHS or Garden Organic, we used UK seed-company and
   nursery pages (tier D):
   - Real Seeds, Sarah Raven, Marshalls, Jekka's Herb Farm, BBC Gardeners' World;
   - a few single nursery pages.
4. **Conditions.** RHS Plant Finder pages gave the H-rating, sun, moisture, pH and soil
   types (126 crops matched by species or a representative cultivar). Container sizes come
   from RHS or Garden Organic text where stated; otherwise they are judged and listed in
   `heuristic_fields`.
5. **Calibration to mid-England.**
   - Tender crops have no outdoor sowing before May and no planting out before late May or
     June.
   - Months that suit only mild areas are kept but named in `mild_areas_only`.
   - The RHS raw lists stay in `cross_checks.rhs_raw`, so the calibration can be audited or
     redone for another location.
6. **Validation.** Every record passed a schema check: month integers sorted and unique,
   enums valid, and at least one source.

## Coverage (share of {{n}} rows with a value)

| Field | Coverage |
|---|---|
| Sow, plant and harvest windows | harvest 100%. 99% have at least one sow or plant window; citrus is bought as a plant, with no window. |
| `sun`, `soil`, `overwinters_outdoors` | 100% |
| `container` | 99%. About a third of container figures are our judgement (see `heuristic_fields`). |
| `hardiness_rhs` | 79%. Tender annuals often have no RHS rating. |
| `days_to_harvest` | 57%. Mostly annuals; usually null for perennials and fruit. |

Evidence tier: {{n_tier_c}} rows are C and {{n_tier_d}} are D. Calendar months were judged for parts of 35
rows: `plant_out` in 24 and `harvest` in 21, mostly the extra crops.

## Sanity check: 12 October, mid-England

35 crops have October in `sow_outdoors` or `plant_out`. Against the RHS-sourced October
list in the reference doc, 11 of 12 food items are found:
- found: garlic, broad bean, onion sets, round peas, lamb's lettuce, land cress, winter
  lettuce, spring cabbage plugs, blueberry, chives division and mint division;
- missed: rhubarb, because the RHS calendar plants crowns from November to March. Garden
  Organic's September–April window would include October; see `disagreements.md`.

## Licence and use

These are **facts compiled with citations, not copied text**. All month lists, ratings and
short notes are restated in our own structured words, and no source prose is stored.

- **RHS terms:** site content is RHS copyright. We hold facts, such as which months and
  which H-rating, with a link to each page. Do not paste RHS text into the app.
- **Garden Organic** and the seed companies: same treatment.
- **Plant Variety Database:** CC BY 4.0 (bripatch/plant-variety-database). Attribute it
  wherever its days-to-harvest values are used.

Before shipping this as public app data, keep the per-row source URLs visible or
attributable. Treat `heuristic_fields` as our own estimates.

## Known limits

- **Granularity.** Whole months only, so "late May" and "early May" look the same. Frost
  dates differ by about 2–3 weeks across England; shift tender windows for the north and
  for frost pockets.
- **One location.** Windows are for mid-England. Scotland and the north need later spring
  windows and earlier autumn ones; Cornwall and coastal areas widen the mild-area windows.
- **Variety averages.** Spring cabbage, winter cabbage and the potato types were derived
  from type descriptions on shared RHS pages.
- **Thin sources.** A few rows rest on one tier-D page: cape gooseberry, jostaberry,
  lingonberry, cranberry and some minor herbs.
- **Build scripts.** `scripts/build_crop_calendar.py` rebuilds these files from the curated
  records in `data/crop_calendar/curation.json` and a local page cache
  (`data/external/soil-and-crops/uk-crop-calendar-cache/`, `--offline` to skip fetching). The
  raw HTML is not redistributed.
