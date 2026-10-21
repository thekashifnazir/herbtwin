# Advice eval 2026-10-04-super-mirage-soilcheck

- Set `actions_mirage`; model `nvidia/nemotron-3-super-120b-a12b` (tokenfactory); prompt hash `a5a39901e134`; git `d3fed36`
- Items 200: 200 scored, 0 missing, 0 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $0.1595

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.445 | 0.375 to 0.515 | 200 |
| primary_in_truth | 0.650 | 0.580 to 0.715 | 200 |
| jaccard | 0.325 | 0.288 to 0.363 | 200 |
| over_treatment | 0.010 | 0.000 to 0.025 | 200 |
| water_conflict | 0.015 | 0.000 to 0.035 | 200 |
| unguarded_water_conflict | 0.000 | 0.000 to 0.000 | 200 |
| asked_when_expert_asked | 0.417 | 0.306 to 0.528 | 72 |
| primary_ok_if_asked_too | 0.445 | 0.375 to 0.515 | 200 |
| hedge_had_answer | nan | - | 0 |

Expert primary: `{'ask_first': 20, 'dont_water': 5, 'leave_normal': 33, 'move_light': 2, 'other': 44, 'prune': 34, 'shelter': 11, 'treat_or_remove': 25, 'water': 26}`

Our primary: `{'dont_water': 8, 'leave_normal': 87, 'move_light': 4, 'other': 36, 'prune': 29, 'shelter': 12, 'treat_or_remove': 5, 'water': 19}`
