# Advice eval 2026-10-04-super-mirage-always

- Set `actions_mirage`; model `nvidia/nemotron-3-super-120b-a12b` (tokenfactory); prompt hash `462dda0ce414`; git `24c13b7`
- Items 200: 200 scored, 0 missing, 0 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $0.1393

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.445 | 0.375 to 0.515 | 200 |
| primary_in_truth | 0.675 | 0.610 to 0.740 | 200 |
| jaccard | 0.340 | 0.301 to 0.378 | 200 |
| over_treatment | 0.005 | 0.000 to 0.015 | 200 |
| water_conflict | 0.055 | 0.025 to 0.090 | 200 |
| asked_when_expert_asked | 0.306 | 0.194 to 0.417 | 72 |
| primary_ok_if_asked_too | 0.445 | 0.375 to 0.515 | 200 |
| hedge_had_answer | nan | - | 0 |

Expert primary: `{'ask_first': 20, 'dont_water': 5, 'leave_normal': 33, 'move_light': 2, 'other': 44, 'prune': 34, 'shelter': 11, 'treat_or_remove': 25, 'water': 26}`

Our primary: `{'dont_water': 14, 'leave_normal': 72, 'move_light': 8, 'other': 37, 'prune': 36, 'shelter': 11, 'treat_or_remove': 6, 'water': 16}`
