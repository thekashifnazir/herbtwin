# Generative and world models of plant growth

Survey for the learning track: what exists for predicting how a plant will look in N days
under a condition, generating synthetic stress images, and simulating growth
mechanistically. Swept 3 Oct 2026. Titles, years and ids were confirmed through the arXiv,
OpenAlex or GitHub APIs unless tagged [memory]. Only abstracts were read, so the "inputs
and outputs" and "fit" notes are partly inference. Repo dates are last push.

## 1. Image and video prediction of growth

| Reference | What it does | Inputs → outputs | Code | Fit |
|---|---|---|---|---|
| Drees et al. 2021, Temporal prediction and evaluation of Brassica growth in the field using conditional GANs, Comput Electron Agric 190, arXiv:2105.07789 | cGAN predicts the future appearance of individual plants | early image → later image | none found | prediction |
| **Drees et al. 2023, Data-driven crop growth simulation on time-varying generated images using multi-conditional GANs, arXiv:2312.03443** | image prediction, then trait estimation on the generated image | start image + growth time + treatment → future image + leaf area and biomass | github.com/luked12/crop-growth-cgan (MIT) | **closest published template for "N days under a condition"** |
| Yasrab et al. 2021, Predicting plant growth from time-series data using deep learning, Remote Sensing, doi:10.3390/rs13030331 | GAN forecast of future plant masks (Arabidopsis, Brassica [memory]) | past masks → future mask | unknown | prediction; masks are easier to score than RGB |
| John et al. 2025, Modeling time-lapse trajectories to characterize cranberry growth, ICCV Workshops, arXiv:2510.08901 | self-supervised ViT giving interpretable growth trajectories | time-lapse frames → latent trajectory | not checked | prediction in latent space |
| **Mayborne et al. 2026, A measurement-driven digital twin architecture for plant-level biomass estimation and growth forecasting in hydroponic systems, arXiv:2606.02796** | per-plant lettuce twin; a neural biomass estimate keeps updating growth-model parameters | sensor streams + images → biomass trajectory | not checked | **closest architecture to ours** |

## 2. Synthetic plant and stress images

| Reference | What it does | Fit |
|---|---|---|
| Muhammad et al. 2023, Harnessing the power of diffusion models for plant disease image augmentation, Front Plant Sci, doi:10.3389/fpls.2023.1280496 | diffusion-generated disease images for augmentation | synthetic eval data |
| Li et al. 2023, DDPMs and transfer learning for citrus disease diagnosis, Front Plant Sci, doi:10.3389/fpls.2023.1267810 | augmentation in a low-data setting | learning |
| Tan et al. 2025, Generative diffusion models for agricultural AI, arXiv:2512.19632 | Stable Diffusion fine-tuned on captioned canola and soybean images; indoor-to-outdoor translation | synthetic data; relevant to pots |
| Joshi et al. 2023, AgML, Plant Phenomics, doi:10.34133/plantphenomics.0084 | dataset hub with a Helios-based synthetic generator [memory]; github.com/Project-AgML/AgML (Apache-2.0) | synthetic eval data |
| Olaniyi et al. 2022, GANs for image augmentation in agriculture, arXiv:2204.04707; Hu et al. 2025, Diffusion models in smart agriculture, arXiv:2507.18376 | reviews | learning |

No controlled study of whether synthetic stress images help or hurt evaluation was found.
Treat them as augmentation or as a robustness test, never as the only eval set, and report
real-only versus real-plus-synthetic separately.

## 3. Video world models

| Reference | What it does | Code | Fit |
|---|---|---|---|
| **NVIDIA 2025, Cosmos world foundation model platform for physical AI, arXiv:2501.03575** | pretrained video world models (Predict, Transfer, Reason [memory]); text + image or video → future video | github.com/nvidia-cosmos/cosmos-predict2 and cosmos-transfer1 (Apache-2.0) | prediction experiment. No agriculture or time-lapse use found; trained for robotics and driving at real-time frame rates, so day-scale growth is out of distribution |
| Assran et al. 2025, V-JEPA 2, arXiv:2506.09985 | self-supervised video encoder with latent prediction and planning | github.com/facebookresearch/vjepa2 (MIT) | cheap latent state predictor, no pixels |
| Bruce et al. 2024, Genie, arXiv:2402.15391 | action-controllable world model learned from video | no weights [memory] | learning |
| Xiang et al. 2026, SPROUT, a scalable diffusion foundation model for multi-crop plant phenotyping, arXiv:2603.27519 | diffusion transformer pretrained on 2.6M unlabelled field images; image → dense features | github.com/UTokyo-FieldPhenomics-Lab/SPROUT; MCD-2.6m on Hugging Face | plant-specific backbone, not temporal |

No paper using a "world model" for crops or greenhouses turned up on arXiv. That is an
open slot for the learning track.

## 4. Mechanistic simulators and RL environments

| Reference | What it does | Code | Fit |
|---|---|---|---|
| **Kelly and Foster 2021, AquaCrop-OSPy, Agric Water Manag, doi:10.1016/j.agwat.2021.106976** | pure-Python crop-water model: daily weather + soil + irrigation → canopy cover, soil water, biomass | github.com/aquacropos/aquacrop (Apache-2.0, active) | **best mechanistic backbone for a weather-driven pot water balance** |
| Zhou et al. 2020, CPlantBox, in silico Plants, doi:10.1093/insilicoplants/diaa001 | functional-structural plant model: parameters + environment → 3D architecture, water and carbon fluxes | GitHub, GPL-3.0, Python bindings [memory] | simulator; heavy to parameterise for herbs |
| OpenAlea, GroIMP | L-system and functional-structural platforms | github.com/openalea/openalea; GroIMP is Java | learning |
| Gautron et al. 2022, gym-DSSAT, arXiv:2207.03270 | DSSAT maize as a gym | Fortran-backed | learning |
| Overweg et al. 2021, CropGym, arXiv:2104.04326 | PCSE/WOFOST gym | github.com/WUR-AI/crop-gym (MIT, stale); PCSE active (ajwdewit/pcse) | simulator option |
| van Laatum et al. 2024, GreenLight-Gym, arXiv:2410.05336 | greenhouse climate and crop RL benchmark, 17x faster than GreenLight | github.com/BartvLaatum/GreenLight-Gym2 (AGPL-3.0) | greenhouse scale, not pot scale |
| Hitti et al. 2021, GrowSpace, arXiv:2110.08307 | RL benchmark: moving a light shapes a space-colonisation plant | github.com/YasmeenVH/growspace (MIT, stale) | toy world-model sandbox |
| Hemming et al. 2019, Autonomous Greenhouse Challenge, Sensors [memory] | AI teams controlling real greenhouse compartments; datasets published | data in `data-catalogue.md` section 4 | validation data |

## 5. Vision models for state extraction

- Williams et al. 2023, Leaf Only SAM, arXiv:2305.09418. Zero-shot leaf segmentation; RGB → leaf masks. Leaf count and area for the twin.
- Wei et al. 2024, PlantSeg, arXiv:2409.04038, github.com/tqwei05/PlantSeg. Disease segmentation in the wild; eval data for lesion area.
- Picon et al. 2025, Mitigating domain drift in multi-species segmentation with DINOv2, arXiv:2508.07514. DINOv2 features hold up across device, year and geography. Evidence for frozen DINOv2 as the stress-state encoder.

## 6. A language or vision-language model with a simulator or twin

- **Wu et al. 2024, The new agronomists: language models are experts in crop management, arXiv:2403.19839.** DSSAT state converted to text; a language model sits inside a deep Q-network policy. The most direct template for LLM-in-the-loop.
- **Rasheed et al. 2025, Hybrid modeling, sim-to-real RL, and LLM driven control for digital twins, arXiv:2510.23882.** Miniature greenhouse twin comparing linear, physics, LSTM and hybrid models and MPC, RL and LLM control. Very close to our setup.
- Chen and Huang 2024, Integrating reinforcement learning and large language models for crop production, arXiv:2410.09680. Framework paper.
- Qu et al. 2026, FAIRY, a smart-agriculture agentic engine for full-season soybean operations, arXiv:2609.00106. Deployed agent over sensors, drones, weather and crop models; agent-evaluation ideas.

## 7. The feasible four-week experiment

1. **Build a hybrid latent twin, not pixel generation.** State = frozen DINOv2 or V-JEPA 2 embeddings plus SAM-derived leaf area. A small model predicts state at t+N days from state at t, weather and watering. AquaCrop-OSPy supplies the mechanistic prior. Nemotron reads the predicted state and writes the advice (Wu and Rasheed patterns).
2. **Baselines to beat:** persistence (no change) and the mechanistic model alone, scored on leaf-area error and wilt-onset timing. The Drees conditional GAN is a stretch goal for "show me the plant in N days".
3. **Cosmos as a one-day probe:** run Cosmos-Predict2 zero-shot from an image and a text condition ("unwatered for 5 days") on held-out time-lapses; score with the same state extractor against the real future frame. Failure is expected because the time scale is out of distribution, and that result is still worth reporting.
4. **Data it needs:** a fixed-viewpoint series of the herbs. The photo protocol gives one pass a day; the experiment would be stronger with 2 to 4 a day for 3 weeks and logged watering. Pot weight or soil moisture would help but is not planned. Public substitutes: the 4th Autonomous Greenhouse Challenge series, the Enders maize cold series, the Aberystwyth time-lapse, and crop-growth-cgan's own datasets for method checks.
5. **Constraint:** garden photos are the only hard data being gathered and nothing may wait on them, so the experiment is developed on the public series first and the garden series is the held-out demonstration.
