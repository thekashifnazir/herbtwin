# Advice eval 2026-10-04-super-se-fewshot-150

- Set `actions_se`; model `nvidia/nemotron-3-super-120b-a12b+fewshot6` (tokenfactory); prompt hash `2ee6b7e37470`; git `242be85`
- Items 150: 150 scored, 0 missing, 0 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $0.1381

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.340 | 0.260 to 0.420 | 150 |
| primary_in_truth | 0.527 | 0.447 to 0.600 | 150 |
| jaccard | 0.312 | 0.261 to 0.361 | 150 |
| over_treatment | 0.040 | 0.013 to 0.073 | 150 |
| water_conflict | 0.040 | 0.013 to 0.073 | 150 |
| asked_when_expert_asked | 0.250 | 0.094 to 0.406 | 32 |
| primary_ok_if_asked_too | 0.340 | 0.260 to 0.420 | 150 |
| hedge_had_answer | 0.053 | 0.000 to 0.132 | 38 |

Expert primary: `{'ask_first': 9, 'dont_water': 13, 'leave_normal': 27, 'move_light': 6, 'other': 37, 'prune': 10, 'shelter': 4, 'treat_or_remove': 37, 'water': 7}`

Our primary: `{'ask_first': 42, 'dont_water': 15, 'leave_normal': 13, 'move_light': 16, 'other': 14, 'prune': 7, 'shelter': 5, 'treat_or_remove': 29, 'water': 9}`
