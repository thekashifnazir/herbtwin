# Advice eval 2026-10-04-advice-actions_se-qwen3-14b-no-think

- Set `actions_se`; model `qwen3:14b:no-think` (ollama); prompt hash `d9fd7599abe0`; git `559112f`
- Items 774: 774 scored, 0 missing, 0 invalid, 0 call errors

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.283 | 0.251 to 0.315 | 774 |
| primary_in_truth | 0.465 | 0.429 to 0.501 | 774 |
| jaccard | 0.294 | 0.271 to 0.318 | 774 |
| over_treatment | 0.114 | 0.092 to 0.137 | 774 |
| water_conflict | 0.043 | 0.028 to 0.058 | 774 |
| asked_when_expert_asked | 0.619 | 0.545 to 0.693 | 176 |

Expert primary: `{'ask_first': 59, 'dont_water': 66, 'leave_normal': 150, 'move_light': 43, 'other': 183, 'prune': 62, 'shelter': 14, 'treat_or_remove': 160, 'water': 37}`

Our primary: `{'ask_first': 356, 'dont_water': 14, 'leave_normal': 81, 'move_light': 40, 'other': 64, 'prune': 46, 'shelter': 34, 'treat_or_remove': 106, 'water': 33}`
