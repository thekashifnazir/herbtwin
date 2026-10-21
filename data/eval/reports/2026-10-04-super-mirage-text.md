# Advice eval 2026-10-04-super-mirage-text

- Set `actions_mirage`; model `nvidia/nemotron-3-super-120b-a12b` (tokenfactory); prompt hash `d9fd7599abe0`; git `242be85`
- Items 200: 200 scored, 0 missing, 0 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $0.1161

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.410 | 0.340 to 0.480 | 200 |
| primary_in_truth | 0.635 | 0.570 to 0.700 | 200 |
| jaccard | 0.308 | 0.268 to 0.350 | 200 |
| over_treatment | 0.015 | 0.000 to 0.035 | 200 |
| water_conflict | 0.030 | 0.010 to 0.055 | 200 |
| asked_when_expert_asked | 0.458 | 0.347 to 0.569 | 72 |
| primary_ok_if_asked_too | 0.410 | 0.340 to 0.480 | 200 |
| hedge_had_answer | 0.000 | 0.000 to 0.000 | 64 |

Expert primary: `{'ask_first': 20, 'dont_water': 5, 'leave_normal': 33, 'move_light': 2, 'other': 44, 'prune': 34, 'shelter': 11, 'treat_or_remove': 25, 'water': 26}`

Our primary: `{'ask_first': 75, 'dont_water': 5, 'leave_normal': 24, 'move_light': 5, 'other': 38, 'prune': 29, 'shelter': 10, 'treat_or_remove': 3, 'water': 11}`
