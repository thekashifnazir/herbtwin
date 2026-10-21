# Advice eval nano4b-base-se-150

- Set `actions_se`; model `nemotron-3-nano:4b-bf16:no-think` (ollama); prompt hash `7ba44f01d95b`; git `323fd9a`
- Items 150: 150 scored, 0 missing, 0 invalid, 0 call errors

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.380 | 0.300 to 0.460 | 150 |
| primary_in_truth | 0.580 | 0.493 to 0.660 | 150 |
| jaccard | 0.281 | 0.240 to 0.321 | 150 |
| over_treatment | 0.193 | 0.133 to 0.260 | 150 |
| water_conflict | 0.033 | 0.007 to 0.067 | 150 |
| unguarded_water_conflict | 0.000 | 0.000 to 0.000 | 150 |
| asked_when_expert_asked | 1.000 | 1.000 to 1.000 | 31 |
| primary_ok_if_asked_too | 0.380 | 0.300 to 0.460 | 150 |
| hedge_had_answer | nan | - | 0 |

Expert primary: `{'ask_first': 6, 'dont_water': 18, 'leave_normal': 27, 'move_light': 9, 'other': 29, 'prune': 10, 'shelter': 4, 'treat_or_remove': 37, 'water': 10}`

Our primary: `{'leave_normal': 34, 'move_light': 5, 'other': 14, 'prune': 17, 'shelter': 2, 'treat_or_remove': 72, 'water': 6}`
