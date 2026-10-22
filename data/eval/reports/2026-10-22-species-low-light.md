# Eval run 2026-10-22-species-low-light

- Set: `species_gbif`; backend `tokenfactory`, model `zai-org/GLM-5.3-Flash`; prompt hash `d9d11b7db0c7`; max side 1024; git `e6cef4e4`
- Items: 150 total, 149 scored, 0 missing, 0 failed, 1 call errors; 0 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 150}; cost $0.134699; mean latency 12908 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| top1 | 0.826 | 0.758 to 0.886 | 0 |
| top3 | 0.919 | 0.872 to 0.960 | 0 |
| genus_top1 | 0.879 | 0.819 to 0.926 | 0 |

Per species top1: `{'acer palmatum': 1.0, 'allium schoenoprasum': 0.9, 'allium tuberosum': 0.9, 'artemisia dracunculus': 0.4, 'coriandrum sativum': 1.0, 'dryopteris filix-mas': 0.9, 'melissa officinalis': 0.9, 'mentha spicata': 0.9, 'ocimum basilicum': 1.0, 'origanum vulgare': 1.0, 'petroselinum crispum': 0.889, 'polystichum setiferum': 0.3, 'salvia officinalis': 0.8, 'salvia rosmarinus': 0.9, 'thymus vulgaris': 0.6}`

Largest disagreements: species_gbif/3858578207, species_gbif/3994136587, species_gbif/4080655364, species_gbif/4606806501, species_gbif/4852525714
