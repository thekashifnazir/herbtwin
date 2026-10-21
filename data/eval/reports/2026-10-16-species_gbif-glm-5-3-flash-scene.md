# Eval run 2026-10-16-species_gbif-glm-5-3-flash-scene

- Set: `species_gbif`; backend `tokenfactory`, model `zai-org/GLM-5.3-Flash`; prompt hash `35b1b37a0ad4`; max side 1024; git `f58b253`
- Items: 150 total, 149 scored, 0 missing, 1 failed, 0 call errors; 0 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 150}; cost $0.133504; mean latency 8228 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| top1 | 0.846 | 0.785 to 0.899 | 0 |
| top3 | 0.933 | 0.893 to 0.966 | 0 |
| genus_top1 | 0.879 | 0.826 to 0.926 | 0 |

Per species top1: `{'acer palmatum': 1.0, 'allium schoenoprasum': 0.9, 'allium tuberosum': 0.8, 'artemisia dracunculus': 0.444, 'coriandrum sativum': 1.0, 'dryopteris filix-mas': 1.0, 'melissa officinalis': 0.9, 'mentha spicata': 0.9, 'ocimum basilicum': 0.9, 'origanum vulgare': 1.0, 'petroselinum crispum': 0.6, 'polystichum setiferum': 0.3, 'salvia officinalis': 1.0, 'salvia rosmarinus': 1.0, 'thymus vulgaris': 0.9}`

Largest disagreements: species_gbif/3415379929, species_gbif/3994136587, species_gbif/4993771888, species_gbif/5153657187, species_gbif/5206130708
