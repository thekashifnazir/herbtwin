# Eval run 2026-10-12-decline_indoor-glm-5-3-flash

- Set: `decline_indoor`; backend `tokenfactory`, model `zai-org/GLM-5.3-Flash`; prompt hash `44ea8edaea55`; max side 1024; git `82c063e`
- Items: 120 total, 120 scored, 0 missing, 0 failed, 0 call errors; 6 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 120}; cost $0.112546; mean latency 10863 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| balanced_accuracy | 0.883 | 0.821 to 0.936 | 0 |
| precision | 0.883 | 0.795 to 0.964 | 0 |
| recall | 0.883 | 0.800 to 0.961 | 0 |
| specificity | 0.883 | 0.796 to 0.964 | 0 |

Pred histogram: `{0: 60, 1: 43, 2: 14, 3: 3}`

Largest disagreements: decline_indoor/Snake_Plant_Healthy/Snake_Plant_Healthy_052, decline_indoor/Snake_Plant_Leaf_Withering/Snake_Plant_Leaf_Withering_017, decline_indoor/Snake_Plant_Leaf_Withering/Snake_Plant_Leaf_Withering_024, decline_indoor/Snake_Plant_Leaf_Withering/Snake_Plant_Leaf_Withering_036, decline_indoor/Snake_Plant_Leaf_Withering/Snake_Plant_Leaf_Withering_061
