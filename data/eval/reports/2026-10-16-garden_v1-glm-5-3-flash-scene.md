# Eval run 2026-10-16-garden_v1-glm-5-3-flash-scene

- Set: `garden_v1`; backend `tokenfactory`, model `zai-org/GLM-5.3-Flash`; prompt hash `35b1b37a0ad4`; max side 1024; git `f58b253`
- Items: 183 total, 183 scored, 0 missing, 0 failed, 0 call errors; 0 answered "not a plant" (scored as given)
- Licence tags: {'owner': 183}; cost $0.166037; mean latency 10141 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| qwk | 0.418 | 0.147 to 0.589 | 0 |
| exact | 0.459 | 0.322 to 0.582 | 0 |
| within_one | 0.907 | 0.833 to 0.959 | 0 |
| mae | 0.634 | 0.474 to 0.825 | 0 |

Truth histogram: `{0: 90, 1: 67, 2: 24, 3: 2}`

Pred histogram: `{0: 39, 1: 75, 2: 67, 3: 2}`

Largest disagreements: garden_v1/c004, garden_v1/c009, garden_v1/c010, garden_v1/c011, garden_v1/c012
