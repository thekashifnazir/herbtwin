# UK crop calendar

- `calendar.json`: sow, plant-out and harvest months, container size, sun and soil for
  each crop, with the source pages for each row. Built by `scripts/build_crop_calendar.py`;
  the "What can I grow here?" page reads it.
- `curation.json`: the builder's hand-made choices (which crops, which sources).
- `README.template.md`: the full schema and method. The builder fills it in on each
  build, with counts, and writes it next to its other outputs.

**Licence and use.** Facts compiled with citations, restated in our own words: RHS,
Garden Organic and the seed companies are copyright, so we keep which months and which
ratings, with a link, and none of their sentences. Days-to-harvest values marked as
coming from the Plant Variety Database
(https://github.com/bripatch/plant-variety-database) are CC BY 4.0
(https://creativecommons.org/licenses/by/4.0/), by Wind River Greens
(https://plants.windrivergreens.com). `scripts/check_copied_text.py` checks for copied text.
