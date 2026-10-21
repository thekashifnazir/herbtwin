# Advice eval 2026-10-04-super-se-always-150

- Set `actions_se`; model `nvidia/nemotron-3-super-120b-a12b` (tokenfactory); prompt hash `462dda0ce414`; git `24c13b7`
- Items 150: 150 scored, 0 missing, 0 invalid, 0 call errors
- Advisor on tokenfactory; recorded cost $0.0999

| Metric | Value | 95% CI | n |
|---|---|---|---|
| primary_match | 0.393 | 0.313 to 0.467 | 150 |
| primary_in_truth | 0.600 | 0.520 to 0.680 | 150 |
| jaccard | 0.341 | 0.294 to 0.388 | 150 |
| over_treatment | 0.033 | 0.007 to 0.067 | 150 |
| water_conflict | 0.053 | 0.020 to 0.093 | 150 |
| asked_when_expert_asked | 0.312 | 0.156 to 0.469 | 32 |
| primary_ok_if_asked_too | 0.393 | 0.313 to 0.467 | 150 |
| hedge_had_answer | nan | - | 0 |

Expert primary: `{'ask_first': 9, 'dont_water': 13, 'leave_normal': 27, 'move_light': 6, 'other': 37, 'prune': 10, 'shelter': 4, 'treat_or_remove': 37, 'water': 7}`

Our primary: `{'dont_water': 24, 'leave_normal': 37, 'move_light': 18, 'other': 15, 'prune': 10, 'shelter': 5, 'treat_or_remove': 28, 'water': 13}`
