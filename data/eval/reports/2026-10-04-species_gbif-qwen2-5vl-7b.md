# Eval run 2026-10-04-species_gbif-qwen2-5vl-7b

- Set: `species_gbif`; backend `ollama`, model `qwen2.5vl:7b`; prompt hash `23d006a5cd18`; max side 1024; git `265cefb`
- Items: 150 total, 148 scored, 0 missing, 2 failed, 0 call errors; 35 answered "not a plant" (scored as given)
- Licence tags: {'safe-to-train': 150}; cost $0; mean latency 11323 ms

| Metric | Value | 95% CI | Skipped draws |
|---|---|---|---|
| top1 | 0.473 | 0.392 to 0.554 | 0 |
| top3 | 0.601 | 0.520 to 0.682 | 0 |
| genus_top1 | 0.547 | 0.466 to 0.628 | 0 |

Per species top1: `{'acer palmatum': 0.1, 'allium schoenoprasum': 0.625, 'allium tuberosum': 0.1, 'artemisia dracunculus': 0.2, 'coriandrum sativum': 0.8, 'dryopteris filix-mas': 0.0, 'melissa officinalis': 1.0, 'mentha spicata': 0.1, 'ocimum basilicum': 0.8, 'origanum vulgare': 0.2, 'petroselinum crispum': 0.8, 'polystichum setiferum': 0.0, 'salvia officinalis': 0.8, 'salvia rosmarinus': 1.0, 'thymus vulgaris': 0.6}`

Largest disagreements: species_gbif/2574080210, species_gbif/2963848468, species_gbif/3355260351, species_gbif/3415379929, species_gbif/3712403315
