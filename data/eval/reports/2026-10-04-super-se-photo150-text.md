# Advice eval 2026-10-04-super-se-photo150-text

- Set `actions_se`; model `nvidia/nemotron-3-super-120b-a12b` (tokenfactory); prompt hash `d9fd7599abe0`; git `ab5df72`
- Items 150: 150 scored, 0 missing, 0 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $0.0848

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.260 | 0.193 to 0.333 | 150 |
| primary_in_truth | 0.493 | 0.420 to 0.573 | 150 |
| jaccard | 0.257 | 0.211 to 0.307 | 150 |
| over_treatment | 0.020 | 0.000 to 0.047 | 150 |
| water_conflict | 0.047 | 0.020 to 0.087 | 150 |
| asked_when_expert_asked | 0.462 | 0.308 to 0.615 | 39 |
| primary_ok_if_asked_too | 0.260 | 0.193 to 0.333 | 150 |
| hedge_had_answer | 0.000 | 0.000 to 0.000 | 57 |

Expert primary: `{'ask_first': 14, 'dont_water': 14, 'leave_normal': 27, 'move_light': 9, 'other': 27, 'prune': 9, 'shelter': 2, 'treat_or_remove': 39, 'water': 9}`

Our primary: `{'ask_first': 65, 'dont_water': 16, 'leave_normal': 17, 'move_light': 12, 'other': 8, 'prune': 7, 'shelter': 3, 'treat_or_remove': 17, 'water': 5}`
