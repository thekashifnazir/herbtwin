# The twin test at scale: 2026-10-18-twin-at-scale

- Advisor `nvidia/nemotron-3-super-120b-a12b`, the app's panel (3 asks, live temperatures); 2 repeats; the run started from git `617a435`
- Rows 480: 480 answered; spent this invocation $0.0000 (cached rows are not re-paid)
- 120 scripted cases (10 herbs x 6 scenarios x pot/ground; UK places: Edinburgh, London, Manchester, Truro); the twin finds a risky day in 42. Both arms see the same WHERE, WEATHER, CARE FACTS and LIGHT blocks; only PLANT MODEL differs.
- The metrics and the decision rule are in the header of `src/herbtwin/evals/twin_at_scale.py`, fixed before any paid call. **P1 is the pre-registered decision metric**; P2 to P4 look at subsets.
- **Caveat:** the reference is the twin's own better choice, so a gain shows the
  advisor follows the twin's forecast, not that the twin is right.

| Metric | Twin off | Twin on | On minus off (95% CI) |
|---|---|---|---|
| P1 Main action is the twin's better choice (all cases) | 0.946 [0.908, 0.979] (n=240) | 0.958 [0.925, 0.988] (n=240) | +0.013 [-0.025, +0.054] |
| P2 ...where the twin finds a risky day | 0.929 [0.845, 0.988] (n=84) | 1.000 [1.000, 1.000] (n=84) | +0.071 [+0.012, +0.155] |
| P3 Leave it, where the twin finds none | 0.955 [0.910, 0.994] (n=156) | 0.936 [0.878, 0.981] (n=156) | -0.019 [-0.071, +0.026] |
| P4 Treatment as main action (healthy plants) | 0.000 [0.000, 0.000] (n=240) | 0.000 [0.000, 0.000] (n=240) | +0.000 [+0.000, +0.000] |

P1's interval includes 0: by the pre-registered rule, no measurable overall change.

P2 rests on few cases: 4 of 42 risky cases moved to the twin's choice with the twin, 0 the other way (sign test p = 0.125): basil/frost/ground, basil/frost/pot, basil/uk_frost/pot, thyme/dry/ground.

S1, the app's final call on the twin-on arm (after `follow_the_twin`):

| Metric | App, twin on |
|---|---|
| P1 Main action is the twin's better choice (all cases) | 0.958 [0.925, 0.988] (n=240) |
| P2 ...where the twin finds a risky day | 1.000 [1.000, 1.000] (n=84) |
| P3 Leave it, where the twin finds none | 0.936 [0.878, 0.981] (n=156) |
| P4 Treatment as main action (healthy plants) | 0.000 [0.000, 0.000] (n=240) |

S2, P1 by scenario:

| Scenario | Off | On |
|---|---|---|
| frost | 0.800 | 0.900 |
| near | 0.925 | 0.850 |
| uk_frost | 0.975 | 1.000 |
| dry | 0.975 | 1.000 |
| wet | 1.000 | 1.000 |
| benign | 1.000 | 1.000 |

S3, mean panel agreement: off 0.936, on 0.940
