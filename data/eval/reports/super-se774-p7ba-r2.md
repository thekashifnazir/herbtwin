# Advice eval super-se774-p7ba-r2

- Set `actions_se`; model `nvidia/nemotron-3-super-120b-a12b` (tokenfactory); prompt hash `7ba44f01d95b`; git `dc1fb457`
- Items 774: 774 scored, 0 missing, 0 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $2.1613

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.424 | 0.390 to 0.460 | 774 |
| primary_in_truth | 0.594 | 0.558 to 0.629 | 774 |
| jaccard | 0.359 | 0.336 to 0.381 | 774 |
| over_treatment | 0.044 | 0.030 to 0.061 | 774 |
| water_conflict | 0.028 | 0.017 to 0.040 | 774 |
| unguarded_water_conflict | 0.004 | 0.000 to 0.009 | 774 |
| asked_when_expert_asked | 0.642 | 0.568 to 0.710 | 176 |
| primary_ok_if_asked_too | 0.424 | 0.390 to 0.460 | 774 |
| hedge_had_answer | nan | - | 0 |

Expert primary: `{'ask_first': 59, 'dont_water': 66, 'leave_normal': 150, 'move_light': 43, 'other': 183, 'prune': 62, 'shelter': 14, 'treat_or_remove': 160, 'water': 37}`

Our primary: `{'dont_water': 78, 'leave_normal': 271, 'move_light': 52, 'other': 140, 'prune': 59, 'shelter': 11, 'treat_or_remove': 124, 'water': 39}`
