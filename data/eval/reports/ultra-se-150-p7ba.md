# Advice eval ultra-se-150-p7ba

- Set `actions_se`; model `nvidia/Nemotron-3-Ultra-550b-a55b` (tokenfactory); prompt hash `7ba44f01d95b`; git `56e9638`
- Items 150: 150 scored, 0 missing, 0 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $0.5161

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.393 | 0.313 to 0.467 | 150 |
| primary_in_truth | 0.593 | 0.513 to 0.667 | 150 |
| jaccard | 0.306 | 0.265 to 0.348 | 150 |
| over_treatment | 0.127 | 0.080 to 0.180 | 150 |
| water_conflict | 0.047 | 0.020 to 0.087 | 150 |
| unguarded_water_conflict | 0.000 | 0.000 to 0.000 | 150 |
| asked_when_expert_asked | 0.935 | 0.839 to 1.000 | 31 |
| primary_ok_if_asked_too | 0.393 | 0.313 to 0.467 | 150 |
| hedge_had_answer | nan | - | 0 |

Expert primary: `{'ask_first': 6, 'dont_water': 18, 'leave_normal': 27, 'move_light': 9, 'other': 29, 'prune': 10, 'shelter': 4, 'treat_or_remove': 37, 'water': 10}`

Our primary: `{'dont_water': 19, 'leave_normal': 40, 'move_light': 11, 'other': 28, 'prune': 10, 'shelter': 3, 'treat_or_remove': 36, 'water': 3}`
