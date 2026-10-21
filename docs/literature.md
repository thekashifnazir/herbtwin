# Literature: what the science says about what we are building

Companion to `docs/data-catalogue.md`. Swept 2 Oct 2026. "V" means the link or DOI was
opened that day; "U" means found by search only. Each entry says which pipeline part it
informs: observe, research, twin, recommend, judges.

## 1. Numbers we reuse (from controlled experiments with photo series)

These are the defaults the twin and the observe prompt start from. Each is an assumption
until the garden set confirms or corrects it.

| Quantity | Value | Source |
|---|---|---|
| Days from water withheld to visible wilting, pots | 2 (larch), 3 to 4 (soybean), 6 to 7 of a 9-day dry-down (cotton) | Jeong 2025, Yang 2023, Das Choudhury 2023 |
| How early image metrics flag stress before the eye | 2 to 3 days | Yang 2023, Das Choudhury 2023 |
| Standard "drought" setpoint in pot experiments | daily irrigation to 30% field capacity | Prigigallo 2025 |
| Basil visible loss | within 7 days at 15 to 20% volumetric water; tolerates 25 to 30% for about 14 days | Lazarevic 2021 |
| Transpiration starts falling | fraction of transpirable soil water 0.3 to 0.4 (species range 0.22 to 0.71) | Sadras and Milroy 1996, Broughton 2024 |
| Potted substrate setpoints that change growth | 0.10 to 0.45 L/L volumetric | Nemali and van Iersel 2006 |
| Recovery after rewatering | turgor back in 1 to 4 days; growth stays below control | Marchetti 2019 |
| False recovery | wilted tips "recover" overnight then die within 1 to 2 days | Jeong 2025 |
| Cold, basil | wilting and discolouration after 24 h at 4 °C; progressive injury over 3 to 12 days at 4 °C, 12 °C mostly safe | Begum 2023, Liu 2025 |
| Cold, maize | necrosis peaks about 4 days after the cold ends | Enders 2019 |
| Heat, wheat | 2 h at 48 °C folds leaves reversibly (recovers in about 50 min); over 2.5 h is irreversible | Rascio 2020 |
| Light, shade plants | bleaching above roughly 80 to 114 µmol m⁻² s⁻¹; burn within weeks to 3 months | Manda 2018, Tejukumar 2023 |
| Drought vs disease in images | drought = slower growth, greener and more compact canopy; yellowing = senescence or disease, not drought | Prigigallo 2025 |
| Crop coefficient, basil | field 0.30 / 0.86 / 0.76 (initial / mid / end); pot values reported 1.5 to 2.8 | Iranian J Soil Water Res; Hortic Bras (U) |
| Crop coefficient, mint | 0.60 / 1.15 / 1.10 | FAO-56 Table 12 |
| Frost forecast error at 6 h lead | 1.5 to 1.7 °C | Talsma 2023 |

## 2. Experiments with photographic time series under controlled conditions

| Study | Species | Conditions | Cadence | Images released? | Reusable finding |
|---|---|---|---|---|---|
| Lazarevic 2021, Front Plant Sci, doi:10.3389/fpls.2021.629441 V | basil 'Genovese', pots | 45 to 50% VWC control; 25 to 30% and 15 to 20% drought; NaCl | weekly, 4 weeks, multispectral | no, traits only | severe drought visible by day 7, mild by day 14 to 21 |
| Jeon 2025, Agronomy 16(1):55, doi:10.3390/agronomy16010055 U | basil | water deficit then recovery | RGB + depth + fluorescence series | on request (approval needed) | 3D-CNN separates stress from recovery at 96.9%; **email for the basil RGB series** |
| Begum 2023, Front Plant Sci, doi:10.3389/fpls.2023.1239010 V | basil 'Marian', pots | 24 h at 4 °C, far-red pretreatment | scored 1 to 5 once | supplementary photos | 24 h at 4 °C wilts untreated basil |
| Liu 2025, 4TU, data.4tu.nl/datasets/1e2af139-9d2f-4098-91ce-491d3b39b635 V | basil leaves | 4 °C vs 12 °C storage | days 0, 3, 6, 9, 12 | scores only, CC BY 4.0 | chilling injury progresses in 3-day steps |
| Prigigallo 2025, Plant Phenomics, doi:10.1016/j.plaphe.2025.100124 V | tomato, 2 L pots, 10 genotypes | 30% FC drought, two cycles, rewatering | RGB twice weekly, days 8 to 41 | no, indices only | drought looks compact and green; yellowing is not drought |
| Yang 2023, Plant Methods, doi:10.1186/s13007-023-01026-w V | soybean (water), tomato (Ralstonia) | irrigation stopped 7 days | days 1, 3, 4, 5, 6 | **on request, Purdue** | wilting metrics predict the 0 to 3 expert score 2 days early |
| Garcia Martinez 2025, zenodo.org/records/15915150 V | tomato, pots | 7 days deficit + 8 days recovery | hyperspectral per stage | yes, CC BY 4.0, 6 GB, not RGB | full stress and recovery cycle in 15 days |
| Das Choudhury 2023, Front Plant Sci, doi:10.3389/fpls.2023.1003150 V | cotton, pots | dry-down from 50% FC, 8 to 9 days | daily RGB, 5 views | on request | drooping only in the last 3 days |
| Fevgas 2025, data.mendeley.com/datasets/294zk6k5wf V | lettuce | watered vs not | twice daily RGB + thermal, 6 days | **yes, CC BY 4.0, 104 images** | thermal shows stress before RGB |
| Enders 2019, Plant Direct, doi:10.1002/pld3.104 V | maize seedlings, 40 lines | 6/2 °C for 2 days then recovery | daily RGB, days 8 to 16 | **yes, CyVerse doi:10.7946/p2t63c, CC BY 4.0; code github.com/maizeumn/cold-phenotyping** | necrosis peaks 4 days after cold |
| Marchetti 2019, Front Plant Sci, doi:10.3389/fpls.2019.01252 V | barley canopies | 100 to 65% FC over 13 days, rewatered day 15 | daily RGB | no | height drops from day 11, recovers in 4 days |
| Rascio 2020, Plants, doi:10.3390/plants9060718 V | durum wheat | 48 °C for 20 min to 5 h | phone time-lapse every 4 s | supplementary videos | reversible under 2 h, irreversible over 2.5 h |
| Jeong 2025, Front Plant Sci, doi:10.3389/fpls.2025.1550748 V | larch seedlings | water withheld, soil 29% to 14% | RGB every 10 min + thermal, 7 days | no | needle angle changes day 2; false overnight recovery |
| Xue and Loudet 2024, doi:10.57745/E8XYSG V | Arabidopsis, 5 accessions | mild water x N deficit | daily, days 9 to 31 | traits only, Etalab 2.0 | daily hue and area trajectories |
| Khanna 2019, Eschikon, doi:10.3929/ethz-c-000788562 V | sugar beet in boxes | drought x N x weeds | biweekly RGB, IR stereo, multispectral, 2 months | **yes, licence unstated; box weights = soil moisture** | nutrient vs drought imagery with SPAD truth |
| Banerjee 2024, doi:10.5281/zenodo.10991581 V | maize | well-watered vs drought, 3 trials | cadence unstated | **yes, CC BY 4.0, 17 GB** | watered and drought plants side by side in one frame |
| Garden-plants drought, Sci Rep 2026, s41598-026-51726-1 V | 10 garden species, 3 pots each | drip then withheld, soil moisture per pot | 5 photos a day, 40 days | no, indices only | **the protocol to copy if we capture our own series** |
| Basil drought, doi:10.5281/zenodo.20368943 V | basil | well-watered / mild / recovery / severe | hyperspectral | yes, CC BY 4.0, 42.6 GB, not RGB | only labelled basil stress set anywhere |
| Ginzburg and Rhee 2023, Bio-protocol, doi:10.21769/BioProtoc.4593 V | Arabidopsis | shared-pot drought, pots weighed daily | Raspberry Pi every 15 min | protocol + code | cheapest rig for a herb time series |
| Tejukumar 2023, doi:10.58993/ijh/2023.80.2.7 V; Manda 2018, horticulturejournal.usamv.ro/pdf/2018/Art100.pdf V | peace lily; Chlorophytum | 35 to 90% shade; 3 light levels | endpoint | no | excess light bleaches then burns |
| Mentha arvensis low-cost platform, doi:10.22541/au.166758437.74559609/v1 U | mint | irrigation levels | automated RGB | unknown | canopy colour tracks drought |

Verified result of the sweep: no released RGB time series exists for sage, rosemary,
thyme, mint, parsley, coriander, oregano, lemon balm, chives or tarragon. Every herb,
lettuce and wilting RGB stress study since 2023 withholds its images. Two emails are
worth sending: Delp lab, Purdue (Yang 2023, 0 to 3 wilting on potted plants) and Jeon
2025 (basil RGB and depth series).

## 3. Annotated bibliography by thread

### Plant and crop digital twins (twin)

- Ariesen-Verschuur, Verdouw, Tekinerdogan 2022, Digital twins in greenhouse horticulture: a review, Comput Electron Agric 199:107183 V. Only about 9% of twins model the plant itself; most track climate; validation rarely reported. Our plant-level twin with a stated validation is the unusual part.
- Melesse 2025, Digital twin-based applications in crop monitoring, Heliyon, doi:10.1016/j.heliyon.2025.e42137 V. Taxonomy (physics, agent, data, hybrid); state is soil moisture, temperature, humidity, growth; validated by comparison to field observation.
- Bukhtoyarov 2025, Hybrid digital twin for phytotron microclimate control, AgriEngineering 7(9):285 V. Physics plus ML twin of a small enclosed growing space, the nearest published scale to a pot.
- Predictive modeling of plant growth in simulated and controlled environments, arXiv:2412.10538 V. Catalogue of growth models for controlled settings.
- GARTWIN (ITER, 2023 to 2026), garden irrigation twin, iter.es U. The only urban-garden twin found; no paper yet.

### Container water balance (twin, research)

- Allen et al. 1998, FAO Irrigation and Drainage Paper 56, fao.org/3/X0490E V. The ET0 x Kc x Ks bucket we implement; Ks from the depletion fraction p.
- Pereira et al. 2021, Updates and advances to the FAO56 method, Agric Water Manag 248:106697 U. Dual Kc and stress handling.
- Nemali and van Iersel 2006, An automated system for controlling drought stress and irrigation in potted plants, Sci Hortic 110:292 V. Substrate VWC setpoints 0.10 to 0.45 L/L with growth response curves: the "simulated action" response.
- Beeson 2010, HortScience 45(8):1260 and Million and Yeager 2010, HortScience 45(11):1741 U. Container ET validated by daily weighing; a canopy-closure "water needs index" instead of Kc; 4-day sums r = 0.88.
- Sadras and Milroy 1996, Soil-water thresholds for leaf expansion and gas exchange, Field Crops Res 47:253 U. Transpiration breakpoint at FTSW 0.3 to 0.4.
- Broughton et al. 2024, Front Plant Sci 15:1451993 V. Modern FTSW dry-down protocol; threshold 0.22 to 0.71 by genotype, so keep it a parameter.
- Basil Kc, Iranian J Soil Water Res (ijswr.ut.ac.ir/article_72332) and pot basil in Hortic Bras U. Pot Kc far exceeds field Kc; declare which we use.

### Frost and hardiness (twin, research)

- Talsma et al. 2023, Frost prediction using ML and DNN models, Front Artif Intell 5:963781 V. 6 to 48 h lead; 6 h error 1.5 to 1.7 °C, our forecast error bar.
- Ferguson et al. 2011, Dynamic thermal time model of cold hardiness, Ann Bot 107:389 V. Hardiness as a state variable updated daily and compared with forecast minima: the frost-risk pattern to copy.
- Wang et al. 2024, NYUS.2 real-time grapevine freezing tolerance, Hortic Res uhad286 V. Weather-fed hardiness simulation at scale.
- RHS hardiness H1a to H7 V and USDA PHZM 2023 V. RHS is absolute minimum, USDA a 30-year mean; do not mix.

### Vision-language models for plant diagnosis (observe)

- Agri-LLaVA 2024, arXiv:2412.02158 V. 221 pests and diseases, about 400k instruction pairs.
- Awais et al., AgroGPT, WACV 2025, arXiv:2410.08405 V. Turns vision-only datasets into expert instruction data; cheap recipe for few-shot exemplars.
- Arshad et al., AgEval, WACV 2025, arXiv:2407.19617 V. 12 stress tasks; few-shot lifts F1 from 46 to 73; exact-category exemplars add 15 F1. **Direct template for the 0 to 3 stress prompt.**
- Shinoda et al., AgroBench, ICCV 2025, arXiv:2507.20519 V. 682 disease classes; weed ID near random for open VLMs; human expert baseline 36.8%.
- AgMMU, NeurIPS 2025, arXiv:2504.10568 V. 116k grower-extension dialogues.
- MIRAGE, NeurIPS 2025, arXiv:2506.20100 V. Multi-turn expert consultations including when to ask a clarifying question.
- No NVIDIA or Nemotron agricultural publication was found.

### LLM advisory agents in agriculture (recommend, judges)

- Farmer.Chat 2024, arXiv:2409.08916 V. RAG over vetted extension content; follow-up questions were 45% of peak interactions; RAGAS checked against 1,000 human-reviewed queries.
- Digital Green, Bolstering a RAG app with LLM-as-a-judge, huggingface.co/blog/digital-green-llm-judge V. Binary rubric judge validated on about 360 human evaluations: a practical calibration template.
- AIEP Initiative 2025, arXiv:2601.11537 V. Weather and soil tool calls plus RAG; corpus curation is the bottleneck; judge tracks agronomists but scores slightly low.
- Pezego-HITL 2026, arXiv:2607.13934 V. Policy-grounded with humans in the loop; judge vs 135 officer-verified reports, Cohen's kappa 0.77.

### LLM-as-judge method (judges)

- Zheng et al. 2023, Judging LLM-as-a-judge with MT-Bench, arXiv:2306.05685 V. Position, verbosity and self-enhancement bias; swap positions.
- Wang et al. 2024, Large language models are not fair evaluators, arXiv:2305.17926 V. Order swap flips verdicts; balanced position calibration.
- Liu et al. 2023, G-Eval, arXiv:2303.16634 V. Chain of thought then form-filling rubric; bias toward LLM-written text.
- Kim et al., Prometheus (ICLR 2024, arXiv:2310.08491) and Prometheus 2 (arXiv:2405.01535) V. Rubric plus reference answer, pointwise and pairwise.
- Shankar et al. 2024, Who validates the validators?, arXiv:2404.12272 V. Criteria drift: raters refine the rubric while grading; iterate with humans, then freeze and fingerprint.
- Thakur et al. 2024, Judging the judges, arXiv:2406.12624 V. Report Cohen's kappa or Scott's pi, never raw agreement.
- Gu et al. 2024, A survey on LLM-as-a-judge, arXiv:2411.15594 V. Bias taxonomy.
- Reliability without validity, 2026, arXiv:2606.19544 V. 21 judges, 541k judgements: kappa sits 33 to 41 points below raw agreement; test-retest above 0.95 coexists with position bias above 0.10. Proposes a minimum viable validation protocol, which plan 2 adopts.
- Rubric-agreement study, 2026, arXiv:2603.11027 V. Sharing rubric structure alone restores 62% of judge agreement.

### Wilting, RGB indices, rater reliability (observe, judges)

- Yang et al. 2023, Image-based plant wilting estimation, Plant Methods 19 V. RGB colour and shape metrics predict expert wilt scores.
- Hunt et al. 2013, TGI, doi:10.1016/j.jag.2012.07.020 V; Louhaichi et al. 2001, GLI V; Woebbecke et al. 1995, ExG U. Visible-band greenness indices computable from a phone photo.
- Harikumar et al. 2025, smartphone RGB and LiDAR for leaf nitrogen, Front Plant Sci 16:1592329 V. Phone RGB suffices for nitrogen status, with limits.
- Bock et al. 2020, From visual estimates to fully automated measurements of plant disease severity, Phytopathology Res 2:9 V. Rater accuracy, standard area diagrams, Lin's concordance; our ordinal scales need the same statistics.
- Bock et al. 2015, Plant Dis 99:1104 U. Rater concordance ranged 0.2 to 0.99: expect large human-rater spread.
- Lin 1989, A concordance correlation coefficient, Biometrics 45:255 V. Concordance for continuous scores; weighted kappa for ordinal.

### Phone plant identification and home monitoring (observe)

- Campbell, Peacock, Bacon 2023, A repeatable scoring system for smartphone plant-ID apps, PLOS ONE 18:e0283386 V. Flowers beat leaves; no app above about 88%; Pl@ntNet and LeafSnap best.
- Jones 2020, Accuracy of free automated plant identification applications, eprints.glos.ac.uk/12421 U.
- Arboriculture and Urban Forestry 48(1):27, 2022 U. On 55 tree species PictureThis 94% top-1, Pl@ntNet 66%.
- No peer-reviewed evaluation of houseplant-care apps or home smartphone monitoring was found. That gap is part of what this project can publish.

## 4. How this changes the plans

- **Observe prompt:** few-shot exemplars per stress category (AgEval), the "compact and green means drought, yellow means something else" rule, and a greenness index computed alongside the VLM score.
- **Twin:** FAO-56 bucket with Ks from depletion, FTSW threshold as a parameter defaulting to 0.35, pot Kc declared separately from field Kc, hardiness as a daily state compared with forecast minima, frost error bar of about 1.7 °C at 6 h.
- **Judges:** chain of thought then rubric, both orders, repeat runs, weighted kappa and Lin's concordance with n and CI, rubric iterated with Kash before freezing then fingerprinted, the 2026 minimum viable validation protocol as the checklist.
- **Recommend:** a clarifying question is a valid action (MIRAGE, Farmer.Chat); ground on vetted text, never on the model's memory alone.
