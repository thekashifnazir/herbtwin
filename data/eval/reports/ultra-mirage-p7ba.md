# Advice eval ultra-mirage-p7ba

- Set `actions_mirage`; model `nvidia/Nemotron-3-Ultra-550b-a55b` (tokenfactory); prompt hash `7ba44f01d95b`; git `56e9638`
- Items 200: 196 scored, 0 missing, 4 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $0.8619

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.423 | 0.352 to 0.495 | 196 |
| primary_in_truth | 0.699 | 0.633 to 0.760 | 196 |
| jaccard | 0.355 | 0.321 to 0.388 | 196 |
| over_treatment | 0.082 | 0.046 to 0.122 | 196 |
| water_conflict | 0.026 | 0.005 to 0.051 | 196 |
| unguarded_water_conflict | 0.000 | 0.000 to 0.000 | 196 |
| asked_when_expert_asked | 0.847 | 0.764 to 0.931 | 72 |
| primary_ok_if_asked_too | 0.423 | 0.352 to 0.495 | 196 |
| hedge_had_answer | nan | - | 0 |

Expert primary: `{'ask_first': 20, 'dont_water': 5, 'leave_normal': 32, 'move_light': 2, 'other': 42, 'prune': 34, 'shelter': 11, 'treat_or_remove': 25, 'water': 25}`

Our primary: `{'dont_water': 10, 'leave_normal': 68, 'move_light': 4, 'other': 52, 'prune': 27, 'shelter': 8, 'treat_or_remove': 13, 'water': 14}`
