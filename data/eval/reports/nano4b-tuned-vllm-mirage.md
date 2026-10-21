# Advice eval nano4b-tuned-vllm-mirage

- Set `actions_mirage`; model `nano4b-tuned:think` (ollama); prompt hash `7ba44f01d95b`; git `e74d519`
- Items 200: 200 scored, 0 missing, 0 invalid, 0 call errors

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.420 | 0.345 to 0.490 | 200 |
| primary_in_truth | 0.630 | 0.560 to 0.700 | 200 |
| jaccard | 0.332 | 0.294 to 0.370 | 200 |
| over_treatment | 0.020 | 0.005 to 0.040 | 200 |
| water_conflict | 0.035 | 0.010 to 0.065 | 200 |
| unguarded_water_conflict | 0.005 | 0.000 to 0.015 | 200 |
| asked_when_expert_asked | 0.500 | 0.389 to 0.611 | 72 |
| primary_ok_if_asked_too | 0.420 | 0.345 to 0.490 | 200 |
| hedge_had_answer | nan | - | 0 |

Expert primary: `{'ask_first': 20, 'dont_water': 5, 'leave_normal': 33, 'move_light': 2, 'other': 44, 'prune': 34, 'shelter': 11, 'treat_or_remove': 25, 'water': 26}`

Our primary: `{'dont_water': 14, 'leave_normal': 67, 'move_light': 8, 'other': 49, 'prune': 33, 'shelter': 8, 'treat_or_remove': 14, 'water': 7}`
