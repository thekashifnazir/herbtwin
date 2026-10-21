# Advice eval nano30b-tf-p7ba

- Set `actions_se`; model `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` (tokenfactory); prompt hash `7ba44f01d95b`; git `fa701d0`
- Items 150: 148 scored, 0 missing, 2 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $0.0139

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.358 | 0.284 to 0.432 | 148 |
| primary_in_truth | 0.561 | 0.480 to 0.635 | 148 |
| jaccard | 0.297 | 0.259 to 0.337 | 148 |
| over_treatment | 0.182 | 0.122 to 0.250 | 148 |
| water_conflict | 0.054 | 0.020 to 0.088 | 148 |
| unguarded_water_conflict | 0.000 | 0.000 to 0.000 | 148 |
| asked_when_expert_asked | 1.000 | 1.000 to 1.000 | 31 |
| primary_ok_if_asked_too | 0.358 | 0.284 to 0.432 | 148 |
| hedge_had_answer | nan | - | 0 |

Expert primary: `{'ask_first': 6, 'dont_water': 18, 'leave_normal': 27, 'move_light': 9, 'other': 28, 'prune': 10, 'shelter': 4, 'treat_or_remove': 37, 'water': 9}`

Our primary: `{'dont_water': 1, 'leave_normal': 44, 'move_light': 16, 'other': 6, 'prune': 11, 'shelter': 3, 'treat_or_remove': 50, 'water': 17}`
