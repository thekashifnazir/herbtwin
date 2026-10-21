# Eval run 2026-10-12-decline_indoor-nemotron-omni

- Set: `decline_indoor`; backend `tokenfactory`, model `dedicated/nvidia/Nemotron-3-Nano-Omni-2j6OgDCI6TwX`; prompt hash `44ea8edaea55`; max side 1024; git `82c063e`
- Items: 120 total, 120 scored, 0 missing, 0 failed, 0 call errors; 1 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 120}; cost $0; mean latency 1627 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| balanced_accuracy | 0.975 | 0.943 to 1.000 | 0 |
| precision | 0.967 | 0.915 to 1.000 | 0 |
| recall | 0.983 | 0.944 to 1.000 | 0 |
| specificity | 0.967 | 0.911 to 1.000 | 0 |

Pred histogram: `{0: 59, 1: 6, 2: 39, 3: 16}`

Largest disagreements: decline_indoor/Snake_Plant_Healthy/Snake_Plant_Healthy_007, decline_indoor/Snake_Plant_Leaf_Withering/Snake_Plant_Leaf_Withering_073, decline_indoor/Spider_Plant_Healthy/Spider_Plant_Healthy_004
