# Eval run 2026-10-04-decline_indoor-qwen2-5vl-7b

- Set: `decline_indoor`; backend `ollama`, model `qwen2.5vl:7b`; prompt hash `23d006a5cd18`; max side 1024; git `e558326`
- Items: 120 total, 120 scored, 0 missing, 0 failed, 0 call errors; 67 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 120}; cost $0; mean latency 12142 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| balanced_accuracy | 0.692 | 0.627 to 0.754 | 0 |
| precision | 1.000 | 1.000 to 1.000 | 0 |
| recall | 0.383 | 0.254 to 0.508 | 0 |
| specificity | 1.000 | 1.000 to 1.000 | 0 |

Pred histogram: `{0: 97, 1: 19, 3: 4}`

Largest disagreements: decline_indoor/Snake_Plant_Leaf_Withering/Snake_Plant_Leaf_Withering_007, decline_indoor/Snake_Plant_Leaf_Withering/Snake_Plant_Leaf_Withering_010, decline_indoor/Snake_Plant_Leaf_Withering/Snake_Plant_Leaf_Withering_013, decline_indoor/Snake_Plant_Leaf_Withering/Snake_Plant_Leaf_Withering_015, decline_indoor/Snake_Plant_Leaf_Withering/Snake_Plant_Leaf_Withering_017
