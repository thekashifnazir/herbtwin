# Eval run 2026-10-04-droop_soybean-glm-5-3-flash

- Set: `droop_soybean`; backend `tokenfactory`, model `zai-org/GLM-5.3-Flash`; prompt hash `23d006a5cd18`; max side 1024; git `756e55e`
- Items: 180 total, 180 scored, 0 missing, 0 failed, 0 call errors; 0 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 180}; cost $0.106782; mean latency 8722 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| qwk | 0.285 | 0.000 to 0.373 | 0 |
| exact | 0.211 | 0.117 to 0.399 | 0 |
| within_one | 0.667 | 0.527 to 0.891 | 0 |
| mae | 1.156 | 0.743 to 1.382 | 0 |

Truth histogram: `{0: 30, 1: 60, 2: 60, 3: 30}`

Pred histogram: `{0: 141, 1: 16, 2: 23}`

Largest disagreements: droop_soybean/11-46_18_09_2019_17_37_14, droop_soybean/11-46_19_09_2019_15_34_03, droop_soybean/11-46_20_09_2019_10_06_06, droop_soybean/11-46_20_09_2019_10_36_08, droop_soybean/11-46_20_09_2019_17_51_24
