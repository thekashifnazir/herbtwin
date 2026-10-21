# Eval run 2026-10-04-decline_indoor-glm-5-3-flash

- Set: `decline_indoor`; backend `tokenfactory`, model `zai-org/GLM-5.3-Flash`; prompt hash `23d006a5cd18`; max side 1024; git `756e55e`
- Items: 120 total, 120 scored, 0 missing, 0 failed, 0 call errors; 7 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 120}; cost $0.077286; mean latency 7967 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| balanced_accuracy | 0.833 | 0.765 to 0.900 | 0 |
| precision | 0.823 | 0.724 to 0.919 | 0 |
| recall | 0.850 | 0.754 to 0.935 | 0 |
| specificity | 0.817 | 0.712 to 0.914 | 0 |

Pred histogram: `{0: 58, 1: 36, 2: 22, 3: 4}`

Largest disagreements: decline_indoor/Snake_Plant_Healthy/Snake_Plant_Healthy_052, decline_indoor/Snake_Plant_Healthy/Snake_Plant_Healthy_055, decline_indoor/Snake_Plant_Leaf_Withering/Snake_Plant_Leaf_Withering_023, decline_indoor/Snake_Plant_Leaf_Withering/Snake_Plant_Leaf_Withering_024, decline_indoor/Snake_Plant_Leaf_Withering/Snake_Plant_Leaf_Withering_061
