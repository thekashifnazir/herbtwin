# Advice eval nano4b-base-vllm-mirage

- Set `actions_mirage`; model `nano4b-base:think` (ollama); prompt hash `7ba44f01d95b`; git `e74d519`
- Items 200: 199 scored, 0 missing, 1 invalid, 0 call errors

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.337 | 0.271 to 0.402 | 199 |
| primary_in_truth | 0.538 | 0.467 to 0.603 | 199 |
| jaccard | 0.282 | 0.250 to 0.315 | 199 |
| over_treatment | 0.176 | 0.126 to 0.226 | 199 |
| water_conflict | 0.005 | 0.000 to 0.015 | 199 |
| unguarded_water_conflict | 0.000 | 0.000 to 0.000 | 199 |
| asked_when_expert_asked | 1.000 | 1.000 to 1.000 | 72 |
| primary_ok_if_asked_too | 0.337 | 0.271 to 0.402 | 199 |
| hedge_had_answer | nan | - | 0 |

Expert primary: `{'ask_first': 20, 'dont_water': 5, 'leave_normal': 33, 'move_light': 2, 'other': 43, 'prune': 34, 'shelter': 11, 'treat_or_remove': 25, 'water': 26}`

Our primary: `{'leave_normal': 82, 'move_light': 5, 'other': 18, 'prune': 33, 'shelter': 4, 'treat_or_remove': 49, 'water': 8}`
