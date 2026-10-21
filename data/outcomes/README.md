# Care outcomes and problem signs (UK)

- `outcomes_uk.json`: for each plant, care action and month, what happens if you do it
  now and if you don't, plus any caution. Loaded by `src/herbtwin/outcomes.py`, which
  checks every row (at most 30 words a field, a URL for every source).
  A key starting with `_` (such as `_note`) is a maintainers' note: never loaded or shown,
  and skipped by the copied-text check.
- `problem_signs_uk.json`: what each pest or disease looks like, one line per problem.

Compiled by hand from the publishers named in each row's `sources` (mostly RHS advice
pages, plus Clemson HGIC, NC State and other university extension services, and the
American Orchid Society). **Facts only, restated in our own words.** Our wording is MIT;
the cited pages stay their publishers' copyright, and no publisher endorses this data.
Before shipping a new or changed row, run `uv run python scripts/check_copied_text.py`:
it fails if a field copies 8 or more words in a row from a page the row cites.
