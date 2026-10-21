# Eval run 2026-10-04-droop_soybean-qwen2-5vl-7b

- Set: `droop_soybean`; backend `ollama`, model `qwen2.5vl:7b`; prompt hash `23d006a5cd18`; max side 1024; git `e558326`
- Items: 180 total, 180 scored, 0 missing, 0 failed, 0 call errors; 13 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 180}; cost $0; mean latency 13442 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| qwk | 0.000 | -0.000 to 0.000 | 0 |
| exact | 0.167 | 0.058 to 0.376 | 0 |
| within_one | 0.500 | 0.281 to 0.876 | 0 |
| mae | 1.500 | 0.770 to 1.959 | 0 |

**Warning:** the model gave every scored item the same score (0); agreement metrics measure nothing here beyond the label mix.

Truth histogram: `{0: 30, 1: 60, 2: 60, 3: 30}`

Pred histogram: `{0: 180}`

Largest disagreements: droop_soybean/11-46_18_09_2019_15_07_09, droop_soybean/11-46_18_09_2019_15_52_11, droop_soybean/11-46_18_09_2019_16_07_11, droop_soybean/11-46_18_09_2019_16_52_13, droop_soybean/11-46_18_09_2019_17_37_14
