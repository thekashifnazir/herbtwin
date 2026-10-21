# Advice eval 2026-10-04-advice-actions_mirage-qwen3-14b-no-think

- Set `actions_mirage`; model `qwen3:14b:no-think` (ollama); prompt hash `d9fd7599abe0`; git `559112f`
- Items 200: 200 scored, 0 missing, 0 invalid, 0 call errors

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.350 | 0.285 to 0.415 | 200 |
| primary_in_truth | 0.575 | 0.505 to 0.645 | 200 |
| jaccard | 0.302 | 0.267 to 0.336 | 200 |
| over_treatment | 0.055 | 0.025 to 0.090 | 200 |
| water_conflict | 0.010 | 0.000 to 0.025 | 200 |
| asked_when_expert_asked | 0.514 | 0.403 to 0.625 | 72 |

Expert primary: `{'ask_first': 20, 'dont_water': 5, 'leave_normal': 33, 'move_light': 2, 'other': 44, 'prune': 34, 'shelter': 11, 'treat_or_remove': 25, 'water': 26}`

Our primary: `{'ask_first': 82, 'dont_water': 1, 'leave_normal': 8, 'move_light': 5, 'other': 36, 'prune': 21, 'shelter': 30, 'treat_or_remove': 12, 'water': 5}`
