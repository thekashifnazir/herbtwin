# Advice eval nano30b-se-150

- Set `actions_se`; model `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` (tokenfactory); prompt hash `7ba44f01d95b`; git `323fd9a`
- Items 150: 150 scored, 0 missing, 0 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $0.1886

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.420 | 0.340 to 0.500 | 150 |
| primary_in_truth | 0.660 | 0.587 to 0.733 | 150 |
| jaccard | 0.324 | 0.279 to 0.367 | 150 |
| over_treatment | 0.073 | 0.033 to 0.113 | 150 |
| water_conflict | 0.020 | 0.000 to 0.047 | 150 |
| unguarded_water_conflict | 0.007 | 0.000 to 0.020 | 150 |
| asked_when_expert_asked | 0.710 | 0.548 to 0.871 | 31 |
| primary_ok_if_asked_too | 0.420 | 0.340 to 0.500 | 150 |
| hedge_had_answer | nan | - | 0 |

Expert primary: `{'ask_first': 6, 'dont_water': 18, 'leave_normal': 27, 'move_light': 9, 'other': 29, 'prune': 10, 'shelter': 4, 'treat_or_remove': 37, 'water': 10}`

Our primary: `{'dont_water': 18, 'leave_normal': 33, 'move_light': 11, 'other': 19, 'prune': 13, 'shelter': 7, 'treat_or_remove': 41, 'water': 8}`
