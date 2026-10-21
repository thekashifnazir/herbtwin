# Seasonal norms (UK), per plant per month

What is normal for a plant in each month of a UK year, so the app can say "leave it, this
is normal for the time of year" (mint brown to the rhizome in October) and name the signs
that would not be normal now. Built 4 to 5 Oct 2026.

- Data: `data/seasonal/norms_uk.json`, one entry per plant per month (360 entries, 12 of them the `mentha` genus).
- Code: `src/herbtwin/seasonal.py`. `normal_for(plant, month)` takes the scientific key or
  any common name, any case, and returns `None` for an unknown plant (say "no seasonal
  data"). `plants()` lists the keys.
- Each entry: `status` (what is happening now), `normal_signs` (looks bad, is normal now),
  `problem_signs` (would not be normal now), `next_change` and its month, `evidence_tier`,
  `sources`.

## Coverage

| Group | Plants | Months |
|---|---|---|
| Garden (outdoor, London climate, many in pots) | sage, purple sage, rosemary, thyme, bay, oregano, French tarragon, mint, lemon balm, garlic chives, chives, parsley, basil, coriander, dill, rose, soft shield fern, male fern, Japanese maple | all 12 |
| Genus (`mentha`, added 5 Oct 2026) | any mint the photo reader names only as "Mentha sp."; answers to "mentha", "mint (unknown kind)", "mentha sp.", "mentha spp.", "unknown mint" (plain "mint" stays spearmint). Copies the spearmint rows with genus wording, all tier D (one below the species), RHS mint guide cited: all garden mints are herbaceous and die back over winter | all 12 |
| Houseplants (`indoor: true`) | peace lily, spider plant, pothos, snake plant, monstera, fiddle-leaf fig, aloe, ZZ plant, Christmas cactus, moth orchid | all 12; quiet months repeat |

Conventions: annuals out of season (basil in January) are `normal_dieback` with the
sowing month as the next change; purple sage is a separate entry and does not answer to
"sage"; a rose is the genus `rosa` (garden hybrids).

## How it was sourced

Local reference files first (`herb-care-packs.md`, `herb-growth-facts.md`,
`risk-models.md`, `community-and-open-media.md` and the open texts), then RHS pages fetched directly, then university extension pages
(NC State, Clemson, Wisconsin) and the American Orchid Society. Under 30 web searches in
all; every cited URL was fetched during research, and a scripted re-check after merging got
a page back from all but four (those four refuse scripted requests). A check after merging found that summarised
fetches had misread the RHS month calendars for basil, coriander and dill, so those
calendars were re-read from the raw page and the rows corrected. Do the same before
trusting any month taken from a calendar graphic.

The 10 houseplants' winter watering was first cross-checked against Plantfolio's seasonal
watering intervals. Plantfolio is CC BY-NC-SA 4.0, so it is no longer cited (13 Oct 2026):
every houseplant row still cites the RHS or NC State page that states the same thing (for
example NC State: snake plant watered every one to two months in winter, ZZ plant
about once a month in winter).

Tiers follow `risk-models.md`. **C** (293 entries): an RHS or extension source states
this month's behaviour, or names a month range or meteorological season (spring March to
May, autumn September to November) that covers it. **D** (55, plus the 12 `mentha` genus rows): the month is our
inference from vaguer wording ("dies back over winter", "after the first hard frost"),
or rests on Wikipedia, a shop listing or a general houseplant guide. No A or B: no
peer-reviewed month-level phenology was found for these plants.

Month-level timing exists for: RHS sow, plant and harvest calendars (basil, coriander,
dill, rosemary, oregano); Christmas cactus flowering and rest; aloe's winter rest;
houseplant growing-season ranges; rose pruning; pest windows (allium leaf miner, carrot
fly, celery leaf miner, leaf-rolling sawfly, bay sucker). Everything else (herb
flowering, herbaceous dieback, fern fronds, maple colour, most houseplant winters) is
season-level mapped to months.

Where sources disagreed, the more cautious norm was kept, so a real problem is not
called normal. Examples: oregano treated as deciduous (a bare but firm crown is normal,
a soft one is not); lemon balm dieback from November, not October; frost-browned rosemary
tips a problem, not normal; rose leaf drop normal only in October and November; leaf drop
on a fiddle-leaf fig and bud drop on a Christmas cactus always problems.

A cross-check against a separate eval set (5 Oct 2026) corrected norms that could reassure
wrongly or alarm wrongly:

- Basil August to November: basil downy mildew (*Peronospora belbahrii*, in the UK since
  2010, outdoor and protected crops; AHDB PE 024a) yellows leaves between the veins, then
  browns or blackens them (UF/IFAS PP271, UConn). October and November now list its signs
  for the outdoor plant (grey-purple fuzz under the leaf), and blackened leaves are normal
  only after a cold night.
- French tarragon: herbaceous, top growth dies back in autumn (RHS). October is now
  `normal_dieback`; August and September point to October as the next change.
- Male fern September: deciduous (RHS plant page), fronds go over in autumn (RHS fern
  guide). A few outer fronds browning in moist compost is now normal; many fronds crisp in
  dry compost stays a problem.
- Chives and garlic chives October: autumn yellowing now comes
  with the rust (RHS leek rust, mid-summer to late autumn) and onion white rot (RHS) signs
  that tell disease from dieback; garlic chives November gains the rust sign.

## Gaps

- Mint's October dieback is tier D: RHS says "dies back over winter"; October is our
  reading of when that starts in London. The spring regrowth month (March) comes from mint
  rust timing on Wikipedia; RHS only says spring.
- Timing is for lowland southern England. Scotland and northern England run two to four
  weeks later in spring and earlier in autumn; nothing here adjusts for that, nor for an
  unusually early frost.
- Garlic chives, tarragon and parsley have the most D entries (dieback timing from
  Wikipedia or "after the first frost").
- Parsley autumn and winter yellowing has no leaf-spot (Septoria) or virus sign: the RHS
  parsley guide lists only pests, so none was added without a source.
- Houseplant entries assume a heated UK home; none covers a cold porch or conservatory.
- Several winter signs are our own wording paired with a source-backed problem sign
  (for example "an occasional oldest leaf yellowing" on a peace lily against "several
  leaves yellowing while the compost stays wet").
