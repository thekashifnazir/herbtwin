# Advice eval 2026-10-04-super-se-photo150-glm

- Set `actions_se`; model `nvidia/nemotron-3-super-120b-a12b+photo-zai-org/GLM-5.3-Flash` (tokenfactory); prompt hash `d9fd7599abe0`; git `242be85`
- Items 150: 150 scored, 0 missing, 0 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $0.0862
- Photo reader on tokenfactory; recorded cost $0.1109

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.340 | 0.267 to 0.420 | 150 |
| primary_in_truth | 0.587 | 0.507 to 0.667 | 150 |
| jaccard | 0.289 | 0.243 to 0.337 | 150 |
| over_treatment | 0.060 | 0.027 to 0.100 | 150 |
| water_conflict | 0.053 | 0.020 to 0.093 | 150 |
| asked_when_expert_asked | 0.128 | 0.026 to 0.256 | 39 |
| primary_ok_if_asked_too | 0.340 | 0.267 to 0.420 | 150 |
| hedge_had_answer | 0.037 | 0.000 to 0.111 | 27 |

Expert primary: `{'ask_first': 14, 'dont_water': 14, 'leave_normal': 27, 'move_light': 9, 'other': 27, 'prune': 9, 'shelter': 2, 'treat_or_remove': 39, 'water': 9}`

Our primary: `{'ask_first': 29, 'dont_water': 20, 'leave_normal': 22, 'move_light': 7, 'other': 18, 'prune': 8, 'shelter': 3, 'treat_or_remove': 34, 'water': 9}`
