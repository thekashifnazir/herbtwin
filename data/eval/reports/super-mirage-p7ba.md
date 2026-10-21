# Advice eval super-mirage-p7ba

- Set `actions_mirage`; model `nvidia/nemotron-3-super-120b-a12b` (tokenfactory); prompt hash `7ba44f01d95b`; git `323fd9a`
- Items 200: 200 scored, 0 missing, 0 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $0.5530

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.435 | 0.365 to 0.505 | 200 |
| primary_in_truth | 0.675 | 0.610 to 0.740 | 200 |
| jaccard | 0.376 | 0.337 to 0.416 | 200 |
| over_treatment | 0.010 | 0.000 to 0.025 | 200 |
| water_conflict | 0.045 | 0.020 to 0.075 | 200 |
| unguarded_water_conflict | 0.005 | 0.000 to 0.015 | 200 |
| asked_when_expert_asked | 0.611 | 0.486 to 0.722 | 72 |
| primary_ok_if_asked_too | 0.435 | 0.365 to 0.505 | 200 |
| hedge_had_answer | nan | - | 0 |

Expert primary: `{'ask_first': 20, 'dont_water': 5, 'leave_normal': 33, 'move_light': 2, 'other': 44, 'prune': 34, 'shelter': 11, 'treat_or_remove': 25, 'water': 26}`

Our primary: `{'dont_water': 13, 'leave_normal': 69, 'move_light': 4, 'other': 45, 'prune': 35, 'shelter': 10, 'treat_or_remove': 4, 'water': 20}`
