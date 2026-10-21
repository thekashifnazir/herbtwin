# Advice eval super-se-150-p7ba

- Set `actions_se`; model `nvidia/nemotron-3-super-120b-a12b` (tokenfactory); prompt hash `7ba44f01d95b`; git `323fd9a`
- Items 150: 150 scored, 0 missing, 0 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $0.4135

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.440 | 0.360 to 0.520 | 150 |
| primary_in_truth | 0.687 | 0.607 to 0.760 | 150 |
| jaccard | 0.366 | 0.317 to 0.415 | 150 |
| over_treatment | 0.020 | 0.000 to 0.047 | 150 |
| water_conflict | 0.027 | 0.007 to 0.053 | 150 |
| unguarded_water_conflict | 0.000 | 0.000 to 0.000 | 150 |
| asked_when_expert_asked | 0.613 | 0.452 to 0.774 | 31 |
| primary_ok_if_asked_too | 0.440 | 0.360 to 0.520 | 150 |
| hedge_had_answer | nan | - | 0 |

Expert primary: `{'ask_first': 6, 'dont_water': 18, 'leave_normal': 27, 'move_light': 9, 'other': 29, 'prune': 10, 'shelter': 4, 'treat_or_remove': 37, 'water': 10}`

Our primary: `{'dont_water': 14, 'leave_normal': 44, 'move_light': 11, 'other': 29, 'prune': 15, 'shelter': 4, 'treat_or_remove': 26, 'water': 7}`
