# Advice eval 2026-10-04-advice-actions_se-photo-subset-with-photo

- Set `actions_se`; model `qwen3:14b:no-think+photo-qwen2.5vl:7b` (ollama); prompt hash `d9fd7599abe0`; git `21b105e`
- Items 546: 538 scored, 0 missing, 8 invalid, 0 call errors

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.268 | 0.232 to 0.305 | 538 |
| primary_in_truth | 0.457 | 0.416 to 0.500 | 538 |
| jaccard | 0.276 | 0.250 to 0.304 | 538 |
| over_treatment | 0.095 | 0.069 to 0.121 | 538 |
| water_conflict | 0.039 | 0.022 to 0.056 | 538 |
| asked_when_expert_asked | 0.551 | 0.476 to 0.639 | 147 |

Expert primary: `{'ask_first': 49, 'dont_water': 52, 'leave_normal': 100, 'move_light': 24, 'other': 108, 'prune': 31, 'shelter': 12, 'treat_or_remove': 135, 'water': 27}`

Our primary: `{'ask_first': 255, 'dont_water': 12, 'leave_normal': 76, 'move_light': 28, 'other': 18, 'prune': 25, 'shelter': 16, 'treat_or_remove': 81, 'water': 27}`
