# Photo-read figures re-measured with the low_light prompt: pre-registration (22 Oct 2026)

Written before any paid call; its sha256 goes in the report.

**Why.** #456 adds a low_light clause to the photo prompt (stages/observe.py SYSTEM), and the
published photo-read figures predate it (integrator's review of #456).

**Code.** Branch fix/indoor-light-from-photo-and-window at e6cef4e4 (main merged in). Same
harnesses, sets and scoring as the published runs; model zai-org/GLM-5.3-Flash, no backup.

**Runs.**
1. Species: `scripts/eval.py --set species_gbif --backend tokenfactory --model
   zai-org/GLM-5.3-Flash` (150 GBIF photos, as 2026-10-16-species_gbif-glm-5-3-flash-scene).
2. Problem check: `scripts/eval_problem_check.py --per-class 24 --healthy 150 --seed 7
   --month 10` (as 2026-10-17-problem-check).

**Published figures and when they change (fixed now).**
- Species top-1, published 0.846 (95% CI 0.785 to 0.899, 149 scored). It moves if the new
  top-1 falls outside that interval; then the Devpost story and About change to the new figure.
- Healthy false alarms, published 0 of 149. Any false alarm moves it.
- Problems named wrong, published 0. Any wrong name moves it.
- Problems named right, published 33 (33 of 57 in scope). It moves if the new count differs by
  more than 5; within 5 is the run-to-run noise of a 57-photo set, and is left.
- Secondary, no bar: how often low_light >= 1 on the 150 species photos (healthy, mostly
  outdoor) and on the 150 healthy problem-check photos.

**Budget.** About $0.15 (species) + $0.50 (problem check); stop at $1.50.
