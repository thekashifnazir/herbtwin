# Advice eval b1-mirage

- Set `actions_mirage`; model `nvidia/nemotron-3-super-120b-a12b` (tokenfactory); prompt hash `eaa055e327b4`; git `0c3c12b`
- Items 200: 200 scored, 0 missing, 0 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $0.5642

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.385 | 0.320 to 0.455 | 200 |
| primary_in_truth | 0.600 | 0.535 to 0.665 | 200 |
| jaccard | 0.326 | 0.288 to 0.362 | 200 |
| over_treatment | 0.015 | 0.000 to 0.035 | 200 |
| water_conflict | 0.030 | 0.010 to 0.055 | 200 |
| unguarded_water_conflict | 0.005 | 0.000 to 0.020 | 200 |
| asked_when_expert_asked | 0.583 | 0.472 to 0.694 | 72 |
| primary_ok_if_asked_too | 0.390 | 0.320 to 0.455 | 200 |
| hedge_had_answer | 0.375 | 0.125 to 0.750 | 8 |

Expert primary: `{'ask_first': 20, 'dont_water': 5, 'leave_normal': 33, 'move_light': 2, 'other': 44, 'prune': 34, 'shelter': 11, 'treat_or_remove': 25, 'water': 26}`

Our primary: `{'ask_first': 8, 'dont_water': 11, 'leave_normal': 77, 'move_light': 4, 'other': 36, 'prune': 36, 'shelter': 8, 'treat_or_remove': 2, 'water': 18}`
