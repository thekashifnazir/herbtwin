# Advice eval 2026-10-04-advice-actions_se-photo-subset-text-only

- Set `actions_se`; model `qwen3:14b:no-think` (ollama); prompt hash `d9fd7599abe0`; git `4a74bd1`
- Items 546: 546 scored, 0 missing, 0 invalid, 0 call errors

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.249 | 0.214 to 0.286 | 546 |
| primary_in_truth | 0.430 | 0.392 to 0.474 | 546 |
| jaccard | 0.263 | 0.238 to 0.287 | 546 |
| over_treatment | 0.117 | 0.092 to 0.145 | 546 |
| water_conflict | 0.042 | 0.026 to 0.059 | 546 |
| asked_when_expert_asked | 0.662 | 0.588 to 0.736 | 148 |

Expert primary: `{'ask_first': 50, 'dont_water': 52, 'leave_normal': 103, 'move_light': 25, 'other': 109, 'prune': 31, 'shelter': 12, 'treat_or_remove': 136, 'water': 28}`

Our primary: `{'ask_first': 304, 'dont_water': 10, 'leave_normal': 46, 'move_light': 21, 'other': 15, 'prune': 24, 'shelter': 18, 'treat_or_remove': 87, 'water': 21}`
