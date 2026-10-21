# Eval run 2026-10-17-decline_indoor-glm-5-3-flash-scene

- Set: `decline_indoor`; backend `tokenfactory`, model `zai-org/GLM-5.3-Flash`; prompt hash `35b1b37a0ad4`; max side 1024; git `6143762`
- Items: 120 total, 120 scored, 0 missing, 0 failed, 0 call errors; 1 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 120}; cost $0.104453; mean latency 11963 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| balanced_accuracy | 0.900 | 0.842 to 0.950 | 0 |
| precision | 0.864 | 0.773 to 0.940 | 0 |
| recall | 0.950 | 0.884 to 1.000 | 0 |
| specificity | 0.850 | 0.750 to 0.937 | 0 |

Pred histogram: `{0: 54, 1: 39, 2: 23, 3: 4}`

Largest disagreements: decline_indoor/Snake_Plant_Healthy/Snake_Plant_Healthy_052, decline_indoor/Snake_Plant_Leaf_Withering/Snake_Plant_Leaf_Withering_076, decline_indoor/Snake_Plant_Leaf_Withering/Snake_Plant_Leaf_Withering_083, decline_indoor/Spider_Plant_Healthy/Spider_Plant_Healthy_004, decline_indoor/Spider_Plant_Healthy/Spider_Plant_Healthy_017
