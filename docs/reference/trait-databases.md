# Species facts from structured databases

Where per-species requirements (temperature, rainfall, light, moisture, hardiness,
phenology, growth form) exist as data rather than prose, for the 14 plants in the garden.
Swept 3 Oct 2026 by direct fetch and parsing; "verified" means rows were read. Companion to
`herb-care-packs.md` (prose facts with licences) and `data-catalogue.md` section 7.

## The join

Three sources together cover almost everything and are licence-clean enough to ship:

| Source | What it adds | Our 14 | Licence |
|---|---|---|---|
| **ECOCROP** (FAO, archived; CSV mirror github.com/OpenCLIM/ecocrop, `EcoCrop_DB.csv`, 2,568 crops) | temperature optimum and absolute min and max, rainfall optimum and absolute, pH, light intensity, soil depth, texture, fertility, drainage, killing temperature, photoperiod class, crop-cycle days, life form | 13 with numbers (Dryopteris row is all NA; no Acer palmatum, no Polystichum) | repo code OGL v3; FAO data has no explicit licence (site dead since 2019); cite, do not claim redistribution rights |
| **Ellenberg-type indicator values for Europe** (Tichý et al. 2023, zenodo.org/records/7427088, 8,909 taxa) | light, temperature, moisture, reaction, nutrients, salinity on 1 to 9 or 1 to 12 scales | 13 incl. both ferns (no Acer palmatum) | CC BY 4.0 |
| **Plant Variety Database** (github.com/bripatch/plant-variety-database, `varieties.csv`, 1,972 cultivars) | USDA zone min and max, days to germination and harvest, height, spacing, sun, water, soil, pH, container-friendly, pests and diseases, planting calendar by zone | 13 (all herbs, Acer palmatum ×4; ferns only Athyrium and Nephrolepis) | CC BY 4.0; text fields are LLM-smoothed from NC State and Johnny's, keep `sources.csv` links |

Optional fourth: **PLANTATT** (BRC/CEH 2008, brc.ac.uk, xls) for UK flowering months,
life form, Ellenberg values and climate of UK range; 9 of 14 (UK-relevant taxa only, no
basil, rosemary, tarragon, garlic chives, maple); licence not stated, historically open for
non-commercial use; read `plantatt.pdf` for the meaning of the E1 and E2 flowering fields
before use.

**Join key:** GBIF usageKey via `api.gbif.org/v1/species/match?name=` (verified: Salvia
rosmarinus 10902460, Acer palmatum 3189882, Polystichum setiferum 4044517). Keep the WCVP
or POWO id as secondary. ECOCROP and the indicator values still use *Rosmarinus
officinalis*; normalise synonyms through WCVP before joining.

Example ECOCROP row, basil: temperature optimum 18 to 27 °C, absolute 7 to 36 °C; rainfall
optimum 1000 to 1600 mm a year; cycle 80 to 270 days. Killing temperature is set for
tarragon (−5), mint (−1), parsley, oregano, coriander and lemon balm (0), and NA for sage,
rosemary, thyme and basil. Example indicator values: sage light 8.2, temperature 7.3,
moisture 3.3; thyme light 8, moisture 1.5; spearmint moisture 7.6.

## Everything else checked

| Source | Link | Coverage | Fields | Licence | Access | Status |
|---|---|---|---|---|---|---|
| ECOCROP alternatives | cropmodels/Recocrop (R, GPL-3, `ecocrop.rds`), supersistence/EcoCrop-ScrapeR (full scrape incl. uses), aruldd/ecocrop-db | same data | same | as above | download | verified exist |
| EIVE 1.0 (Dengler et al. 2023) | zenodo.org/records/7534792 | pan-European | continuous indicator values with niche widths | CC BY 4.0 | download | record verified, species not parsed |
| ClimPlant v2 | figshare.com/articles/dataset/12199628 | forest understorey: Dryopteris filix-mas and Origanum vulgare confirmed; herbs absent | realised climatic niche percentiles, monthly | CC0 | download | verified |
| GIFT | gift.uni-goettingen.de, open API | global, 109 trait columns | growth form, height, life form, flower colour, seed mass; no thresholds | R package GPL; data terms not found | API, no key | partly verified |
| TRY | try-db.org | global; frost and drought tolerance sparse | 2,000+ traits | CC BY default but request-gated | request | policy verified |
| BIEN | bien.nceas.ucsb.edu | global | TRY-derived | **CC BY-NC-ND**, unusable | R package | verified |
| LEDA | uol.de/en/landeco/research/leda/data-files | NW European flora | canopy height, SLA, seed mass, lifespan | not stated | download | page verified |
| AusTraits 7.0 | zenodo.org/records/15718081 | Australian flora; ours only as naturalised | | CC BY 4.0 | download | record verified |
| iNaturalist phenology API | api.inaturalist.org/v1/observations/histogram with term_id 12 (flowering), place_id 6857 (UK), interval month_of_year | any taxon; UK counts thin for cultivated herbs (oregano 139, mint 10, sage 0) | monthly flowering counts | per-observation CC, aggregates fine | API | **verified** |
| USA-NPN species API | services.usanpn.org/npn_portal/species/getSpecies.json | 2 of 14 (coriander, basil); US only | phenophases | open | API | verified |
| PEP725 | pep725.eu | trees and field crops, no herbs | BBCH-coded dates | science and education | registration | unverified |
| Nature's Calendar | woodlandtrust.org.uk | trees and wildflowers, none of ours | | request | | unverified |
| Ecological Flora of Britain and Ireland | ecoflora.org.uk | UK flora, flowering months | | | TLS certificate expired | unverified |
| NC State Extension Plant Toolbox | plants.ces.ncsu.edu/plants/<slug>/ | **all 14** | USDA zones, light, soil, height, bloom time, water, maintenance, toxicity | no data licence stated | HTML | verified 200s; use for validation truth, not redistribution |
| RHS AGM lists | rhs.org.uk AGM PDFs | herbs and ornamentals | name, hardiness rating | RHS copyright | PDF | existence verified |
| Johnny's Selected Seeds herb guide and culture chart | johnnyseeds.com growers library | all herbs | days to germination and harvest, annual or perennial by zone | proprietary; already reflected in the Plant Variety Database | HTML, PDF | links verified |
| WCVP (Kew) | sftp.kew.org/pub/data-repositories/WCVP/ (`wcvp.zip`, Darwin Core) | 14 of 14 names | taxonomy, distribution, life form, climate string | CC BY 4.0 | download | listing verified |
| Dr Duke's | agdatacommons.nal.usda.gov/articles/24660351 | herbs | phytochemicals and uses, **no growing data** | CC0 | download | verified |
| Mansfeld's World Database | mansfeld.ipk-gatersleben.de | cultivated plants | nomenclature, distribution, uses; no thresholds, no bulk download | no licence | web | verified |
| World Checklist of Useful Plant Species | Kew | categories only | | | 403, not on Zenodo | unverified |
| EOL TraitBank | opendata.eol.org | | | | DNS fails | likely dead |
| FloraDB sample | hf.co/datasets/Ichlibitiche/floradb-houseplants-care-sample | 100 houseplants, no herbs | lux, watering days, temperature, humidity, toxicity, gbif key | CC BY-NC 4.0 | download | verified |
| BBCH monograph (Meier, JKI) | julius-kuehn.de BBCH epaper PDF | bulb vegetables, leaf vegetables, weeds; **no Lamiaceae or Apiaceae herb, no chives, no maple or fern scale** | growth stage codes | open PDF | download | verified by text extraction |

Thompson and Morgan (403), Suttons, Ball, Sakata, Enza: no structured public data found.
Missouri Botanical Garden Plant Finder: certificate error, unverified. No open per-species
Köppen or Kaggle hardiness set exists; `waldoj/frostline` is zone by US ZIP only. No Xiaomi
Flower Care database dump found on GitHub.

## Not covered by any database

- Numeric frost or killing temperature for sage, rosemary, thyme and basil (ECOCROP NA);
  use the RHS H rating and PFAF figures from `herb-care-packs.md`.
- Indoor lux and humidity bands for herbs.
- Cold hardiness for ferns and Japanese maple beyond USDA zone bands.
- UK flowering months for cultivated Mediterranean herbs (PLANTATT lacks them, iNaturalist
  too sparse).
- Any BBCH growth-stage scale for herbs. If stages are needed, define a 5-stage scale of
  our own and document it.

Scratch copies of the parsed files (ECOCROP CSV, varieties CSV, indicator values, PLANTATT,
ClimPlant, BBCH text) exist only in the session scratchpad and are not in the repo; the
download script in plan 2 fetches them fresh.
