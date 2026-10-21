# Eval run 2026-10-15-species_gbif-cosmos-reason2-32b

- Set: `species_gbif`; backend `ollama`, model `nvidia/Cosmos-Reason2-32B`; prompt hash `44ea8edaea55`; max side 1024; git `23389bd`
- Items: 150 total, 148 scored, 0 missing, 2 failed, 0 call errors; 0 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 150}; cost $0; mean latency 3136 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| top1 | 0.574 | 0.493 to 0.655 | 0 |
| top3 | 0.628 | 0.547 to 0.709 | 0 |
| genus_top1 | 0.743 | 0.669 to 0.811 | 0 |

Per species top1: `{'acer palmatum': 0.9, 'allium schoenoprasum': 1.0, 'allium tuberosum': 0.1, 'artemisia dracunculus': 0.5, 'coriandrum sativum': 0.9, 'dryopteris filix-mas': 0.0, 'melissa officinalis': 0.8, 'mentha spicata': 0.3, 'ocimum basilicum': 0.8, 'origanum vulgare': 0.778, 'petroselinum crispum': 0.8, 'polystichum setiferum': 0.0, 'salvia officinalis': 0.7, 'salvia rosmarinus': 1.0, 'thymus vulgaris': 0.0}`

Largest disagreements: species_gbif/2574080210, species_gbif/3355260351, species_gbif/3415379929, species_gbif/3912032612, species_gbif/3994136587
