# Eval run 2026-10-21-species-potfit-control

- Set: `species_gbif`; backend `tokenfactory`, model `zai-org/GLM-5.3-Flash`; prompt hash `35b1b37a0ad4`; max side 1024; git `0890e89a`
- Items: 150 total, 150 scored, 0 missing, 0 failed, 0 call errors; 0 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 150}; cost $0.136924; mean latency 11479 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| top1 | 0.840 | 0.780 to 0.900 | 0 |
| top3 | 0.927 | 0.887 to 0.967 | 0 |
| genus_top1 | 0.880 | 0.827 to 0.933 | 0 |

Per species top1: `{'acer palmatum': 1.0, 'allium schoenoprasum': 0.9, 'allium tuberosum': 0.9, 'artemisia dracunculus': 0.5, 'coriandrum sativum': 1.0, 'dryopteris filix-mas': 1.0, 'melissa officinalis': 0.9, 'mentha spicata': 0.9, 'ocimum basilicum': 1.0, 'origanum vulgare': 1.0, 'petroselinum crispum': 0.6, 'polystichum setiferum': 0.3, 'salvia officinalis': 0.9, 'salvia rosmarinus': 0.9, 'thymus vulgaris': 0.8}`

Largest disagreements: species_gbif/3858578207, species_gbif/3994136587, species_gbif/4606806501, species_gbif/4993771888, species_gbif/5037219106
