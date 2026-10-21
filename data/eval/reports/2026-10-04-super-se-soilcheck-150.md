# Advice eval 2026-10-04-super-se-soilcheck-150

- Set `actions_se`; model `nvidia/nemotron-3-super-120b-a12b` (tokenfactory); prompt hash `a5a39901e134`; git `d3fed36`
- Items 150: 150 scored, 0 missing, 0 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $0.1246

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.413 | 0.333 to 0.493 | 150 |
| primary_in_truth | 0.607 | 0.527 to 0.687 | 150 |
| jaccard | 0.363 | 0.310 to 0.415 | 150 |
| over_treatment | 0.047 | 0.013 to 0.080 | 150 |
| water_conflict | 0.033 | 0.007 to 0.067 | 150 |
| unguarded_water_conflict | 0.013 | 0.000 to 0.033 | 150 |
| asked_when_expert_asked | 0.375 | 0.219 to 0.531 | 32 |
| primary_ok_if_asked_too | 0.413 | 0.333 to 0.493 | 150 |
| hedge_had_answer | nan | - | 0 |

Expert primary: `{'ask_first': 9, 'dont_water': 13, 'leave_normal': 27, 'move_light': 6, 'other': 37, 'prune': 10, 'shelter': 4, 'treat_or_remove': 37, 'water': 7}`

Our primary: `{'dont_water': 17, 'leave_normal': 44, 'move_light': 14, 'other': 22, 'prune': 8, 'shelter': 7, 'treat_or_remove': 30, 'water': 8}`
