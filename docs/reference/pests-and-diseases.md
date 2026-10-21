# Pests and diseases of herbs and houseplants: data and references

What labelled images and licence-clean text exist for the problems our plants actually
get. Swept 3 Oct 2026 by direct API calls (Zenodo, iNaturalist, GBIF, Wikimedia Commons,
Wikipedia, OpenAlex, Europe PMC, CrossRef, Hugging Face). Kaggle, Roboflow Universe, CABI
and EPPO block fetchers; those rows are marked unverified.

## 1. Image datasets

| Name | Link | Size | Classes | Licence | Relevance |
|---|---|---|---|---|---|
| **IP102** (Wu 2019) | github.com/xpwu95/IP102; HF mirror EnmmmmOvO/insect-pest-dataset (75,222 rows, claims MIT, dubious) | 75,222 images, about 19k with boxes | 102 | "free for academic usage", contact for other use | 7 aphid classes, greenhouse whitefly, 3 spider-mite classes, generic thrips, 1 mealybug, 5 scale, 2 leaf-miner classes. No slug, snail, vine weevil or fungus gnat. Field crop and citrus photos. |
| **BAU-Insectv2** | hf.co/datasets/Project-AgML/BAU_insectV2_classification; Mendeley 10.17632/x2c6c8thdk.2 | 2,616 phone and DSLR field images | 9 incl. aphids 310, mites 296 | CC BY 4.0 | **Best open-licence aphid and mite photo set** |
| **CCMT crop pest and disease** | hf.co/datasets/Project-AgML/crop_pest_disease_classification | 25,170 raw | 18 incl. green mite 1,015, leaf miner 1,378, Septoria leaf spot 2,743 | CC BY 4.0 | Damage-symptom classes on cassava, tomato, maize |
| Yellow sticky traps (Nieuwenhuizen 2019; md-121 re-annotation) | github.com/md-121/yellow-sticky-traps-dataset; 4TU | 284 images, 8,114 boxes | whitefly 5,807 boxes + 2 predators | CC0 | Whitefly, trap domain not leaves |
| Pest sticky traps (Pisa) | zenodo.org/records/7801239 | trap photos, dot labels | two whitefly species | CC BY 4.0 | Same caveat |
| AgriPest (Wang 2021) | doi:10.3390/s21051601 | 49.7k images, 264.7k boxes | 14 | paper CC BY; data by request | Wheat, rice, maize trap rigs; low relevance |
| Pest24 (Wang 2020) | doi:10.1016/j.compag.2020.105585 | 25,378 images | 24 | none stated; by request | Light-trap moths; near zero |
| Roboflow-100 pests | hf.co/datasets/LibreYOLO/pests-2xlvx | 717 | 28 moths and planthoppers | CC BY 4.0 | Irrelevant |
| iNaturalist 2021 Insecta | github.com/visipedia/inat_comp (AWS Open Data) | 663,682 train images | 2,526 insect species | non-commercial research; per-photo CC | Adults of many of our pests, no leaf or damage context |
| **iNaturalist and GBIF live pulls** (research grade; open-licence count / all) | api.inaturalist.org, api.gbif.org | vine weevil 1,913 / 16,789 (GBIF 14,562 media); grey field slug 2,063 / 14,425; Arion vulgaris 900; Cornu aspersum 16,125; two-spotted spider mite 111 / 306; greenhouse whitefly 19 / 158; citrus mealybug 9 / 87; western flower thrips 6 / 31; peach-potato aphid 29 / 72; Liriomyza 1,613; **mint rust 63 / 295 (GBIF 5,385)**; basil downy mildew 9 / 24; Septoria petroselini 3; Botrytis 50; Golovinomyces 4,107 | per taxon | per-photo CC, default BY-NC | **The only labelled source for mint rust, basil downy mildew, vine weevil and slugs.** Filter per-photo licence. |
| **Wikimedia Commons categories** (file counts) | commons.wikimedia.org/wiki/Category:<name> | Puccinia menthae 47; Peronospora belbahrii 17; Peronospora lamii 9; Botrytis cinerea 68; Powdery mildew 57; Golovinomyces biocellatus 11; Neoerysiphe galeopsidis 21; Septoria 27; Fusarium 52; Phytophthora 28; Pythium 18; Otiorhynchus sulcatus 131; Aphidoidea 110; Aphis fabae 44; Tetranychus urticae 81; Aleyrodidae 41; Pseudococcidae 40; Planococcus citri 24; Diaspididae 21; Coccidae 11; Thripidae 30; Sciaridae 6 and Bradysia 10; Arion vulgaris 74; Deroceras reticulatum 45; Liriomyza 3 | small | per-file CC or public domain | Few-shot reference photos |
| AgroBench pest task | hf.co/datasets/Project-AgML/AgroBench | 544 images, 134 pest categories, MCQ | | CC BY-NC 4.0 | Eval only |
| Agri-LLaVA | hf.co/datasets/Project-AgML/Agri-LLaVA_... | 391,785 images, 221+ pest and disease types from 16 sets | | per source, inherits IP102 terms | Instruction data |
| Kaggle agricultural pests (vencerlanz09) | kaggle.com/datasets/vencerlanz09/agricultural-pests-image-dataset | about 5.5k web images | 12 incl. **slug, snail, weevil**, earwig | unverified (blocked) | Only set with slug and snail classes; scraped |
| Herb disease image sets | none found on Zenodo, HF, OpenAlex or Europe PMC for mint rust, basil downy mildew, basil fusarium, sage or rosemary powdery mildew, parsley Septoria, coriander blight, lemon-balm mildew, Phytophthora on herbs, Botrytis on herbs | | | | Zenodo 4956789 (basil downy mildew) is tabular |
| Houseplant pest sets | none labelled on HF or Zenodo; tiny unlicensed mealybug YOLO repos on GitHub; Roboflow unverifiable | | | | Gap |

## 2. Text and image references for grounding

| Source | Licence | Coverage |
|---|---|---|
| **Wikipedia** | CC BY-SA 4.0 | Aphid (large, 50 images), Thrips, Scale insect, Whitefly, Mealybug, Fungus gnat, Tetranychus urticae, Vine weevil (short), Deroceras reticulatum, Botrytis cinerea, Erysiphaceae, Downy mildew, Phytophthora, Fusarium wilt, Root rot (short), Puccinia menthae (no infected-leaf photo, no control section), Peronospora belbahrii (stub). **Missing:** Septoria petroselini, Peronospora lamii, a "mint rust" article. |
| **Wikimedia Commons** | per file | counts above |
| **UC IPM Pest Notes** | UC Regents: personal and educational use, no commercial redistribution; photos need permission | Aphids pn7404, Scales pn7408, Fungus gnats pn7448, Thrips pn7429, Spider mites pn7405, Snails and slugs pn7427, Powdery mildew pn7493 at ipm.ucanr.edu/PMG/PESTNOTES/. Link and cite, never bundle. |
| PFAF | text CC BY 4.0 with share-alike wording; images CC BY-NC-ND | thin on pests and diseases |
| CABI Compendium and PlantwisePlus Knowledge Bank | non-commercial research and teaching; site blocks fetchers | datasheets exist for all of ours (basil downy mildew 118352, mint rust 45826, vine weevil 38071, citrus mealybug 45082). Treat as non-open; cite. |
| EPPO Global Database | all rights reserved; quarantine pests only | none of ours; skip |
| Open-access reviews | CC BY | Plant Methods 2021 review doi:10.1186/s13007-021-00722-9; Front Plant Sci 2025 vision-language review doi:10.3389/fpls.2025.1579355 |

## 3. Pest identification accuracy, published

- IP102 (102 classes): ResNet-50 about 49% top-1 in 2019; 2025 state of the art 78.8% (Swin-AARNet, doi:10.3389/fpls.2025.1619551), 78.4% (AdaptPest-Net, doi:10.3390/e27121211). Fine-grained pest ID has a ceiling near 79% for CNN and ViT models.
- AgroBench pest task (134 categories, MCQ): GPT-4o 77.8%, Gemini 1.5 Pro 74.5%, Qwen2-VL-72B 73.4%, LLaVA-Next-72B 49.8%; disease task GPT-4o 64.2%.
- AgEval (arXiv 2407.19617): best model F1 46.2% zero-shot to 73.4% with 8 shots; per-class variation 26 to 58%.
- LLMI-CPD (Sci Rep 2025, doi:10.1038/s41598-025-01908-0): 32 pest classes, 822 images; a fine-tuned multimodal model beat Qwen-VL, VisualGLM and MiniGPT4.
- No study evaluates vision-language models on home phone photos of houseplant or herb pests.

## 4. Our likely problems: who has labelled images

| Status | Problems |
|---|---|
| **Open, ML-ready** | aphids (IP102 7 classes; BAU-Insectv2 310 CC BY), spider mites (IP102 3 classes; BAU 296; CCMT green mite 1,015), generic powdery mildew (PlantVillage; wheat PM Zenodo 13137587 CC BY, not herb-specific) |
| **Citizen science only** (organism, not damage; per-photo licences) | mint rust (Commons 47; iNat 63 open of 295; GBIF 5,385 media), vine weevil adults (iNat 1,913 open; Commons 131; larvae and root damage essentially absent), slugs (iNat 2,063 open grey field slug, 900 Arion, 16k Cornu), mealybug, scale, thrips, fungus gnat (Commons 40 / 32 / 30 / 16; IP102 has crop species only) |
| **Thin** | basil downy mildew (Commons 17, iNat 9 open, GBIF 19, Wikipedia stub, no dataset) |
| **None anywhere** | sage root rot (only generic Phytophthora 28 and Pythium 18 on Commons), sage, rosemary and lemon-balm powdery mildew as herb-specific classes (Golovinomyces biocellatus 11, Neoerysiphe galeopsidis 21), parsley Septoria, coriander bacterial blight, basil Fusarium, Botrytis on herbs, slug leaf damage |

**Implication for the pipeline.** Pest organism identification can lean on IP102, BAU and
iNaturalist few-shot references. Herb disease identification has no training data and must
be zero-shot by the vision-language model, grounded on Wikipedia and UC IPM text plus a
handful of Commons and iNaturalist reference photos, and evaluated on a self-built set from
the nine real herbs.
