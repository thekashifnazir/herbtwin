# Eval run 2026-10-04-species_gbif-glm-5-3-flash

- Set: `species_gbif`; backend `tokenfactory`, model `zai-org/GLM-5.3-Flash`; prompt hash `23d006a5cd18`; max side 1024; git `756e55e`
- Items: 150 total, 150 scored, 0 missing, 0 failed, 0 call errors; 0 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 150}; cost $0.092844; mean latency 9956 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| top1 | 0.867 | 0.813 to 0.920 | 0 |
| top3 | 0.947 | 0.907 to 0.980 | 0 |
| genus_top1 | 0.893 | 0.840 to 0.940 | 0 |

Per species top1: `{'acer palmatum': 1.0, 'allium schoenoprasum': 0.9, 'allium tuberosum': 1.0, 'artemisia dracunculus': 0.6, 'coriandrum sativum': 1.0, 'dryopteris filix-mas': 0.8, 'melissa officinalis': 0.9, 'mentha spicata': 0.9, 'ocimum basilicum': 1.0, 'origanum vulgare': 1.0, 'petroselinum crispum': 0.8, 'polystichum setiferum': 0.2, 'salvia officinalis': 1.0, 'salvia rosmarinus': 1.0, 'thymus vulgaris': 0.9}`

Largest disagreements: species_gbif/4993771888, species_gbif/5230907367, species_gbif/5238416353, species_gbif/6129823678, species_gbif/6129835524
