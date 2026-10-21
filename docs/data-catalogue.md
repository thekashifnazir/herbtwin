# Data catalogue

Every public dataset, API and knowledge source found for evaluating and calibrating the
herb digital twin, swept on 2 Oct 2026. Grouped by what each source is good for. Sizes
are as published; "V" means a link or licence page was fetched and read that day, "U"
means found by search only and not yet opened.

Rules that apply to everything here:

- **Nothing here is committed to the repo.** Scripts download into `data/external/`
  (gitignored) from a manifest of ids; the public repo ships manifests, not images.
- **Non-commercial licences (CC BY-NC, NC-SA, NC-ND) are fine for evaluation** in a
  hackathon project but must never be redistributed or used for a paid product. They are
  marked NC below.
- **When the Hugging Face card and the paper disagree on the licence, trust the card and
  email the authors** before anything leaves the eval harness. Known conflicts: LeafBench,
  AgMMU, MIRAGE, PlantExpertVQA.
- **Our nine herbs appear in no benchmark.** Public sets measure general plant competence;
  Kash's garden cases measure the herbs. Both are needed.

## 1. Species identification (observe stage)

| Source | Link | Size | Labels | Licence | Cost | Fit |
|---|---|---|---|---|---|---|
| **iNatAg** (AgML) V | https://hf.co/datasets/Project-AgML/iNatAg | 4.72M images, 2,959 species, one zip per species | species (iNaturalist research grade) | Apache-2.0 | free | **Best.** Confirmed archives for sage, rosemary, spearmint, peppermint, parsley, oregano, lemon balm, tarragon, garlic chives, chives, thyme, basil, coriander (0.7 to 1.35 GB each). No Japanese maple. `iNatAg-mini` samples 200 per species. |
| Pl@ntNet-300K v1.1 V | https://zenodo.org/records/5645731 | 306,146 images, 1,081 species, 31.7 GB | species, long tail | CC BY 4.0 (per-image mixes noted in paper) | free | Citizen photos, standard baseline |
| iNaturalist 2021 Plantae V | https://github.com/visipedia/inat_comp/tree/master/2021 | 1.15M train, 4,271 species | species, location | research only, no redistribution | free | Backup for iNatAg |
| GBIF occurrence media S | https://www.gbif.org/occurrence/search?taxon_key=6&media_type=StillImage | millions | species, locality, per-record licence | CC0 / CC BY / CC BY-NC per record | free | Filter `license=CC0_1_0` for a clean per-herb set; link rot risk |
| house-plant-species U | https://hf.co/datasets/kakasher/house-plant-species | 14,790 images, 47 species | species | CC BY 3.0 on card, Bing-scraped, non-expert | free | Houseplant sanity check only |
| Indoor Plant Varieties V | https://data.mendeley.com/datasets/ct79299k27/1 | 1,172 raw, 7 species | species | CC BY 4.0 | free | Nursery phone shots |
| DIMPSAR medicinal leaves V | https://hf.co/datasets/Project-AgML/DIMPSAR_medicinal_leaf_classification | 6,900 images, 80 classes | species (incl. mint, coriander, lemongrass, tulsi) | CC BY 4.0 | free | Single leaves, lab |
| Medicinal Leaf, 9 species V | https://data.mendeley.com/datasets/k8m93ft9kk/2 | 1,010 images | species (mint, coriander) | CC BY 4.0 | free | Single leaves |
| MedicinalLeafBD S | https://data.mendeley.com/datasets/2p2k5bt2pg/1 | 6,827 images, 16 species | species (basil 461) | likely CC BY 4.0 | free | Single leaves |
| Flora Incognita S | floraincognita.com | 200k+ images, 1,700 species | species | by request | free | Central European flora, email required |
| Pl@ntNet API S | https://my.plantnet.org | API | species + score | custom, free tier | free tier | A labelling aid, not a dataset |

### 1b. GBIF photo counts per garden species (live API, 2 Oct 2026)

`https://api.gbif.org/v1/occurrence/search?scientificName=<name>&mediaType=StillImage&limit=0`
with `&license=CC0_1_0` or `&license=CC_BY_4_0`. Research-grade iNaturalist only: add `datasetKey=<uuid>` using the key shown on the GBIF
dataset page for "iNaturalist Research-grade Observations" (omitted here because the
secret scanner flags UUIDs).

| Species | All images | CC0 | CC BY 4.0 |
|---|---|---|---|
| Salvia officinalis (sage) | 7,622 | 673 | 4,749 |
| Salvia rosmarinus (rosemary) | 18,299 | 956 | 3,326 |
| Artemisia dracunculus (tarragon) | 11,055 | 2,262 | 3,170 |
| Origanum vulgare (oregano) | 61,702 | 4,537 | 16,638 |
| Allium tuberosum (garlic chives) | 2,970 | 347 | 568 |
| Petroselinum crispum (parsley) | 3,353 | 542 | 1,564 |
| Mentha spicata (mint) | 11,679 | 2,414 | 5,242 |
| Melissa officinalis (lemon balm) | 18,270 | 1,426 | 8,306 |
| Thymus vulgaris (thyme) | 7,346 | 598 | 2,702 |
| Ocimum basilicum (basil) | 4,413 | 1,423 | 1,778 |
| Coriandrum sativum (coriander) | 5,681 | 1,400 | 2,266 |
| Acer palmatum (Japanese maple) | 6,196 | 1,653 | 1,340 |

About 68k CC0 or CC BY images across the herbs; the rest is CC BY-NC (iNaturalist's
default). Garlic chives is the thinnest at 915 licence-clean images.

Small single-herb detection sets on Roboflow Universe (site blocks fetchers; details need a
browser): basil 878 images (CC BY 4.0), mint leaves 542 and 1,470, rosemary 531, plus
"Plant health" (healthy / dried / infected), "Root Rot", "Powdery mildew" and
"StressPlants" (spider mites), all CC BY 4.0 where shown. Kaggle herb sets: Herbify
6,104 images, 91 species (CC BY-NC-SA, NC).

### Added in the second pass

| Source | Link | Size | Labels | Licence | Cost | Fit |
|---|---|---|---|---|---|---|
| **iNaturalist Open Data on AWS** V | https://registry.opendata.aws/inaturalist-open-data/ | 400M+ photos, monthly CSVs (observations, photos, taxa) on public S3, no credentials | species, licence per photo | CC0 / CC BY / CC BY-NC per photo | free | **Bulk route to in-situ photos of our herbs with a licence column; filter taxon + licence** |
| Pl@ntNet-300K species check V | official species list, 1,081 species | n/a | n/a | CC BY 4.0 | free | **None of our 11 herb species are in it.** Not a herb source. |
| Wikimedia Commons categories V | MediaWiki API categoryinfo | top-level files: basil 328, oregano 284, parsley 233, sage 177, lemon balm 168, spearmint 145, thyme 128, tarragon 113, rosemary 110, garlic chives 66, coriander 53; subcategories hold several times more | species | per-file CC | free | Small, curated, licence-clean extras |
| Phone app accuracy studies V | AoB Plants 2026 (PMC13394787), PLoS One 2026 (PMC12952603), PLOS ONE 2023 e0283386 | n/a | n/a | n/a | n/a | Baselines to quote: Flora Incognita 79.2% vs iNaturalist 66.5% top-1 on 5,291 plot images; no app above about 88% on herbaceous plants |
| Agrio API U | https://agrio.app/Agriculture-API/ | API | image diagnosis with confidence and treatment | proprietary | paid | An external oracle for comparison only |

## 2. Disease and health in field conditions (observe stage)

| Source | Link | Size | Labels | Licence | Cost | Fit |
|---|---|---|---|---|---|---|
| PlantDoc V | https://hf.co/datasets/Project-AgML/plant_doc_classification | 2,569 images, 28 classes | disease, healthy | CC BY-SA 4.0 | free | Web-scraped field photos, 13 species |
| PlantWild V | https://hf.co/datasets/Voxel51/PlantWild | 18,542 images, 89 classes (33 healthy) | disease, healthy, text prompts | CC BY-NC-ND 4.0 (NC) | free | In-the-wild |
| CCMT Ghana V | https://data.mendeley.com/datasets/bwh3zbpkpv/1 | 24,881 raw, 22 classes | pest and disease, 4 crops | CC BY 4.0 | free | Field smartphone |
| PlantSeg V | https://zenodo.org/records/16665770 | 11,400 masks + 8,000 healthy | disease segmentation | CC BY 4.0 | free | In-the-wild |
| DiaMOS Plant V | https://zenodo.org/records/5557313 | 3,505 images, 13 GB | 4 pear diseases x 4 severity grades | CC BY 4.0 | free | **Ordinal severity** |
| LeafNet / LeafBench V | https://hf.co/datasets/enalis/LeafBench | 186k images, 97 diseases, 13,950 QA | disease, symptom, stage, nutrient | paper CC BY-NC-ND vs card MIT; gated | free | Licence conflict, ask authors |
| Basil disease and variety V | https://data.mendeley.com/datasets/7hmt25zc56/1 | not stated | basil diseases, varieties | CC BY 4.0 | free | **Culinary basil, garden backgrounds** |
| Mint leaf condition V | https://hf.co/datasets/Project-AgML/mint_leaf_classification | 5,384 images | dried / fresh / spoiled / sunlight | CC BY 4.0 | free | Herb, but detached leaves |
| Bay leaf health V | https://hf.co/datasets/Project-AgML/bay_leaf_disease_classification | 5,696 images | disease / dry / healthy | CC BY 4.0 | free | Herb, detached leaves |
| Money plant disease V | https://hf.co/datasets/Project-AgML/money_plant_disease_classification | 1,872 images | bacterial wilt / healthy / Mn toxicity | CC BY 4.0 | free | Houseplant |
| Epipremnum money plant V | https://data.mendeley.com/datasets/kd8hs7ch6t/4 | 4,304 images, 7 GB | healthy / unhealthy / yellow leaf | CC BY 4.0 | free | Houseplant, cause unlabelled |
| Plant Pathology 2020/2021 S | kaggle.com/c/plant-pathology-2021-fgvc8 | 23,249 apple leaves | scab, rust, complex, healthy | competition rules | free | Orchard photos |
| Cassava Leaf Disease S | kaggle.com/c/cassava-leaf-disease-classification | 21,397 images | 5 classes | competition rules | free | Farmer phone photos |
| FieldPlant U | DOI 10.1109/ACCESS.2023.3263042 | 5,170 images, 27 classes | disease | unknown, hosting not located | free | Plantation photos |
| AgML mirror, 100+ crop sets V | https://hf.co/Project-AgML | thousands each | disease, variety, maturity, pests | mostly CC BY 4.0 | free | Browse by crop when a specific symptom is needed |

### Added in the second pass

| Source | Link | Size | Labels | Licence | Cost | Fit |
|---|---|---|---|---|---|---|
| **Indoor plant diseases** (Mendeley 7wbstnfpjy) V | https://data.mendeley.com/datasets/7wbstnfpjy | 787 images, 9 classes | money, snake and spider plant diseases, leaf withering, tip necrosis | CC BY 4.0 | free | Houseplant symptoms incl. withering |
| Houseplant Diseases Collection V | https://zenodo.org/records/17357719 | 11 indoor disease and pest classes + healthy | disease, pest | CC BY 4.0 but files restricted (403); email author | free | Only other indoor disease set |
| FieldPlant hosting V | https://universe.roboflow.com/plant-disease-detection/fieldplant | 3.27k images | disease | article CC BY; dataset licence unverified | free | Cassava, maize, tomato in plantations |
| CDDM licence V | github.com/UnicomAI/UnicomBenchmark/tree/main/CDDMBench | 137k images | disease | **no licence file anywhere**; Google Drive hosting | free | Treat as unusable for a public repo |
| OPPD seedlings V | https://gitlab.au.dk/AUENG-Vision/OPPD, subset https://zenodo.org/records/7501825 | 7,590 images, 47 species | grown under ideal / drought / natural | CC BY-NC-SA 4.0 (NC) | free | **Labelled drought vs ideal images at scale** (seedlings, weeds) |

## 3. Abiotic stress with labels (observe stage, the hard part)

| Source | Link | Size | Labels | Licence | Cost | Fit |
|---|---|---|---|---|---|---|
| Purdue wilting (tomato, soybean, potted) V | https://pmc.ncbi.nlm.nih.gov/articles/PMC10230817/ | n/a | expert wilting score, soybean 0 to 3 | by request (ace@ecn.purdue.edu) | free | **Closest match to our 0 to 3 scale and potted.** Email early. |
| Maize leaf water treatment V | https://data.mendeley.com/datasets/w77b87fvct/1 | 18,040 crops from 656 photos | well-watered / reduced / drought | CC BY 4.0 | free | 3-level water stress, outdoors |
| Lettuce RGB + thermal + soil moisture V | https://data.mendeley.com/datasets/294zk6k5wf/2 | 104 images, 2 plants, 6 days | irrigated vs not, hourly moisture log, stressed-area masks | CC BY 4.0 | free | Potted, tiny; a worked example for the twin |
| Eschikon Plant Stress Phenotyping (ETH) V | https://projects.asl.ethz.ch/datasets/plant-stress-phenotyping-2018 | 5 GB sugar beet in boxes | drought, N level, box weights, SPAD, climate logs | not stated | free | Water-balance time series with images |
| OLID I cucurbits V | https://zenodo.org/records/8105154 | 4,749 images, 14.5 GB | 57 classes incl. N / K / Mg deficiency | CC BY 4.0 | free | Nutrient, field, chemically verified |
| Banana nutrient deficiency V | https://hf.co/datasets/Project-AgML/banana_leaf_nutrient_classification | 5,348 raw | B, Ca, Fe, K, Mg, Mn, S, Zn deficiency | CC BY 4.0 | free | Nutrient |
| DND-SB sugar beet V | https://zenodo.org/records/4106221 | 5,648 images, 49 GB | 7 fertiliser omissions | CC BY-NC-SA 4.0 (NC) | free | Nutrient |
| Iowa State soybean stress (xPLNet) V | https://github.com/SCSLabISU/xPLNet | 16,573 at 64x64 | 8 stresses incl. iron chlorosis | form-gated | free | Weak, tiny images |
| Rice NPK U | kaggle.com guy007/nutrientdeficiencysymptomsinrice | 1,156 images | N / P / K | unknown | free | Licence risk |
| Bok choy water stress S | cloud.csiss.gmu.edu (503 on check) | n/a | pixel stressed / not | unknown | free | Recheck |
| **Healthy and wilted houseplants** (Kaggle, russellchan) U | kaggle.com/datasets/russellchan/healthy-and-wilted-houseplant-images | 904 images, 292 MB | healthy / wilted | "Data files (c) Original Authors", unclear | free | **Closest public wilting set on real houseplant photos**; binary only; ask the author |
| Houseplant health (Kaggle, tarieretimitimi) U | kaggle.com/datasets/tarieretimitimi/houseplant-health-classification-dataset | 91 images | healthy / unhealthy | CC BY-SA 4.0 | free | Tiny, real home and nursery photos |
| Indoor plant disease detection (Kaggle, abdulahad0296) U | kaggle.com/datasets/abdulahad0296/indoor-plant-disease-detection-dataset | 3.7 GB | disease classes on succulents and houseplants | CC BY 4.0 | free | Compiled from other sets |
| Ornamental plant diseases (Kaggle, itselif) U | kaggle.com/datasets/itselif/ornamental-plant-diseases-master-dataset | 320 MB | rose and aloe pathologies | CC0 | free | Houseplant-adjacent |
| AgEval tasks V | https://github.com/arbab-ml/AgEval | 12 tasks x 100 images | Yellow Rust 6-level, Fusarium wilt 5-level, IDC soybean 5-level | per-source | free | **Ordinal severity tasks with a published VLM protocol** |
| PlantInquiryVQA V | https://hf.co/datasets/SyedNazmusSakib/PlantInquiryVQA | 138k QA, 24,950 images | severity MILD / MODERATE / SEVERE on every diseased image | CC BY 4.0 | free | Ordinal severity at scale |

Not found anywhere: labelled over- or under-watered houseplants; heat, light, sunscald,
frost or root-rot image sets; potted herbs with graded stress. The garden set is the only
source for that and Toloka raters are the only gold.

### Added in the second pass

| Source | Link | Size | Labels | Licence | Cost | Fit |
|---|---|---|---|---|---|---|
| **Basil drought, hyperspectral** V | https://doi.org/10.5281/zenodo.20368943 | 42.6 GB | well-watered / mild / recovery / severe | CC BY 4.0 | free | Only labelled basil stress set anywhere; RGB must be synthesised from bands |
| Sorghum shoot, nitrogen gradient (Danforth) U | https://www.quantitative-plant.org/dataset/sorghum-shoot-dataset-nitrogen-treatments | 96,867 images | 30 genotypes x N deprivation, time series | not stated | free | Nutrient stress over time |
| MiPlo-B / MiPlo-WW U | https://huggingface.co/datasets/jh-yi/MiPlo | large phone multi-view | 6 nutrient treatments, barley and wheat | unverified | free | Nutrient |
| Wheat frost damage V | https://github.com/Gosling6585/Wheat-Frost-Damage-Dataset | 17 MB | frost damage | CC0 | free | **Only CC0 frost set** |
| Grapevine frost (FGVL) V | https://ieee-dataport.org/documents/frost-damaged-leaf-and-grape | 418 frost grapes, 510 frost leaves, masks | frost vs healthy | academic use only, cite | free | Frost with pixel masks |
| Camelina freeze damage U | paper only | 3,114 images, 3 severity classes | ordinal freeze damage | unverified | free | Hosting not found |
| Root rot (Roboflow MTSU) U | https://universe.roboflow.com/mtsu-4rtyu/root-rot | 124 images | healthy root / root-rot leaf | CC BY 4.0 | free | Tiny; the only root-rot set |
| Garden-plants drought protocol, Sci Rep 2026 V | https://www.nature.com/articles/s41598-026-51726-1 | 6,000 time-lapse photos, 10 species x 3 pots x 5 a day x 40 days, soil moisture per pot | drought onset | images NOT released | n/a | **The protocol to copy** if we capture our own herb series |
| Bok choy water stress V | cloud.csiss.gmu.edu | n/a | n/a | n/a | n/a | Dead (503 twice, no archive) |

Heat, sunscald and light-stress labelled RGB sets: confirmed absent after a dedicated
search. "Overwatered" exists as a class in no dataset; the nearest are hydrated vs
dehydrated (Roboflow) and the 904-image healthy vs wilted Kaggle set.

## 4. Growth and time series (twin calibration, plan 3)

| Source | Link | Size | Labels | Licence | Cost | Fit |
|---|---|---|---|---|---|---|
| AGC 3rd edition lettuce images V | https://data.4tu.nl/articles/_/15023088/1 | 388 RGB + 388 depth | fresh and dry weight, height, diameter, leaf area | CC BY 4.0 | free | Growth ground truth |
| AGC 3rd edition climate + images V | https://data.4tu.nl/articles/_/21960932/1 | 45 GB | realised climate, irrigation, daily images | CC BY 4.0 | free | **Best fit for calibrating a weather-driven model** |
| AGC 1st / 2nd editions S | 4TU | climate + harvest, no images | climate, irrigation, yield | CC BY 4.0 | free | Twin calibration |
| Aberystwyth Leaf Evaluation V | https://zenodo.org/records/168158 | 63.7 GB, 15-min time-lapse | leaf masks, harvest biomass | CC BY 4.0 | free | Lab Arabidopsis |
| INRAE RGB-D seedling emergence V | https://doi.org/10.57745/AMFJTK | 70k frames, 190 GB | emergence per pot over time | Etalab 2.0 | free | Potted, no watering data |
| IPK Arabidopsis 55 days V | https://doi.org/10.5447/ipk/2016/7 | 30,426 images | growth, genotype | CC BY 4.0 | free | Lab |
| CVPPP leaf segmentation V | https://www.plant-phenotyping.org/datasets-overview | about 1k images | leaf masks and counts | registration, terms page 404 | free | Potted |
| KOMATSUNA V | https://limu.ait.kyushu-u.ac.jp/~agri/komatsuna/ | 900 RGB + RGB-D | leaf masks over time | not stated | free | Potted |
| GrowliFlower S | https://rs.ipb.uni-bonn.de/data/growliflower/ | 740 plants | stage, size | non-commercial, no redistribution | free | Poor fit |
| Smart-garden sensor log S | https://data.mendeley.com/datasets/jtsyb593fy/1 | 960 rows, 20 days | moisture, temp, light, pump | unknown | free | Twin, no images |

### Added in the second pass

| Source | Link | Size | Labels | Licence | Cost | Fit |
|---|---|---|---|---|---|---|
| **4th Autonomous Greenhouse Challenge (WUR)** V | https://data.4tu.nl/datasets/fa102772-32db-4b30-bace-12f2016722ce/1 | 2 months, 6 teams: 5-minute climate, control, weather and irrigation series (6 GB) + RGB-D canopy images 4x a day (31 GB) | dwarf tomato growth under logged water and climate | CC BY 4.0 | free | **The only verified photo + climate + irrigation time series: the twin's validation set** |
| Enders 2019 maize cold series V | CyVerse doi:10.7946/p2t63c; code github.com/maizeumn/cold-phenotyping | about 1,400 plants, daily RGB days 8 to 16 | cold then recovery, necrosis | CC BY 4.0 | free | Released daily series with stress labels |
| Banerjee 2024 maize drought V | https://doi.org/10.5281/zenodo.10991581 | 17 GB raw | well-watered vs drought, paired in frame | CC BY 4.0 | free | Released paired images |
| PhenoCam v2.0 V | https://daac.ornl.gov/VEGETATION/guides/PhenoCam_V2.html | 393 sites, 2000 to 2018, greenness series + sample JPGs; raw imagery on registration | canopy greenness vs weather | citation policy | free | Weather vs greenness ground truth for seasonality |
| Growing Strawberries V | https://data.4tu.nl/datasets/73424098-2e29-4cc0-9fb2-86e379c8ced0/1 | hourly greenhouse frames 2023 to 2024 | none | CC BY-NC-ND (NC) | free | Time-lapse only |
| ColourQuant coleus V | https://zenodo.org/records/4421754 | 70,000 leaf scans | colour patterning, a houseplant genus | not stated | free | Low |
| CVPPP terms V | https://www.plant-phenotyping.org/datasets-terms-and-conditions | n/a | n/a | **non-commercial by contract, form-gated, no CC** | free | Academic only |
| KOMATSUNA licence V | readme PDFs | n/a | n/a | **no licence stated**, citation request only | free | Ask before public use |
| USA-NPN Nature's Notebook V | https://www.usanpn.org/data/observational | 2009 to present | phenology observations | citation terms | free | US only |

## 5. Vision-language benchmarks (observe and recommend stages)

| Source | Link | Size | Format | Licence | Access | Fit |
|---|---|---|---|---|---|---|
| **AgroBench** (ICCV 2025) V | https://hf.co/datasets/Project-AgML/AgroBench (open mirror) | 4,342 QA; 203 crops, 682 diseases | 5-option MCQ, 7 tasks (disease, pest, weed, crop management, disease management, machinery, traits) | mirror CC BY-NC 4.0 (NC); original gated | open | Observe eval. Human agronomist baseline 36.8% is a sanity ceiling. |
| **PlantExpertVQA** V | https://hf.co/datasets/SyedNazmusSakib/PlantExpertVQA | 765,186 QA, 150,841 images, 38 crops | free text, 9 categories, 3 levels | CC BY 4.0 (card) | open | Observe eval, species and diagnosis |
| PlantInquiryVQA (ACL 2026) V | https://hf.co/datasets/SyedNazmusSakib/PlantInquiryVQA | 138k QA, 34 crops | multi-turn chain of inquiry, severity column | CC BY 4.0 | open | Observe eval with ordinal severity |
| PlantVillageVQA V | https://hf.co/datasets/SyedNazmusSakib/PlantVillageVQA | 193,609 QA, 14 crops | VQA | see card | open | Lab backgrounds, lower value |
| **AgMMU** (NeurIPS 2025) V | https://hf.co/datasets/AgMMU/AgMMU_v1 | 746 MCQ + 746 open eval; 57k facts | 4-option MCQ; open answers graded statement-level | card "cc", paper CC BY-SA 4.0 | open | Both: distilled from 116k Ask Extension grower dialogues |
| **MIRAGE** (NeurIPS 2025) V | https://hf.co/datasets/Project-AgML/MIRAGE | 37,512 consultations; MMST 25.7k + contextual 3.9k; MMMT 861 dialogues | identification and management long-form; clarify-or-answer multi-turn; judges score 0 to 4 | CC BY-SA 4.0 (card) | open | **Both.** Real expert answers 2012 to 2025 with a "Plant Care and Gardening Guidance" category; the contextual split tests "recognise what is missing" (our uncertainty rubric line). Best frontier model 43.9% identification. |
| AgroCoT V | https://hf.co/datasets/Project-AgML/AgroCoT | 4,759 samples | VQA with reasoning field | CC BY-SA 4.0 | open | Observe eval |
| AgroOmni V | https://hf.co/datasets/Project-AgML/AgroOmni | 100k to 1M | multi-view VQA | CC BY-NC 4.0 (NC) | open | Secondary |
| Agri-LLaVA V | https://hf.co/datasets/Project-AgML/Agri-LLaVA_Agricultural_Pests_And_Diseases_Feature_Alignment_Dataset | about 400k | instruction tuning, VQA bench | code Apache-2.0, bench CC BY-NC (NC) | open | Training rather than eval |
| CDDM U | https://github.com/UnicomAI/UnicomBenchmark/tree/main/CDDMBench | 137k images, 1M QA | conversational | not stated | open | Unverified licence |
| AgriBench, Agri-R1, AgriBench-13K | arXiv | landscape or model-only | n/a | n/a | n/a | Not relevant |

## 6. Judge calibration (human-rated agricultural advice)

| Source | Link | Size | What it holds | Licence | Fit |
|---|---|---|---|---|---|
| **DigiGreen human_preference_eval_dataset** V | https://hf.co/datasets/DigiGreen/human_preference_eval_dataset | 378 pairs | question, two answers, expert preference and reasoning (en, hi) | CC BY 4.0 | **Only released set with expert preference labels.** Pairwise judge calibration. |
| DigiGreen human_curated_qa_dataset V | https://hf.co/datasets/DigiGreen/human_curated_qa_dataset | 11,966 pairs | expert-corrected golden answers | CC BY 4.0 | Reference answers |
| AgReason V | https://hf.co/datasets/BGLab/AgReason | 100 questions | agronomist gold answers; statement-level supported / unsupported / missing protocol | none on card | Reference answers and a scoring protocol worth copying |
| MIRAGE and AgMMU open answers | above | thousands | expert answers | see above | Reference answers |
| Pezego-HITL V | https://arxiv.org/pdf/2607.13934 | numbers only | GPT judge vs 135 officer-verified reports: Cohen's kappa 0.77, accuracy 91.9% | not released | A published agreement number to compare against |
| AIEP V | https://arxiv.org/pdf/2601.11537 | numbers only | LLM judge "similar to agronomists, slightly lower", low-to-medium correlations | not released | Expectation setting |
| Farmer.Chat V | https://arxiv.org/abs/2603.03294 | numbers only | 4 experts, 308 queries, 65.9% preference | n/a | Context |

No released agricultural set pairs Likert expert ratings with LLM-judge ratings. Toloka
raters on the garden set will produce the first one this project has.

### Added in the second pass

| Source | Link | What it holds | Licence | Fit |
|---|---|---|---|---|
| CROP benchmark V | https://huggingface.co/datasets/AI4Agr/CROP-benchmark and CROP-dataset | 5,045 MCQ + QA; code Apache-2.0 | CC BY-NC 4.0 (NC) | Text benchmark for the recommend model |
| AgriBench-13K V | arXiv 2508.08632 | "will be released" | n/a | Not available |
| Digital Green LLM-judge write-up V | https://huggingface.co/blog/digital-green-llm-judge | binary rubric judge validated on about 360 human evaluations | n/a | Calibration template to copy |

## 7. Plant-care knowledge (research stage)

| Source | Link | What it gives | Access | Licence | Status | Fit |
|---|---|---|---|---|---|---|
| **FAO-56 Table 12** V | https://www.fao.org/4/x0490e/x0490e0b.htm | Kc ini / mid / end and height; mint 0.60 / 1.15 / 1.10; small vegetables 0.7 / 1.05 / 0.95; no "herbs" row | none | FAO, cite | live, pre-formatted text | **Core twin input.** Transcribe by hand; `FAO56` R package has it as data frames |
| **OpenPlantBook** V | https://open.plantbook.io/docs/ | per-species min and max soil moisture, light (lux, mmol), temperature, humidity | OAuth2 or API key, free | community, ToS unspecified | live | **Only open source with numeric moisture and light bands**. Used since B5 for light and soil-moisture bands when there is no RHS page; its `min_temp` is a growing comfort, not frost survival |
| Growspot light needs V | https://hf.co/datasets/Growspot/houseplant-light-needs-and-indoor-lux-readings | species to light tier with lux bands; indoor lux readings | none | CC BY 4.0 | live | Light bands |
| Perenual V | https://perenual.com/docs/api | 10k species: watering, sunlight, zones, care guides (paid tier) | API key, about 100 req/day free | proprietary, images CC BY-SA | live | Care tags; $59.99/month beyond free |
| Trefle V | https://trefle.io | 1M taxa, sparse growth fields | token, 60/min | per-source attribution | live, docs updated Sep 2026 | Sparse for herbs |
| USDA PLANTS V | https://plants.sc.egov.usda.gov/home/downloads | characteristics: drought tolerance, moisture use, pH | bulk CSV | public domain | live | Patchy herb coverage, licence clean |
| PFAF V | https://pfaf.org | 8k plants: habitat, hardiness, moisture, shade | web only | text CC BY 4.0 | live | Good herb coverage, needs scraping |
| Wikidata V | https://query.wikidata.org/sparql | P8193 hardiness (10 of 11 herbs), P1772 USDA id | public SPARQL | CC0 | live, values inconsistent | Linking ids |
| GBIF species API V | https://api.gbif.org/v1/species/match | canonical taxon keys | none | CC0 | live | **Join key for everything** |
| RHS hardiness scale V | https://www.rhs.org.uk/advice/rhs-hardiness-rating | H1a to H7 bands with temperatures | public page | RHS | live | 9-row table encoded in `rhs.py`; since B5 the research stage reads one species' details page on demand for a plant the seed file lacks and keeps it in `data/pages/` (gitignored, never published) |
| FloraDB full | floradb.dataengineered.io | care thresholds, pet toxicity | paid $49 | commercial | n/a | Skip |
| EOL TraitBank, TRY | opendata.eol.org, try-db.org | research traits | registration | CC BY mixed | EOL unreachable on check | Low |

### Added in the second pass

| Source | Link | What it gives | Access | Licence | Status | Fit |
|---|---|---|---|---|---|---|
| **Plantfolio common-plants** V | https://github.com/Luminoid/plantfolio-common-plants | 952 houseplants and garden plants as JSON: seasonal watering intervals, light, humidity, temperature, toxicity, soil pH, USDA zone, POWO names | git | CC BY-NC-SA 4.0 (NC) | v1.9.0 Sep 2026 | **Best structured care-prior table; NC is fine for the hackathon** |
| GrowSpot published light figures V | https://zenodo.org/records/22172763 | 543 light, humidity and temperature figures transcribed from 80 publishers with source URL per row | none | CC BY 4.0 | live | Citable grounding for "what it needs" |
| OpenFarm V | https://github.com/openfarmcc/OpenFarm | crowd growing guides (watering, sun, spacing) | repo archived Apr 2025, servers down | **data CC0**, code MIT | dump not found | Only CC0 care text; look for a snapshot |
| Home Assistant plant integration V | https://www.home-assistant.io/integrations/plant/ | default thresholds: moisture 20 to 60%, conductivity 500 to 3000 µS/cm | docs | Apache-2.0 | live | Sane rule baseline |
| PlantCV v4 tutorials V | https://github.com/danforthcenter (plantcv-tutorial-v4-VIS-single-plant and others) | notebooks with sample images: leaf area, greenness, morphology | git | CC BY 4.0 | live | **Photo-to-greenness pipeline to call for the RGB index** |
| Kew POWO via pykew U | https://github.com/RBGKew/pykew | descriptions, distributions, names | pip | not stated (WCVP is CC BY) | site blocks fetchers | Taxonomy backbone |
| Perenual free tier V | https://perenual.com/subscription-api-pricing | n/a | **100 requests a day** | proprietary | live | Confirmed limit |
| RHS, AHDB, UC IPM terms V | their copyright pages | care and pest text | web | personal or educational use only, no bundling | live | Cite, never embed |
| MIT OpenAg V | https://github.com/OpenAgricultureFoundation | 51 repos; only a tomato experiment notebook holds grow data | git | GPL-3 | archived | Low |

## 8. Environment (environment stage and twin)

| Source | Link | What it gives | Access | Licence | Status | Fit |
|---|---|---|---|---|---|---|
| Open-Meteo forecast V | https://api.open-meteo.com/v1/forecast | hourly and daily ET0, soil moisture 4 layers, rain, Tmin | none; 10k/day non-commercial | CC BY 4.0 | live, London call checked | Core (in use) |
| Open-Meteo archive V | https://open-meteo.com/en/docs/historical-weather-api | ERA5-Land 0.1 degree from 1950, IFS 9 km from 2017 | same | CC BY 4.0 | live | Core backfill |
| **Open-Meteo Previous Runs** V | https://previous-runs-api.open-meteo.com/v1/forecast | `<var>_previous_day0..7`, forecast as issued N days earlier, from Jan 2024 | same | CC BY 4.0 | live; hourly only, daily sums rejected | **Forecast-skill backtest (plan 3).** Sum hourly yourself. |
| EA flood-monitoring rainfall V | https://environment.data.gov.uk/flood-monitoring | 15-minute gauge totals, last 4 weeks; 3 stations within 10 km of central London | none | OGL v3 | live | Observed rain |
| EA Hydrology API V | https://environment.data.gov.uk/hydrology | qualified daily and 15-minute totals, multi-year | none | OGL v3 | live | Backfilling actuals |
| SoilGrids V | https://rest.isric.org/soilgrids/v2.0/properties/query | clay, sand, field capacity, wilting point at 6 depths | none | CC BY 4.0 | live, **urban pixels null across London** | Needs nearest-valid fallback or user-supplied pot soil |
| **BGS Soil Parent Material Model 1 km** V | https://www.bgs.ac.uk/datasets/soil-parent-material-model/ | texture class, light/medium/heavy, carbonate, depth per 1 km cell across GB | direct zip | OGL | downloaded 11 Oct 2026 to `data/external/soil-and-crops/` | **Soil prior by location; has London values** (see `reference/soil-area-and-what-to-grow.md`) |
| **UKCEH Countryside Survey topsoil pH / bulk density 1 km** V | https://catalogue.ceh.ac.uk/documents/5dd624a9-55c9-4cc0-b366-d335991073c7 | modelled pH 1978/1998/2007 with SE | direct zip | OGL | downloaded 11 Oct 2026 | pH prior (farmland classes, not gardens) |
| Soilscapes (LandIS) V | https://www.landis.org.uk/arcgis/rest/services/UKSoilObservatory/Soilscapes_Cranfield/MapServer/identify | 27-class soil landscape text | none | Cranfield terms | live | weak prior; "unclassified" over built-up London |
| BGS geology OGC API V | https://ogcapi.bgs.ac.uk/collections/bgsgeology625kbedrock/items | bedrock and superficial deposits, 1:625k | none | OGL | live | context for the soil prior |
| Practical Plants (PFAF-derived) V | https://github.com/Ecohackerfarm/powerplant/blob/master/db/practicalplants-data.js | 7,414 species: shade, hardiness, pH, texture, water, edible notes | direct | **treat as CC BY-NC-SA** (wiki footer; PFAF) | downloaded 11 Oct 2026 | dev-time "what to grow" filters only; not shippable data |
| Munsell renotation (RIT) V | https://www.rit-mcsl.org/MunsellRenotation/real.dat | 2,734 Munsell to CIE xyY rows | direct | free, no formal licence (also in `colour-science`, BSD-3) | downloaded 11 Oct 2026 | soil colour from a photo |
| HadUK-Grid 1 km (CEDA) V | https://dap.ceda.ac.uk/badc/ukmo-hadobs/data/insitu/MOHC/HadOBS/HadUK-Grid/ | monthly 30-year frost days, Tmin, sunshine per 1 km | free CEDA login (files redirect to login; listings open) | OGL | fetched 12 Oct 2026: 1991-2020 groundfrost, airfrost, tasmin and sun normals (155 MB) in `data/external/haduk-grid/` | frost and sunshine normals for any GB garden |
| Met Office DataHub V | https://datahub.metoffice.gov.uk | site-specific forecast, 360 calls/day free | API key | Met Office terms | live | Optional second forecast |
| EA LiDAR DSM 1 m V | https://environment.data.gov.uk/dataset/9ba4d5ac-d596-445a-9056-dae3ddec0178 | 2022 composite surface model | none | OGL | live | Garden horizon and shading (plan 3) |
| ERA5-Land (CDS) V | https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land | hourly soil water, potential evaporation | CDS account | CC BY | live | Already served via Open-Meteo |
| Netatmo public map U | https://dev.netatmo.com/apidocumentation/weather | shared personal weather stations | user OAuth token, not app-only | Netatmo ToS | unverified | Low |
| Solar position V | `astral` (Apache-2.0), `pvlib` (BSD-3) | sunrise, elevation, azimuth | pip | OSS | live | Core |

### Added in the second pass

| Source | Link | What it gives | Access | Licence | Status | Fit |
|---|---|---|---|---|---|---|
| Capacitive soil-moisture calibration (Strypsteen 2026, Sensors) V | https://zenodo.org/records/16911016 | Arduino sketches + lab and field VWC calibration tables | none | CC BY 4.0 | live | Calibration curves if a probe is added |
| SIMPaCT park soil moisture V | https://zenodo.org/records/16811020 | 13-sensor VWC time series + virtual-sensor scripts | none | data CC BY 4.0, code MIT | live | Moisture dynamics reference |
| IoT smart-pot log V | https://zenodo.org/records/13346022 | temperature, soil moisture, light, pump state | none | CC BY 4.0 | live | Tiny, exactly the smart-pot shape |
| Netatmo access V | dev.netatmo.com | public station data | **needs a user bearer token with read_station scope; client-credentials grant removed Oct 2022** | Netatmo ToS | verified via community | Low |
| Mi Flora / HHCC logs | GitHub, Zenodo | daemon code only | n/a | n/a | none found | No public time series with photos |

## 9. Picks for plan 2

| Track | Set | Why |
|---|---|---|
| Observe, species on our herbs | iNatAg, 100 per herb, 13 species; GBIF CC0 or CC BY as the second source | Real outdoor photos, Apache-2.0, exact species; GBIF adds a licence filter and per-record provenance |
| Observe, general plant competence | AgroBench mirror 300 MCQ + PlantExpertVQA 500 QA | Expert-labelled, two answer formats |
| Observe, ordinal severity | AgEval three severity tasks + PlantInquiryVQA severity column | Only public ordinal labels; tests the 0 to 3 habit |
| Recommend and uncertainty | MIRAGE contextual split, 200 cases | Scores "ask before answering"; real gardener questions |
| Judge calibration | DigiGreen preference pairs, 378 | Only expert-preference set; checks judge order bias too |
| Stress on our herbs | Garden set (55 photos auto-cropped) + Toloka 3 raters on 100 | Nothing public covers it |
| Twin calibration (plan 3) | **4th AGC (photo + climate + irrigation, CC BY)**, AGC 3rd edition, Enders maize cold series, Banerjee maize drought pairs, Open-Meteo Previous Runs, EA rainfall | Weather-driven ground truth with released images |
| Care priors (research stage) | Plantfolio JSON (NC), GrowSpot published figures (CC BY), OpenPlantBook bands, FAO-56 Kc | Structured, citable, licence-known |
| Drought classifier check | OPPD seedlings ideal vs drought (NC), Fevgas lettuce pair | Only labelled drought images at scale |
| Species photos, bulk | iNaturalist Open Data on S3 with the licence column | Licence-filterable in-situ photos of our herbs |

Requests worth sending now: Purdue wilting data (0 to 3 potted soybean, Delp lab), Jeon 2025
(basil RGB and depth series), AgroBench original (non-NC licence), and the Zenodo
Houseplant Diseases Collection author (files restricted).

## 10. Gaps the sweep confirmed

- No labelled over- or under-watered houseplant or herb photos exist publicly beyond one
  binary healthy / wilted Kaggle set of 904 houseplant photos with an unclear licence.
- No heat, light, sunscald, frost or root-rot labelled RGB sets.
- No pot time-lapse pairing photos with watering logs beyond 2 lettuces and the Eschikon boxes.
- Kc values exist for mint only among herbs; others map to FAO "small vegetables" and are
  declared as assumptions.
- Licence-clean care knowledge is thin: USDA PLANTS (public domain), PFAF text (CC BY),
  OpenPlantBook (community). RHS and Perenual are closed.
- SoilGrids is masked over London; soil water capacity needs a fallback.
- Purdue wilting and chickpea water-stress sets are request-only or unpublished. Every herb,
  lettuce and wilting RGB stress study since 2023 withholds its images.
- Pl@ntNet-300K contains none of our herbs; two of six dataset registries are dead
  (plant-image-analysis.org, Papers with Code); the AgML index equals its HF mirror.
  Further sweeps are unlikely to find a public RGB herb-stress set.
- The literature behind the thresholds and methods is in `docs/literature.md`.
