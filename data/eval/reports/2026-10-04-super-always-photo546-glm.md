# Advice eval 2026-10-04-super-always-photo546-glm

- Set `actions_se`; model `nvidia/nemotron-3-super-120b-a12b+photo-zai-org/GLM-5.3-Flash` (tokenfactory); prompt hash `462dda0ce414`; git `e06ef8a`
- Items 546: 543 scored, 0 missing, 3 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $0.4001
- Photo reader on tokenfactory; recorded cost $0.4031

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.363 | 0.320 to 0.403 | 543 |
| primary_in_truth | 0.565 | 0.523 to 0.606 | 543 |
| jaccard | 0.339 | 0.315 to 0.365 | 543 |
| over_treatment | 0.059 | 0.041 to 0.079 | 543 |
| water_conflict | 0.050 | 0.031 to 0.068 | 543 |
| asked_when_expert_asked | 0.381 | 0.306 to 0.456 | 147 |
| primary_ok_if_asked_too | 0.363 | 0.320 to 0.403 | 543 |
| hedge_had_answer | nan | - | 0 |

Expert primary: `{'ask_first': 50, 'dont_water': 52, 'leave_normal': 101, 'move_light': 25, 'other': 108, 'prune': 31, 'shelter': 12, 'treat_or_remove': 136, 'water': 28}`

Our primary: `{'dont_water': 77, 'leave_normal': 168, 'move_light': 45, 'other': 50, 'prune': 42, 'shelter': 10, 'treat_or_remove': 107, 'water': 44}`
