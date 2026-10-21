# Advice eval b1b-mirage

- Set `actions_mirage`; model `nvidia/nemotron-3-super-120b-a12b` (tokenfactory); prompt hash `114a377a8a65`; git `f0b841c`
- Items 200: 200 scored, 0 missing, 0 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $0.4996

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.410 | 0.340 to 0.475 | 200 |
| primary_in_truth | 0.650 | 0.585 to 0.715 | 200 |
| jaccard | 0.350 | 0.312 to 0.388 | 200 |
| over_treatment | 0.010 | 0.000 to 0.025 | 200 |
| water_conflict | 0.025 | 0.005 to 0.050 | 200 |
| unguarded_water_conflict | 0.000 | 0.000 to 0.000 | 200 |
| asked_when_expert_asked | 0.556 | 0.444 to 0.667 | 72 |
| primary_ok_if_asked_too | 0.410 | 0.340 to 0.475 | 200 |
| hedge_had_answer | nan | - | 0 |

Expert primary: `{'ask_first': 20, 'dont_water': 5, 'leave_normal': 33, 'move_light': 2, 'other': 44, 'prune': 34, 'shelter': 11, 'treat_or_remove': 25, 'water': 26}`

Our primary: `{'dont_water': 8, 'leave_normal': 86, 'move_light': 4, 'other': 42, 'prune': 31, 'shelter': 6, 'treat_or_remove': 4, 'water': 19}`
