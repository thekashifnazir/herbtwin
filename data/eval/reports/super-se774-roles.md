# Advice eval super-se774-roles

- Set `actions_se`; model `nvidia/nemotron-3-super-120b-a12b` (tokenfactory); prompt hash `ba9e03c80e31`; git `dc1fb457`
- Items 774: 774 scored, 0 missing, 0 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $2.2215

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.408 | 0.373 to 0.443 | 774 |
| primary_in_truth | 0.574 | 0.539 to 0.609 | 774 |
| jaccard | 0.353 | 0.331 to 0.376 | 774 |
| over_treatment | 0.049 | 0.035 to 0.065 | 774 |
| water_conflict | 0.040 | 0.026 to 0.054 | 774 |
| unguarded_water_conflict | 0.010 | 0.004 to 0.018 | 774 |
| asked_when_expert_asked | 0.648 | 0.574 to 0.716 | 176 |
| primary_ok_if_asked_too | 0.408 | 0.373 to 0.443 | 774 |
| hedge_had_answer | nan | - | 0 |

Expert primary: `{'ask_first': 59, 'dont_water': 66, 'leave_normal': 150, 'move_light': 43, 'other': 183, 'prune': 62, 'shelter': 14, 'treat_or_remove': 160, 'water': 37}`

Our primary: `{'dont_water': 88, 'leave_normal': 243, 'move_light': 48, 'other': 159, 'prune': 67, 'shelter': 8, 'treat_or_remove': 114, 'water': 47}`
