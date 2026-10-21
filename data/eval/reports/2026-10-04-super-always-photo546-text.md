# Advice eval 2026-10-04-super-always-photo546-text

- Set `actions_se`; model `nvidia/nemotron-3-super-120b-a12b` (tokenfactory); prompt hash `462dda0ce414`; git `3e9b2c4`
- Items 546: 546 scored, 0 missing, 0 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $0.3816

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.372 | 0.330 to 0.412 | 546 |
| primary_in_truth | 0.546 | 0.502 to 0.586 | 546 |
| jaccard | 0.336 | 0.310 to 0.362 | 546 |
| over_treatment | 0.046 | 0.029 to 0.064 | 546 |
| water_conflict | 0.059 | 0.040 to 0.079 | 546 |
| asked_when_expert_asked | 0.419 | 0.345 to 0.500 | 148 |
| primary_ok_if_asked_too | 0.372 | 0.330 to 0.412 | 546 |
| hedge_had_answer | nan | - | 0 |

Expert primary: `{'ask_first': 50, 'dont_water': 52, 'leave_normal': 103, 'move_light': 25, 'other': 109, 'prune': 31, 'shelter': 12, 'treat_or_remove': 136, 'water': 28}`

Our primary: `{'dont_water': 87, 'leave_normal': 185, 'move_light': 41, 'other': 44, 'prune': 36, 'shelter': 12, 'treat_or_remove': 103, 'water': 38}`
