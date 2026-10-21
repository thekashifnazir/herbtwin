# Data profile: what we actually hold

Result of the first pull, 3 Oct 2026. The catalogue lists what sources claim; this file
records what was downloaded, counted and inspected. Everything sits under `data/external/`
(18 GB, excluded from git locally; the plan 2 fetch script will add the proper
`.gitignore` entry and reproduce it from manifests). Nothing here is committed.

## What is on disk

| Source | Holding | Licence as found | Where | Problems hit |
|---|---|---|---|---|
| Species facts join (ECOCROP, Plant Variety Database, Tichý indicator values) | `facts.json` for 15 species, all resolved to GBIF keys | ECOCROP repo carries no licence; variety DB CC BY 4.0; indicators CC BY 4.0 | `s1/` | rosemary sits under its old name in ECOCROP; spearmint matched only as "var. crispa" |
| Heathrow climatology | station file to Sep 2026 and a summary | Met Office open data | `s2/` | 2021 onward is only 5 to 6 years |
| Stack Exchange Gardening | 17,860 questions, 25,421 answers; a 2,026-row subset of diagnosis and herb questions | CC BY-SA | `s3/se_diagnosis_herb.jsonl` | dump ends 31 Mar 2024 |
| Soybean wilt (Zenodo 8256382) | 1,892 JPEGs, all 640×480 | CC BY 4.0, verified in the record | `s4/` | **labels run 0 to 5, not 0 to 4** |
| AgroBench | 4,342 rows, images embedded in parquet, 2.0 GB | CC BY-NC 4.0 | `s5/AgroBench/` | no task column; the task is only in `raw_metadata.source` |
| MIRAGE | parquet and JSON only | CC BY-SA 4.0 | `s5/MIRAGE/` | images are 10.9 GB of zips, not downloaded |
| DigiGreen preference pairs | 378 rows | CC BY 4.0 | `s5/human_preference_eval_dataset/` | **377 of 378 questions are in Hindi** |
| GBIF photos | 600 images, 40 per species, 15 species | CC0 440, CC BY 160, checked per image | `s6/gbif_manifest.csv` | 590 of 600 are iNaturalist-hosted; 14 herbarium URLs timed out |
| iNaturalist UK autumn | 2,308 photos from 1,213 observations | CC BY 1,384, CC0 898, CC BY-SA 26 | `s6/inat_manifest.csv` | "medium" size is about 375×500; tarragon has none |
| iNatAg herb archives | 13 zips, 28,190 images, 13 GB | repo says Apache-2.0 | `s7/` | **no per-photo licence in the annotations** |
| Kains, Culinary Herbs (1912) | 36,365 words | US public domain | `s8/kains.txt` | none |
| Basil recovery time-lapse (Commons) | 1080p, 22.6 s; 23 frames at one per second | CC BY-SA 3.0 | `s9/` | none |
| OpenPlantBook | 14 plant records | community data | `opb/opb_herbs.json` | no record for male fern; rosemary only under its old name |

## Species facts coverage

Filled (Y) or empty (-). Temperature optimum and absolute range, rainfall, pH, killing
temperature, photoperiod and cycle come from ECOCROP; light, temperature, moisture and
nutrient indicator values from Tichý et al.; zone, harvest days, sun and water from the
variety database.

| Species | T opt | T abs | Rain | pH | Kill T | Photo | Cycle | L | T | M | N | Zone | Harvest | Sun | Water |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Sage | Y | Y | Y | Y | - | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| Rosemary | Y | Y | Y | Y | - | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| Tarragon | Y | Y | Y | Y | Y | Y | Y | Y | - | Y | Y | Y | Y | Y | Y |
| Oregano | Y | Y | Y | Y | Y | Y | Y | Y | - | Y | Y | Y | Y | Y | Y |
| Garlic chives | Y | Y | Y | Y | - | Y | Y | - | - | - | - | Y | Y | Y | Y |
| Chives | Y | Y | Y | Y | - | Y | Y | Y | Y | Y | - | Y | Y | Y | Y |
| Parsley | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| Spearmint | Y | Y | Y | Y | Y | Y | Y | Y | - | Y | Y | Y | Y | Y | Y |
| Lemon balm | Y | Y | Y | Y | Y | Y | Y | Y | - | - | Y | Y | Y | Y | Y |
| Thyme | Y | Y | Y | Y | - | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| Basil | Y | Y | Y | Y | - | Y | Y | - | - | - | - | Y | Y | Y | Y |
| Coriander | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| Japanese maple | - | - | - | - | - | - | - | - | - | - | - | Y | - | Y | Y |
| Male fern | - | - | - | - | - | - | Y | - | - | - | Y | - | - | - | - |
| Soft shield fern | - | - | - | - | - | - | - | Y | Y | - | - | - | - | - | - |

The twelve herbs are well covered. Killing temperature is missing for sage, rosemary,
thyme, basil and both chives; the maple and ferns have almost nothing. The variety
database rests on few cultivars (basil 14, parsley 9, oregano 5, most others 1 or 2) and
gives basil a zone of 10 to 10, an annual-crop artefact.

**OpenPlantBook** adds light bands that do vary by plant (sage 3,700 to 20,000 lux,
garlic chives 2,500 to 110,000, soft shield fern 300 to 4,000) and temperature bands, but
its moisture band is the same 15 to 60% for eight of the herbs; only parsley (28 to 75%),
coriander and garlic chives (25 to 65%) differ. `min_temp_survival` is empty for every
plant. Use it for light, not for telling herbs apart on watering.

## Heathrow, September to December

| Period | Mean Tmin °C (Sep / Oct / Nov / Dec) | Air-frost days | Rain mm |
|---|---|---|---|
| 1991 to 2020 | 11.6 / 8.8 / 5.3 / 3.1 | 0 / 0.3 / 2.7 / 7.2 | 50 / 65 / 67 / 57 |
| 2021 onward | 12.8 / 9.9 / 6.0 / 4.6 | 0 / 0 / 3.0 / 3.8 | 65 / 79 / 64 / 56 |

Recent autumns run about 1 °C warmer at night with half the December frost days. The frost
rule should use the recent period as its prior and say so.

## Stack Exchange Gardening

- 17,860 questions, 25,421 answers, 7,733 questions with an accepted answer.
- **Diagnosis tag:** 1,463 questions; 1,234 with images; 516 accepted; 459 with both.
- **Herb problems** (tag or title): 637 questions; 382 with images; 289 accepted. Only 74 are both herb and diagnosis (63 with images).
- **Houseplants + diagnosis:** 261 questions; 244 with images; 88 accepted.
- **Preference pairs** (two or more answers, one accepted or a score gap of 3 or more): **3,990** in total; 228 in diagnosis (194 with images) and 177 in herbs (84 with images).

## Soybean wilt labels

Labels are in `dataAnns_goodFiles.csv`, column `Annotation`, keyed by file name; plot and
timestamp are encoded in the name.

| Score | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| Images | 524 | 473 | 369 | 216 | 206 | 104 |

Reasonably balanced across six levels. To compare with our 0 to 3 scale, map 0 → 0,
1 and 2 → 1, 3 and 4 → 2, 5 → 3, and report the mapping; also report the raw six-level
agreement.

## Benchmarks

- **AgroBench** rows by source code: DID (disease identification) 1,502, WID (weed identification) 609, DMN (disease management) 569, PID (pest identification) 544, CMN (crop management) 411, TM (traditional management) 404, MQA (machine usage) 303. Columns `images`, `id`, `messages`, `origin_dataset`, `raw_metadata`.
- **MIRAGE contextual test:** 3,934 rows. Plant Care 1,797, Disease Management 1,184, Pest Management 641, Weeds 312. 65 rows name one of our herbs; 1,290 mention watering or a container.
- **MIRAGE standard test:** 8,184 rows. Plant Identification 2,600, Plant Care 1,609, Pest Identification 1,146, Disease Management 1,047, Pest Management 725, Disease Identification 578, Weeds 479. 198 rows name one of our herbs. Answers are about 99% open-ended. Images are hash paths; the bytes are in the zips.
- **DigiGreen:** columns `question`, `Response A`, `Response B`, `Expert Preference`, `Reasoning`. Preferences: A 244, B 118, none 9, both 7. Reasoning is in English; questions and responses are Hindi.

## Photos per species

| Species | GBIF with image (all / CC0 / CC BY) | GBIF downloaded | iNaturalist UK autumn (observations / photos / captive) | iNatAg images |
|---|---|---|---|---|
| Sage | 7,622 / 673 / 4,749 | 40 | 11 / 12 / 9 | 2,500 |
| Rosemary | 18,299 / 956 / 3,326 | 40 | 46 / 55 / 33 | 2,500 |
| Tarragon | 11,055 / 2,262 / 3,170 | 40 | 0 / 0 / 0 | 2,500 |
| Oregano | 61,702 / 4,537 / 16,638 | 40 | 246 / 347 / 2 | 2,034 |
| Garlic chives | 2,970 / 347 / 568 | 40 | 8 / 26 / 0 | 1,816 |
| Chives | 19,806 / 2,061 / 8,160 | 40 | 10 / 18 / 2 | 1,909 |
| Parsley | 3,353 / 542 / 1,564 | 40 | 9 / 18 / 2 | 2,500 |
| Spearmint | 11,679 / 2,414 / 5,242 | 40 | 50 / 101 / 0 | 2,500 |
| Lemon balm | 18,270 / 1,426 / 8,306 | 40 | 102 / 168 / 3 | 1,889 |
| Thyme | 7,346 / 598 / 2,702 | 40 | 3 / 7 / 1 | 1,992 |
| Basil | 4,413 / 1,423 / 1,778 | 40 | 4 / 5 / 2 | 2,500 |
| Coriander | 5,681 / 1,400 / 2,266 | 40 | 7 / 14 / 1 | 1,689 |
| Japanese maple | 6,196 / 1,653 / 1,340 | 40 | 59 / 86 / 55 | not pulled |
| Male fern | 71,278 / 6,709 / 22,133 | 40 | 494 / 1,066 / 1 | not pulled |
| Soft shield fern | 15,389 / 2,029 / 6,779 | 40 | 164 / 385 / 3 | not pulled |

Peppermint (iNatAg only): 1,861. GBIF median resolution 1536×2048; iNatAg median
768×1024. Each iNatAg zip holds the images and one `annotations.json` carrying photo id,
user, date and coordinates but no licence.

## Kains, Culinary Herbs

Own sections for sage, rosemary, tarragon, chives, parsley, mint, balm, thyme, basil and
coriander. Oregano appears only inside the marjoram section; garlic chives are absent.

## The garden photo index

The private working repo's `garden_photos.csv` lists every garden photo in `data/photos/all/` (gitignored, the maintainer's machine only): 120 photos from 24 Sep to 12 Oct 2026, one row each with `taken_at` from EXIF. All 120 also carry `scene` (trough, pot_row, corner_pot, patio_view, bed_*, garden_view, garden_view_sun_in_frame, maple, the `_closeup` variants, and sky_or_other for sky and indoor shots), `light` (sunny, sunny_hard_shadows, bright, overcast) and `ground` (dry, damp, wet). `ground` is the paving wetness for the visit, so a sky or lawn shot takes the value of the paving photos taken minutes either side. Labels were read off the photos by eye: those before 4 Oct were added on 12 Oct in one pass. Useful subsets: `20261004_131430` and `20261002_123229`, `_140108`, `_144502`, `_144503` have the sun in frame (compass anchors), and so does `20261012_105327`, through cloud, which put the camera at 155° and settled the step 0 compass check; the 2 Oct series shows the watering (paving dry at 10:16, wet from 10:18, dry again by 12:32); 27 Sep shows wet paving with no watering on record; `20261011_1116*` have hard shadows; 7 and 9 Oct show rain-wet paving (no watering after 2 Oct, see the private working repo's `plants.json` notes); `20261011_1407*` and `_1418*` show the newly dug raised bed; `20261012_112912` shows the strip bed's layers: thin topsoil over pebbly clay. Add a row when photos are added.

## The garden photos (auto-crop spike)

A free local model (qwen2.5vl:7b through Ollama, about 10 s a photo) was tested on the 55
garden photos. gemma3:12b cannot localise plants at all (1 good box of 56).

| Viewpoint | Photos | Result |
|---|---|---|
| Pot row | 14 | every terracotta pot cropped cleanly; 26 good boxes of 29; two ferns merge into one box |
| Trough | 16 | plants are not separated: sage and purple sage always return as one box; a two-step split of the trough box frames chives well (16 of 16), sage and rosemary about 13, tarragon and purple sage about 8; oregano never |
| Maple | 3 | already single-plant frames |
| Empty corner, sky or wide | 22 | no usable plants; the model invents a box, so a viewpoint filter must run first |

Estimated yield: about 120 usable per-plant crops. Camera position drifts too much for
fixed pixel regions. Model labels are generic, so plant identity comes from position in
the register and needs human confirmation. Sage, purple sage, rosemary, tarragon and
oregano depend on the new two-shot photo protocol.

## What this corrects in the catalogue

1. **DigiGreen is not usable for judge calibration in English.** The pairs are Hindi. **The Stack Exchange preference pairs (3,990, of which 228 are diagnosis) become the primary calibration set**, with MIRAGE open answers as expert references.
2. **iNatAg is evaluation-only.** Its Apache-2.0 tag covers the compilation, not the iNaturalist users' photos, and it is capped at 2,500 images a species. Anything shown or redistributed must come from GBIF or iNaturalist with a per-image licence, which the manifests record.
3. **GBIF's licence filter is per occurrence, not per image.** A CC0 occurrence can carry non-commercial media; filter on the media licence.
4. **The open wilt set has six levels and small images** (640×480), not five.
5. **Open-licensed UK autumn photos are scarce for the herbs that matter**: basil 4 observations, thyme 3, tarragon 0. Sage, rosemary and maple are mostly garden plants; the wild-growing species dominate.
6. **MIRAGE has few herb cases** (65 contextual, 198 standard) but 1,797 contextual Plant Care rows, which is the right pool for the "ask before answering" test.
7. **AgroBench tasks must be read from `raw_metadata.source`**, and the full set is 2 GB because images are embedded.
8. **ECOCROP lacks killing temperatures for sage, rosemary, thyme, basil and chives**, exactly where frost advice needs them; the care packs' RHS and PFAF figures fill that.
