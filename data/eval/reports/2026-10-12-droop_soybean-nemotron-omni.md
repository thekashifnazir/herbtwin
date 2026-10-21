# Eval run 2026-10-12-droop_soybean-nemotron-omni

- Set: `droop_soybean`; backend `tokenfactory`, model `dedicated/nvidia/Nemotron-3-Nano-Omni-2j6OgDCI6TwX`; prompt hash `44ea8edaea55`; max side 1024; git `82c063e`
- Items: 180 total, 180 scored, 0 missing, 0 failed, 0 call errors; 0 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 180}; cost $0; mean latency 1828 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| qwk | 0.292 | 0.000 to 0.394 | 0 |
| exact | 0.206 | 0.113 to 0.396 | 0 |
| within_one | 0.689 | 0.542 to 0.888 | 0 |
| mae | 1.150 | 0.752 to 1.370 | 0 |

Truth histogram: `{0: 30, 1: 60, 2: 60, 3: 30}`

Pred histogram: `{0: 143, 1: 11, 2: 26}`

Largest disagreements: droop_soybean/11-46_18_09_2019_16_52_13, droop_soybean/11-46_19_09_2019_14_19_00, droop_soybean/11-46_19_09_2019_14_34_01, droop_soybean/11-46_19_09_2019_15_34_03, droop_soybean/11-46_20_09_2019_09_21_05
