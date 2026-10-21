# Eval run 2026-10-13-species_gbif-bk-google_gemma-3-27b-it

- Set: `species_gbif`; backend `tokenfactory`, model `google/gemma-3-27b-it`; prompt hash `44ea8edaea55`; max side 1024; git `9fd2289`
- Items: 150 total, 147 scored, 1 missing, 0 failed, 2 call errors; 0 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 150}; cost $0.018168; mean latency 4968 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| top1 | 0.599 | 0.517 to 0.680 | 0 |
| top3 | 0.782 | 0.714 to 0.850 | 0 |
| genus_top1 | 0.701 | 0.626 to 0.776 | 0 |

Per species top1: `{'acer palmatum': 0.889, 'allium schoenoprasum': 0.9, 'allium tuberosum': 0.0, 'artemisia dracunculus': 0.0, 'coriandrum sativum': 0.6, 'dryopteris filix-mas': 0.8, 'melissa officinalis': 0.7, 'mentha spicata': 0.6, 'ocimum basilicum': 0.889, 'origanum vulgare': 0.6, 'petroselinum crispum': 0.8, 'polystichum setiferum': 0.0, 'salvia officinalis': 0.889, 'salvia rosmarinus': 0.9, 'thymus vulgaris': 0.5}`

Largest disagreements: species_gbif/2574080210, species_gbif/2963848468, species_gbif/3355260351, species_gbif/3355462344, species_gbif/3415379929
