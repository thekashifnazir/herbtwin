# Advice eval 2026-10-05-panel2-mirage

- Set `actions_mirage`; model `nvidia/nemotron-3-super-120b-a12b` (tokenfactory); prompt hash `a66249c964d2`; git `5426356`
- Items 200: 200 scored, 0 missing, 0 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $0.5338

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.445 | 0.375 to 0.515 | 200 |
| primary_in_truth | 0.630 | 0.565 to 0.695 | 200 |
| jaccard | 0.337 | 0.300 to 0.375 | 200 |
| over_treatment | 0.020 | 0.005 to 0.040 | 200 |
| water_conflict | 0.055 | 0.025 to 0.090 | 200 |
| unguarded_water_conflict | 0.010 | 0.000 to 0.025 | 200 |
| asked_when_expert_asked | 0.542 | 0.431 to 0.653 | 72 |
| primary_ok_if_asked_too | 0.445 | 0.375 to 0.515 | 200 |
| hedge_had_answer | nan | - | 0 |

Expert primary: `{'ask_first': 20, 'dont_water': 5, 'leave_normal': 33, 'move_light': 2, 'other': 44, 'prune': 34, 'shelter': 11, 'treat_or_remove': 25, 'water': 26}`

Our primary: `{'dont_water': 15, 'leave_normal': 74, 'move_light': 6, 'other': 40, 'prune': 32, 'shelter': 11, 'treat_or_remove': 9, 'water': 13}`
