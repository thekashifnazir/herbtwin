# Eval run 2026-10-18-species_gbif-deepseek-ai-deepseek-v4-1-flash

- Set: `species_gbif`; backend `tokenfactory`, model `deepseek-ai/DeepSeek-V4.1-Flash`; prompt hash `35b1b37a0ad4`; max side 1024; git `9dbe93d`
- Items: 150 total, 147 scored, 0 missing, 0 failed, 3 call errors; 0 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 150}; cost $0.419058; mean latency 17228 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| top1 | 0.776 | 0.701 to 0.837 | 0 |
| top3 | 0.857 | 0.796 to 0.912 | 0 |
| genus_top1 | 0.803 | 0.735 to 0.864 | 0 |

Per species top1: `{'acer palmatum': 0.9, 'allium schoenoprasum': 0.889, 'allium tuberosum': 1.0, 'artemisia dracunculus': 0.444, 'coriandrum sativum': 0.9, 'dryopteris filix-mas': 0.8, 'melissa officinalis': 0.8, 'mentha spicata': 0.8, 'ocimum basilicum': 0.9, 'origanum vulgare': 0.7, 'petroselinum crispum': 0.8, 'polystichum setiferum': 0.0, 'salvia officinalis': 0.9, 'salvia rosmarinus': 0.889, 'thymus vulgaris': 0.9}`

Largest disagreements: species_gbif/4039205391, species_gbif/4606806501, species_gbif/4987473314, species_gbif/5153657187, species_gbif/5230907367
