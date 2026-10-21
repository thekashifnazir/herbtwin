# Advice eval nano30b-selfhost-p7ba

- Set `actions_se`; model `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B:vllm-no-think` (ollama); prompt hash `7ba44f01d95b`; git `46602f8`
- Items 150: 148 scored, 0 missing, 2 invalid, 0 call errors

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.311 | 0.236 to 0.385 | 148 |
| primary_in_truth | 0.527 | 0.446 to 0.608 | 148 |
| jaccard | 0.279 | 0.239 to 0.318 | 148 |
| over_treatment | 0.230 | 0.162 to 0.297 | 148 |
| water_conflict | 0.061 | 0.027 to 0.101 | 148 |
| unguarded_water_conflict | 0.000 | 0.000 to 0.000 | 148 |
| asked_when_expert_asked | 1.000 | 1.000 to 1.000 | 31 |
| primary_ok_if_asked_too | 0.311 | 0.236 to 0.385 | 148 |
| hedge_had_answer | nan | - | 0 |

Expert primary: `{'ask_first': 6, 'dont_water': 17, 'leave_normal': 27, 'move_light': 8, 'other': 29, 'prune': 10, 'shelter': 4, 'treat_or_remove': 37, 'water': 10}`

Our primary: `{'dont_water': 3, 'leave_normal': 43, 'move_light': 12, 'other': 9, 'prune': 8, 'shelter': 2, 'treat_or_remove': 53, 'water': 18}`
