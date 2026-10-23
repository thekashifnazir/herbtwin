# What is normal each month (UK)

`norms_uk.json`: for each plant and month, what a healthy plant looks like (status and
normal signs), which signs are a problem, and what changes next. The photo reading and
the advice compare against it.

Compiled by hand from the pages named in each row's `sources`: mostly RHS, plus NC State,
Clemson and other university extension services, the American Orchid Society, and
Wikipedia pinned to a revision. Some rows cite our own notes in `docs/reference/`.
**Facts only, restated in our own words.** Wikipedia text is CC BY-SA 4.0 and none is
quoted. Our wording is MIT; the cited pages stay their publishers' copyright.
`scripts/check_copied_text.py` checks for copied text.

## Indoors (`indoor_care_uk.json`)

For a plant the photo shows indoors, where the outdoor season and the forecast don't apply:
what is normal in a room or on a windowsill this month, 3 to 5 care tips (light, water,
air, warmth, feeding or repotting) and at most one Also-do card. One row per group of
plants kept alike (soft herbs, woody herbs, leafy houseplants, succulents, the Christmas
cactus, the moth orchid) per run of months, plus `any indoor plant` for the rest. Plant
keys are the season table's. Same rules as above: RHS pages first (houseplant, cacti and
succulent, winter-care and herb pages), a Clemson herb sheet where RHS is silent, facts
only and in our own words; `scripts/check_copied_text.py` covers it. It assumes a heated
UK home.

## Outdoors (`outdoor_care_uk.json`)

The indoor table's twin, for a plant the photo shows outdoors in the UK: 2 or 3 care points
for the month (water, picking, trimming, shelter from winter rain), one row per group of
herbs kept alike (basil, leafy herbs, herbs that die back, woody herbs) per run of months,
with a herb on its own where its stage differs (parsley, coriander, rosemary, bay). What is
normal now comes from `norms_uk.json`, not this table. `pot_tips` (a pot out of the rain, a
feed in a pot, watering a pot in hot weather) are shown only for a pot or a container the
photo doesn't show; `bed_tips` only for a bed. Plants or months with no row (roses, ferns,
the maple, basil from November to May, dill from September) get no card. Facts from the RHS
grow-your-own pages for each herb, the RHS herbs-in-containers page and the RHS frost-damage
page, only in our own words; a job point (trim, feed, repot, divide) keeps to the outcome
table's months for that plant and job. The answer leaves out any point about a job its own
cards already decide. `scripts/check_copied_text.py` covers it.
