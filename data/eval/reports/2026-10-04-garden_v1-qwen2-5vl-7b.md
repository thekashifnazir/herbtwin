# Eval run 2026-10-04-garden_v1-qwen2-5vl-7b

- Set: `garden_v1`; backend `ollama`, model `qwen2.5vl:7b`; prompt hash `23d006a5cd18`; max side 1024; git `e558326`
- Items: 183 total, 183 scored, 0 missing, 0 failed, 0 call errors; 1 answered "not a plant" (scored as given)
- Licence tags: {'owner': 183}; cost $0; mean latency 11633 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| qwk | 0.282 | -0.040 to 0.538 | 0 |
| exact | 0.536 | 0.319 to 0.748 | 0 |
| within_one | 0.918 | 0.815 to 0.983 | 0 |
| mae | 0.546 | 0.282 to 0.833 | 0 |

Truth histogram: `{0: 90, 1: 67, 2: 24, 3: 2}`

Pred histogram: `{0: 145, 1: 35, 2: 1, 3: 2}`

Largest disagreements: garden_v1/c021, garden_v1/c058, garden_v1/c060, garden_v1/c062, garden_v1/c063
