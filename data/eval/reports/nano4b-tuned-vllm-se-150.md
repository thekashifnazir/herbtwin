# Advice eval nano4b-tuned-vllm-se-150

- Set `actions_se`; model `nano4b-tuned:think` (ollama); prompt hash `7ba44f01d95b`; git `e74d519`
- Items 150: 150 scored, 0 missing, 0 invalid, 0 call errors

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.400 | 0.320 to 0.480 | 150 |
| primary_in_truth | 0.593 | 0.513 to 0.667 | 150 |
| jaccard | 0.348 | 0.299 to 0.397 | 150 |
| over_treatment | 0.087 | 0.047 to 0.133 | 150 |
| water_conflict | 0.040 | 0.013 to 0.073 | 150 |
| unguarded_water_conflict | 0.007 | 0.000 to 0.020 | 150 |
| asked_when_expert_asked | 0.581 | 0.387 to 0.742 | 31 |
| primary_ok_if_asked_too | 0.400 | 0.320 to 0.480 | 150 |
| hedge_had_answer | nan | - | 0 |

Expert primary: `{'ask_first': 6, 'dont_water': 18, 'leave_normal': 27, 'move_light': 9, 'other': 29, 'prune': 10, 'shelter': 4, 'treat_or_remove': 37, 'water': 10}`

Our primary: `{'dont_water': 19, 'leave_normal': 39, 'move_light': 13, 'other': 23, 'prune': 11, 'shelter': 1, 'treat_or_remove': 42, 'water': 2}`
