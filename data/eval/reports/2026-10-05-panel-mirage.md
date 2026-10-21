# Advice eval 2026-10-05-panel-mirage

- Set `actions_mirage`; model `nvidia/nemotron-3-super-120b-a12b` (tokenfactory); prompt hash `ee8da6c2c947`; git `bde5544`
- Items 200: 200 scored, 0 missing, 0 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $0.5337

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.450 | 0.380 to 0.515 | 200 |
| primary_in_truth | 0.665 | 0.600 to 0.730 | 200 |
| jaccard | 0.346 | 0.308 to 0.385 | 200 |
| over_treatment | 0.005 | 0.000 to 0.015 | 200 |
| water_conflict | 0.020 | 0.005 to 0.040 | 200 |
| unguarded_water_conflict | 0.000 | 0.000 to 0.000 | 200 |
| asked_when_expert_asked | 0.514 | 0.403 to 0.625 | 72 |
| primary_ok_if_asked_too | 0.450 | 0.380 to 0.515 | 200 |
| hedge_had_answer | nan | - | 0 |

Expert primary: `{'ask_first': 20, 'dont_water': 5, 'leave_normal': 33, 'move_light': 2, 'other': 44, 'prune': 34, 'shelter': 11, 'treat_or_remove': 25, 'water': 26}`

Our primary: `{'dont_water': 11, 'leave_normal': 90, 'move_light': 4, 'other': 37, 'prune': 34, 'shelter': 10, 'treat_or_remove': 2, 'water': 12}`
