# Eval run 2026-10-15-species_gbif-cosmos-reason1-7b

- Set: `species_gbif`; backend `ollama`, model `nvidia/Cosmos-Reason1-7B`; prompt hash `44ea8edaea55`; max side 1024; git `23389bd`
- Items: 150 total, 150 scored, 0 missing, 0 failed, 0 call errors; 0 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 150}; cost $0; mean latency 1200 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| top1 | 0.540 | 0.460 to 0.620 | 0 |
| top3 | 0.653 | 0.580 to 0.727 | 0 |
| genus_top1 | 0.607 | 0.527 to 0.680 | 0 |

Per species top1: `{'acer palmatum': 0.8, 'allium schoenoprasum': 0.9, 'allium tuberosum': 0.4, 'artemisia dracunculus': 0.0, 'coriandrum sativum': 0.8, 'dryopteris filix-mas': 0.2, 'melissa officinalis': 0.9, 'mentha spicata': 0.0, 'ocimum basilicum': 0.8, 'origanum vulgare': 0.4, 'petroselinum crispum': 0.8, 'polystichum setiferum': 0.0, 'salvia officinalis': 0.7, 'salvia rosmarinus': 1.0, 'thymus vulgaris': 0.4}`

Largest disagreements: species_gbif/2574080210, species_gbif/2963848468, species_gbif/3415379929, species_gbif/3912032612, species_gbif/3994136587
