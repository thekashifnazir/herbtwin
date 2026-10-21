# Advice eval 2026-10-04-super-mirage-fewshot

- Set `actions_mirage`; model `nvidia/nemotron-3-super-120b-a12b+fewshot6` (tokenfactory); prompt hash `2ee6b7e37470`; git `242be85`
- Items 200: 200 scored, 0 missing, 0 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $0.1895

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.395 | 0.325 to 0.465 | 200 |
| primary_in_truth | 0.620 | 0.550 to 0.685 | 200 |
| jaccard | 0.299 | 0.262 to 0.338 | 200 |
| over_treatment | 0.010 | 0.000 to 0.025 | 200 |
| water_conflict | 0.040 | 0.015 to 0.070 | 200 |
| asked_when_expert_asked | 0.347 | 0.236 to 0.458 | 72 |
| primary_ok_if_asked_too | 0.395 | 0.325 to 0.465 | 200 |
| hedge_had_answer | 0.000 | 0.000 to 0.000 | 57 |

Expert primary: `{'ask_first': 20, 'dont_water': 5, 'leave_normal': 33, 'move_light': 2, 'other': 44, 'prune': 34, 'shelter': 11, 'treat_or_remove': 25, 'water': 26}`

Our primary: `{'ask_first': 66, 'dont_water': 7, 'leave_normal': 25, 'move_light': 4, 'other': 40, 'prune': 30, 'shelter': 10, 'treat_or_remove': 6, 'water': 12}`
