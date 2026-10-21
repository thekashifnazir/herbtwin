# Plant model on vs off: 2026-10-17-plant-model-ablation

- Advisor `nvidia/nemotron-3-super-120b-a12b`, the app's panel (3 asks); 2 repeats; git `9feb86b`
- Rows 240: 240 answered; spent this invocation $0.0000 (rows cached from an earlier one are not re-paid)
- 60 synthetic items (5 herbs x 4 weather scenarios x 3 variants). Both arms see the
  same WEATHER, CARE FACTS and YOU TOLD US blocks; only PLANT MODEL differs.
- **Caveat:** each scenario's right answer is a gardener's rule on the same weather the
  plant model reads. A gain shows the advisor uses the model's forecast, not that its
  advice is more correct against experts.

| Metric | Off | On | On minus off (95% CI) |
|---|---|---|---|
| Main action fits the rule | 0.925 [0.858, 0.983] | 0.958 [0.917, 0.992] | +0.033 [-0.033, +0.108] |
| Frost scenario: did not shelter | 0.200 [0.000, 0.400] | 0.033 [0.000, 0.100] | -0.167 [-0.367, +0.000] |
| Watered outside the dry spell | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.000 [+0.000, +0.000] |
| Treatment as main action | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.000 [+0.000, +0.000] |

| Scenario | Off | On |
|---|---|---|
| frost | 0.800 | 0.967 |
| wet | 0.933 | 0.933 |
| dry | 0.967 | 0.933 |
| mild | 1.000 | 1.000 |

Items where the plant-model arm did worse: rosemary/dry/pot_told, rosemary/wet/pot_told, thyme/dry/ground, thyme/wet/pot_told

Items where it did better: basil/frost/ground, basil/frost/pot, basil/frost/pot_told, rosemary/dry/ground, rosemary/wet/pot
