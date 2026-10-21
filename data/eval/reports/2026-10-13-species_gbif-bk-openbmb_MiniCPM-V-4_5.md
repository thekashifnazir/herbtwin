# Eval run 2026-10-13-species_gbif-bk-openbmb_MiniCPM-V-4_5

- Set: `species_gbif`; backend `tokenfactory`, model `openbmb/MiniCPM-V-4_5`; prompt hash `44ea8edaea55`; max side 1024; git `9fd2289`
- Items: 150 total, 149 scored, 1 missing, 0 failed, 0 call errors; 0 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 150}; cost $0.089952; mean latency 2364 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| top1 | 0.396 | 0.322 to 0.477 | 0 |
| top3 | 0.570 | 0.497 to 0.644 | 0 |
| genus_top1 | 0.604 | 0.523 to 0.685 | 0 |

Per species top1: `{'acer palmatum': 0.9, 'allium schoenoprasum': 0.8, 'allium tuberosum': 0.0, 'artemisia dracunculus': 0.2, 'coriandrum sativum': 0.9, 'dryopteris filix-mas': 0.0, 'melissa officinalis': 0.1, 'mentha spicata': 0.6, 'ocimum basilicum': 0.556, 'origanum vulgare': 0.1, 'petroselinum crispum': 0.8, 'polystichum setiferum': 0.0, 'salvia officinalis': 0.2, 'salvia rosmarinus': 0.7, 'thymus vulgaris': 0.1}`

Largest disagreements: species_gbif/2963848468, species_gbif/3355260351, species_gbif/3415379929, species_gbif/3712403315, species_gbif/3858578207
