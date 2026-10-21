# Eval run 2026-10-12-species_gbif-glm-5-3-flash

- Set: `species_gbif`; backend `tokenfactory`, model `zai-org/GLM-5.3-Flash`; prompt hash `44ea8edaea55`; max side 1024; git `82c063e`
- Items: 150 total, 150 scored, 0 missing, 0 failed, 0 call errors; 0 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 150}; cost $0.134579; mean latency 9384 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| top1 | 0.867 | 0.813 to 0.920 | 0 |
| top3 | 0.947 | 0.907 to 0.980 | 0 |
| genus_top1 | 0.907 | 0.860 to 0.953 | 0 |

Per species top1: `{'acer palmatum': 1.0, 'allium schoenoprasum': 0.9, 'allium tuberosum': 1.0, 'artemisia dracunculus': 0.4, 'coriandrum sativum': 1.0, 'dryopteris filix-mas': 0.9, 'melissa officinalis': 0.9, 'mentha spicata': 1.0, 'ocimum basilicum': 1.0, 'origanum vulgare': 1.0, 'petroselinum crispum': 0.8, 'polystichum setiferum': 0.4, 'salvia officinalis': 1.0, 'salvia rosmarinus': 1.0, 'thymus vulgaris': 0.7}`

Largest disagreements: species_gbif/4606806501, species_gbif/4852525714, species_gbif/4993771888, species_gbif/5206130708, species_gbif/5230907367
