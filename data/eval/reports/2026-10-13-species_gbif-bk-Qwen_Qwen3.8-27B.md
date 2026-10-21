# Eval run 2026-10-13-species_gbif-bk-Qwen_Qwen3.8-27B

- Set: `species_gbif`; backend `tokenfactory`, model `Qwen/Qwen3.8-27B`; prompt hash `44ea8edaea55`; max side 1024; git `9fd2289`
- Items: 150 total, 149 scored, 1 missing, 0 failed, 0 call errors; 0 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 150}; cost $0.9023; mean latency 6039 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| top1 | 0.577 | 0.497 to 0.658 | 0 |
| top3 | 0.664 | 0.584 to 0.738 | 0 |
| genus_top1 | 0.671 | 0.597 to 0.745 | 0 |

Per species top1: `{'acer palmatum': 0.8, 'allium schoenoprasum': 0.9, 'allium tuberosum': 0.2, 'artemisia dracunculus': 0.1, 'coriandrum sativum': 0.4, 'dryopteris filix-mas': 0.6, 'melissa officinalis': 0.9, 'mentha spicata': 0.6, 'ocimum basilicum': 0.667, 'origanum vulgare': 0.0, 'petroselinum crispum': 0.8, 'polystichum setiferum': 0.0, 'salvia officinalis': 0.9, 'salvia rosmarinus': 0.9, 'thymus vulgaris': 0.9}`

Largest disagreements: species_gbif/2574080210, species_gbif/2634034148, species_gbif/2963848468, species_gbif/3343875406, species_gbif/3355462344
