# Eval run 2026-10-04-garden_v1-glm-5-3-flash

- Set: `garden_v1`; backend `tokenfactory`, model `zai-org/GLM-5.3-Flash`; prompt hash `23d006a5cd18`; max side 1024; git `756e55e`
- Items: 183 total, 183 scored, 0 missing, 0 failed, 0 call errors; 0 answered "not a plant" (scored as given)
- Licence tags: {'owner': 183}; cost $0.117099; mean latency 10739 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| qwk | 0.406 | 0.178 to 0.564 | 0 |
| exact | 0.486 | 0.340 to 0.602 | 0 |
| within_one | 0.902 | 0.820 to 0.956 | 0 |
| mae | 0.612 | 0.451 to 0.821 | 0 |

Truth histogram: `{0: 90, 1: 67, 2: 24, 3: 2}`

Pred histogram: `{0: 39, 1: 78, 2: 65, 3: 1}`

Largest disagreements: garden_v1/c001, garden_v1/c004, garden_v1/c005, garden_v1/c008, garden_v1/c009
