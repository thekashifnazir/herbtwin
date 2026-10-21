# Advice eval nano30b-tf2-p7ba

- Set `actions_se`; model `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` (tokenfactory); prompt hash `7ba44f01d95b`; git `fa701d0`
- Items 150: 150 scored, 0 missing, 0 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $0.0115

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.353 | 0.273 to 0.427 | 150 |
| primary_in_truth | 0.560 | 0.480 to 0.640 | 150 |
| jaccard | 0.300 | 0.261 to 0.342 | 150 |
| over_treatment | 0.193 | 0.133 to 0.260 | 150 |
| water_conflict | 0.073 | 0.033 to 0.120 | 150 |
| unguarded_water_conflict | 0.000 | 0.000 to 0.000 | 150 |
| asked_when_expert_asked | 1.000 | 1.000 to 1.000 | 31 |
| primary_ok_if_asked_too | 0.353 | 0.273 to 0.427 | 150 |
| hedge_had_answer | nan | - | 0 |

Expert primary: `{'ask_first': 6, 'dont_water': 18, 'leave_normal': 27, 'move_light': 9, 'other': 29, 'prune': 10, 'shelter': 4, 'treat_or_remove': 37, 'water': 10}`

Our primary: `{'dont_water': 1, 'leave_normal': 47, 'move_light': 16, 'other': 5, 'prune': 10, 'shelter': 3, 'treat_or_remove': 49, 'water': 19}`
