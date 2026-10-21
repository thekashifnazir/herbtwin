# Eval run 2026-10-17-decline_indoor-nemotron-3-5-super-vl

- Set: `decline_indoor`; backend `tokenfactory`, model `nvidia/Nemotron-3.5-Super-VL`; prompt hash `35b1b37a0ad4`; max side 1024; git `6143762`
- Items: 120 total, 120 scored, 0 missing, 0 failed, 0 call errors; 0 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 120}; cost $0.050404; mean latency 1197 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| balanced_accuracy | 0.833 | 0.774 to 0.894 | 0 |
| precision | 1.000 | 1.000 to 1.000 | 0 |
| recall | 0.667 | 0.548 to 0.788 | 0 |
| specificity | 1.000 | 1.000 to 1.000 | 0 |

Pred histogram: `{0: 80, 1: 17, 2: 13, 3: 10}`

Largest disagreements: decline_indoor/Snake_Plant_Leaf_Withering/Snake_Plant_Leaf_Withering_017, decline_indoor/Snake_Plant_Leaf_Withering/Snake_Plant_Leaf_Withering_032, decline_indoor/Snake_Plant_Leaf_Withering/Snake_Plant_Leaf_Withering_083, decline_indoor/Spider_Plant_Leaf_Tip_Necrosis/Spider_Plant_Leaf_Tip_Necrosis_009, decline_indoor/Spider_Plant_Leaf_Tip_Necrosis/Spider_Plant_Leaf_Tip_Necrosis_010
