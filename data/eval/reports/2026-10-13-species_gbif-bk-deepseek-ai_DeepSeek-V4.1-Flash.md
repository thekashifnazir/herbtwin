# Eval run 2026-10-13-species_gbif-bk-deepseek-ai_DeepSeek-V4.1-Flash

- Set: `species_gbif`; backend `tokenfactory`, model `deepseek-ai/DeepSeek-V4.1-Flash`; prompt hash `44ea8edaea55`; max side 1024; git `323fd9a`
- Items: 150 total, 144 scored, 1 missing, 0 failed, 5 call errors; 0 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 150}; cost $0.435281; mean latency 14095 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| top1 | 0.799 | 0.729 to 0.861 | 0 |
| top3 | 0.889 | 0.840 to 0.938 | 0 |
| genus_top1 | 0.833 | 0.771 to 0.889 | 0 |

Per species top1: `{'acer palmatum': 0.9, 'allium schoenoprasum': 0.9, 'allium tuberosum': 1.0, 'artemisia dracunculus': 0.5, 'coriandrum sativum': 0.8, 'dryopteris filix-mas': 1.0, 'melissa officinalis': 0.889, 'mentha spicata': 0.7, 'ocimum basilicum': 0.875, 'origanum vulgare': 1.0, 'petroselinum crispum': 0.889, 'polystichum setiferum': 0.0, 'salvia officinalis': 0.8, 'salvia rosmarinus': 1.0, 'thymus vulgaris': 0.8}`

Largest disagreements: species_gbif/3343875406, species_gbif/4039205391, species_gbif/4606806501, species_gbif/4852525714, species_gbif/4987473314
