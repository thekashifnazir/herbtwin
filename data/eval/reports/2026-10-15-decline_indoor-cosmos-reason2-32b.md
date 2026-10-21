# Eval run 2026-10-15-decline_indoor-cosmos-reason2-32b

- Set: `decline_indoor`; backend `ollama`, model `nvidia/Cosmos-Reason2-32B`; prompt hash `44ea8edaea55`; max side 1024; git `23389bd`
- Items: 120 total, 120 scored, 0 missing, 0 failed, 0 call errors; 0 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 120}; cost $0; mean latency 3110 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| balanced_accuracy | 0.892 | 0.839 to 0.942 | 0 |
| precision | 1.000 | 1.000 to 1.000 | 0 |
| recall | 0.783 | 0.678 to 0.883 | 0 |
| specificity | 1.000 | 1.000 to 1.000 | 0 |

Pred histogram: `{0: 73, 2: 2, 3: 45}`

Largest disagreements: decline_indoor/Snake_Plant_Leaf_Withering/Snake_Plant_Leaf_Withering_010, decline_indoor/Snake_Plant_Leaf_Withering/Snake_Plant_Leaf_Withering_015, decline_indoor/Snake_Plant_Leaf_Withering/Snake_Plant_Leaf_Withering_025, decline_indoor/Snake_Plant_Leaf_Withering/Snake_Plant_Leaf_Withering_027, decline_indoor/Snake_Plant_Leaf_Withering/Snake_Plant_Leaf_Withering_028
