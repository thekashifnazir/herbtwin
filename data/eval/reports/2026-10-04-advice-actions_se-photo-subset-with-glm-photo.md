# Advice eval 2026-10-04-advice-actions_se-photo-subset-with-glm-photo

- Set `actions_se`; model `qwen3:14b:no-think+photo-zai-org/GLM-5.3-Flash` (ollama); prompt hash `d9fd7599abe0`; git `1664c80`
- Items 546: 546 scored, 0 missing, 0 invalid, 0 call errors
- Photo reader on tokenfactory; recorded cost $0.4005

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.278 | 0.242 to 0.317 | 546 |
| primary_in_truth | 0.462 | 0.421 to 0.505 | 546 |
| jaccard | 0.288 | 0.263 to 0.314 | 546 |
| over_treatment | 0.178 | 0.147 to 0.211 | 546 |
| water_conflict | 0.051 | 0.033 to 0.070 | 546 |
| asked_when_expert_asked | 0.480 | 0.399 to 0.561 | 148 |

Expert primary: `{'ask_first': 50, 'dont_water': 52, 'leave_normal': 103, 'move_light': 25, 'other': 109, 'prune': 31, 'shelter': 12, 'treat_or_remove': 136, 'water': 28}`

Our primary: `{'ask_first': 220, 'dont_water': 17, 'leave_normal': 66, 'move_light': 29, 'other': 15, 'prune': 23, 'shelter': 17, 'treat_or_remove': 122, 'water': 37}`
