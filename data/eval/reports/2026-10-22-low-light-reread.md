# Photo-read figures with the low_light prompt (22 Oct 2026)

**Result: every published photo-read figure holds within its pre-registered noise band, so
the Devpost story and About are unchanged.** Pre-registered in `2026-10-22-low-light-reread/PREREG.md`
before any call (sha256 `f4aca46f892eaa8acba422f0928a1f4f0f73e3a98b1ae148760108a39c2bca63`).
One edit after scoring: in PREREG.md, the Devpost file's name now reads "the Devpost story", because
the public export forbids naming a file it leaves out. Swap the words back and the file
hashes to the sha256 above again. Code e6cef4e4, GLM-5.3-Flash, no backup; observe prompt hash `d9d11b7db0c7` (published runs:
`35b1b37a0ad4`). Same harnesses, sets and scoring. Scored once.

| Figure | Published | Now | Rule | Docs |
|---|---|---|---|---|
| Species top-1 (149 GBIF photos) | 0.846 (CI 0.785 to 0.899) | **0.826** (CI 0.758 to 0.886) | moves only outside the old CI | unchanged |
| Healthy false alarms | 0 of 149 | **0 of 149** | any alarm moves it | unchanged |
| Problems named wrong | 0 | **0** | any wrong name moves it | unchanged |
| Problems named right | 33 (of 57 in scope) | **29** (of 51 in scope) | moves if more than 5 apart | unchanged |

- Species top-1 is 0.02 lower (top-3 0.919 against 0.933). This is inside both runs'
  intervals; the pot_fit re-read on 21 Oct gave 0.859 with the same set. One call failed in
  each run.
- Problem check by class (right / photos), 17 Oct → now: basil downy mildew 8 → 9, mint rust
  14 → 14, powdery mildew 10 → 6, aphids 1 → 0, slugs 0 → 0: 4 fewer for powdery mildew, 1 fewer
  for aphids and 1 more for downy mildew. Fewer powdery-mildew photos were read as a herb the
  app knows (in scope 13 → 9).
- **Secondary, low_light on the 149 healthy species photos:** 0 on 121, 1 on 3, 2 on none, and
  left out on 25 (a missing score is "not known", never "no sign"). All 3 fires were read as
  outdoor plants: species_gbif/5230907367, 6184932300 and 6235849867. The tally, from the run's
  rows, is `2026-10-22-low-light-reread/low_light_tally.json`.

Files: `2026-10-22-species-low-light.summary.json` and `.md`,
`2026-10-22-problem-check.summary.json`. Spend: species $0.135 (recorded); problem check not
recorded by its script, about $0.45 at GLM's per-read cost.
