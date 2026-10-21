# Eval run 2026-10-12-species_gbif-nemotron-omni

- Set: `species_gbif`; backend `tokenfactory`, model `dedicated/nvidia/Nemotron-3-Nano-Omni-2j6OgDCI6TwX`; prompt hash `44ea8edaea55`; max side 1024; git `82c063e`
- Items: 150 total, 150 scored, 0 missing, 0 failed, 0 call errors; 1 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 150}; cost $0; mean latency 1897 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| top1 | 0.587 | 0.507 to 0.667 | 0 |
| top3 | 0.680 | 0.607 to 0.753 | 0 |
| genus_top1 | 0.680 | 0.607 to 0.753 | 0 |

Per species top1: `{'acer palmatum': 0.9, 'allium schoenoprasum': 0.9, 'allium tuberosum': 0.0, 'artemisia dracunculus': 0.2, 'coriandrum sativum': 1.0, 'dryopteris filix-mas': 0.2, 'melissa officinalis': 0.0, 'mentha spicata': 1.0, 'ocimum basilicum': 0.9, 'origanum vulgare': 0.2, 'petroselinum crispum': 0.8, 'polystichum setiferum': 0.1, 'salvia officinalis': 0.7, 'salvia rosmarinus': 1.0, 'thymus vulgaris': 0.9}`

Largest disagreements: species_gbif/2963848468, species_gbif/3355260351, species_gbif/3415379929, species_gbif/3912032612, species_gbif/3994136587
