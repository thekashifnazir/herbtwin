# Eval run 2026-10-18-species_gbif-nvidia-nemotron-3-5-super-vl

- Set: `species_gbif`; backend `tokenfactory`, model `nvidia/Nemotron-3.5-Super-VL`; prompt hash `35b1b37a0ad4`; max side 1024; git `9dbe93d`
- Items: 150 total, 150 scored, 0 missing, 0 failed, 0 call errors; 0 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 150}; cost $0.083203; mean latency 1580 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| top1 | 0.627 | 0.547 to 0.707 | 0 |
| top3 | 0.813 | 0.753 to 0.873 | 0 |
| genus_top1 | 0.700 | 0.620 to 0.773 | 0 |

Per species top1: `{'acer palmatum': 1.0, 'allium schoenoprasum': 0.9, 'allium tuberosum': 0.0, 'artemisia dracunculus': 0.0, 'coriandrum sativum': 0.2, 'dryopteris filix-mas': 1.0, 'melissa officinalis': 0.3, 'mentha spicata': 0.8, 'ocimum basilicum': 1.0, 'origanum vulgare': 0.7, 'petroselinum crispum': 0.8, 'polystichum setiferum': 0.0, 'salvia officinalis': 1.0, 'salvia rosmarinus': 1.0, 'thymus vulgaris': 0.7}`

Largest disagreements: species_gbif/2574080210, species_gbif/2634034148, species_gbif/2963848468, species_gbif/3355260351, species_gbif/3355462344
