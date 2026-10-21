# Eval run 2026-10-21-species-potfit-variant

- Set: `species_gbif`; backend `tokenfactory`, model `zai-org/GLM-5.3-Flash`; prompt hash `0e5f9cb27423`; max side 1024; git `be506639`
- Items: 150 total, 149 scored, 0 missing, 1 failed, 0 call errors; 0 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 150}; cost $0.14425; mean latency 10946 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| top1 | 0.859 | 0.799 to 0.913 | 0 |
| top3 | 0.946 | 0.906 to 0.980 | 0 |
| genus_top1 | 0.893 | 0.846 to 0.940 | 0 |

Per species top1: `{'acer palmatum': 1.0, 'allium schoenoprasum': 0.9, 'allium tuberosum': 1.0, 'artemisia dracunculus': 0.667, 'coriandrum sativum': 1.0, 'dryopteris filix-mas': 0.9, 'melissa officinalis': 0.9, 'mentha spicata': 0.9, 'ocimum basilicum': 0.9, 'origanum vulgare': 1.0, 'petroselinum crispum': 0.8, 'polystichum setiferum': 0.3, 'salvia officinalis': 0.9, 'salvia rosmarinus': 0.9, 'thymus vulgaris': 0.8}`

Largest disagreements: species_gbif/3858578207, species_gbif/4039205391, species_gbif/4606806501, species_gbif/4993771888, species_gbif/5230907367
