# Herb digital twin: design spec

- Date: 2026-10-02
- Status: approved 2026-10-02 (conversational review); implementation plan next
- Scope: the whole hackathon project (one core loop plus bolt-on learning modules)
- Deadline: Nebius x NVIDIA Global AI Hackathon, submissions close 2026-10-30 10:00 PDT;
  judging 2026-12-01 to 2026-12-15 (the demo URL must stay up until then)

## 1. Intent

**What it is.** Take one photo of a potted culinary herb. With no typing from the user, the
system works out what it is, estimates its condition, pulls the local weather history and
forecast, builds a small physics-grounded "digital twin" of the plant, forecasts the risks it
faces over the next 14 days (water stress, frost, fungal disease, heat, light, bolting,
growth stall), simulates what each possible action would do, and recommends one action with
alternatives, confidence, and sources. Several AI judges score every recommendation, and
their scores are calibrated against human expert labels.

**Why it exists (the real goal).** The herbs are the way in. The project is a vehicle for
learning evaluation pipelines, world models, and every Nebius Builder credit (Token Factory,
Tavily, LangSmith, Toloka, Nebius AI Cloud). Winning something is secondary. A design that
uses three services perfectly and skips the rest fails the real goal.

**What makes it more than standard.** Nobody in the surveyed prior art joins photo-based
stress estimation, a weather-driven twin, simulated interventions, and judges measured
against humans. Comparable apps stop at reminders (Greg) or prompt-only diagnosis (two
hackathon repos). Plant-Pulse, a lablab submission, is a fully mocked dashboard with no
model calls. The proactive risk forecast ("bring it in Thursday night, frost at 03:00") is
the differentiator a judge can see in 10 seconds.

**Success looks like.**
- The chain runs end to end on a real photo, on Token Factory, from a public URL.
- Every stage has a measured score on the case set, and the judge-vs-human agreement is
  reported with confidence intervals.
- Every credit has a bounded module with its own measurable output.
- A curated public repo, a 3-minute video, and a specific tool-feedback write-up exist.

**Constraints and decisions already made.**
- Track: Best Apps and Agents. Bonus: Best Use of Tavily (runtime call required). London
  city prize if the Builders & Brews event is attended.
- Mandatory: runtime calls to Token Factory and at least one NVIDIA open model (Nemotron 3
  for reasoning and judging). Public repo with MIT licence. Under-3-minute YouTube video.
- Web app first. Android only if the loop is green with time to spare.
- Local hardware: MacBook Pro M4 Max, 128 GB. Used for local-vs-cloud comparison, not as a
  replacement for Token Factory.
- Time: near full-time through October.
- Submission is a curated repo distilled from this one.

## 2. Architecture (approach A: pipeline-first, eval-native)

The product and the eval harness run the same code: a pipeline of plain functions with typed
inputs and outputs. Each model call goes through a provider adapter. Each stage is a tracing
span. Learning modules plug in as a new stage, a new provider, or a new evidence source.

```
photo ─► observe ─► environment ─► research ─► twin ─► recommend ─► page / JSON
             │           │             │         │          │
             └───────────┴─────────────┴─────────┴──────────┴──► trace (LangSmith + sqlite)
                                                                        │
                                              eval harness ◄────────────┘
                                              judges (3+ families) ◄── rubric
                                              humans (Toloka, outcome photos)
```

Rejected alternatives:
- **Agent-first** (one Nemotron agent choosing its own tool chain): flashier, but
  non-deterministic runs make judge comparison noisy and per-stage eval hard. Used in one
  place only: the Tavily research agent.
- **Notebook-first** (one experiment per credit, stitch a demo at the end): fastest learning
  per hour, but "complete product" is a scored criterion and stitching always slips.

### 2.1 Stack

- Python 3.12, `uv`, pydantic for every stage boundary.
- FastAPI. Server-rendered pages with HTMX for the product. A JSON endpoint
  (`POST /api/analyse`) alongside, for the eval harness and a future Android client.
- Docker image deployed on a Nebius Serverless Endpoint (public URL, billed per second;
  counts as "runs on Nebius AI Cloud"). Local run is `uv run`.
- LangSmith for traces, datasets, experiments, and feedback. A sqlite trace store underneath
  (lifted from an earlier eval project) so everything works offline.

### 2.2 Stages

| Stage | In | Out | Provider |
| --- | --- | --- | --- |
| observe | photo (+ few-shot examples) | species candidates with confidence; water stress 0-3; heat/light stress 0-3; "fine, leave it" yes/no; symptoms; leaf cues; soil-surface cue | VLM on Token Factory (Nemotron 3 Nano Omni if listed, else GLM-5.3-Flash or Qwen3.8-27B); Cosmos Reason2-8B as an NVIDIA-model candidate via the serverless cookbook template |
| environment | location, timestamp | past 14 days + 14-day forecast: rain, temperature, humidity, ET0, solar radiation, daylight, sunrise/sunset, UV; horizon profile for the garden | **v1: Open-Meteo only** (UKMO 2 km model; history to 1940; hourly ET0). Week 3+: Previous Runs archive for backtesting; Air Quality API for UV; EA LiDAR 1 m DSM + pvlib for shading; Meteostat / Met Office land observations as station ground truth; Netatmo public stations (median within 3-5 km; latest readings only, so poll and store) for hyperlocal temperature and humidity; Environment Agency rain gauges (free, 15-min) for "did it actually rain" |
| research | species, symptoms | knowledge pack: water, light, temperature thresholds, disease conditions, sources | OpenPlantDB (CC0 seed: sun, water, frost tolerance, days to maturity for all six herbs) + Perenual (structured care fields), then Tavily to fill gaps and fetch thresholds with sources; every field carries a source URL and a verified flag; cached per species in a JSON store |
| twin | observation, environment, pack, watering log | plant state with uncertainty; 14-day risk strip per risk per action branch | pure Python + AquaCrop-OSPy surrogate |
| recommend | state, risk table, pack | one action, alternatives table, confidence, "why", sources | Nemotron 3 Ultra for recommend (Super if Ultra is unlisted or too slow); Nano for formatting and extraction |
| judge | the whole record | rubric scores per dimension | 3+ judges from different model families |

### 2.3 Provider adapters

Lifted from an earlier eval project's adapters: a small `ModelAdapter` seam with `complete`,
`complete_json(schema)`, and an `on_call` tracing hook; alias and pricing tables; lazy SDK
import; a deterministic mock adapter. Additions for this project:

- `complete_with_image(system, user, image_bytes, schema)` on the interface.
- `tokenfactory_adapter.py`: OpenAI-compatible, base URL
  `https://api.tokenfactory.nebius.com/v1/`, bearer `HERBTWIN_NEBIUS_API_KEY`.
- Model routing lives in one config: which model for observe, recommend, formatting, and
  each judge. Changing a model is a config change, never a code change.

Existing adapters that carry over for the dev loop and as extra judge columns: Anthropic,
OpenAI, Ollama (local, $0 by construction), Claude CLI, Codex CLI.

### 2.4 Error handling

- Each stage returns a result or a typed failure. Never a silent default.
- The page renders partial results with a plain caption ("weather unavailable; based on the
  photo only"). The real exception is logged with the trace id.
- Every provider call has a timeout and at most one retry. JSON output is parsed from the
  first `{` to the last `}`; on failure, one repair call quoting the bad reply, then fail
  loudly.
- Untrusted input is validated at the boundary: image type and size; model output is data,
  never instructions.

### 2.5 Secrets and privacy

- All keys in `.env`, namespaced `HERBTWIN_*` (`HERBTWIN_NEBIUS_API_KEY`,
  `HERBTWIN_TAVILY_API_KEY`, `HERBTWIN_LANGSMITH_API_KEY`, ...). `.env.example` lists names
  only.
- The garden coordinates are config (`HERBTWIN_HOME_LAT`, `HERBTWIN_HOME_LON`), not derived
  from photos. Raw photos live outside the repo at `HERBTWIN_PHOTOS_DIR`. The
  phone has location tagging off, so EXIF carries time but not GPS.
- Raw photos stay out of git. A curated set goes in the public repo with EXIF stripped.

## 3. Data and the risk gate

### 3.1 Cases

A case is one plant at one moment: `data/cases/<case_id>/meta.json` in the repo, with the
photo filenames resolved against `HERBTWIN_PHOTOS_DIR` (photos never enter git; the curated
public set is a separate, EXIF-stripped export):

```json
{
  "photos": ["20260929_162116.jpg"],
  "taken_at": "2026-09-29T16:21:16+01:00",
  "location": "home",
  "plant_id": "basil-1",
  "labels": {"species": "Ocimum basilicum", "water_stress": 2, "heat_light_stress": 0,
             "fine_leave_it": false, "labelled_by": "kash"},
  "watering_events": ["2026-10-02"],
  "notes": ""
}
```

Labels use a 4-line rubric: species; water stress 0-3; heat/light stress 0-3; "fine, leave
it" yes/no. The last exists because the literature says VLMs over-diagnose healthy plants.
Weather is derived at run time from `taken_at` and location, never stored by hand.

### 3.2 Sources of cases

- Kash's photos from 2026-09-27 onward (still on the phone; copy to `HERBTWIN_PHOTOS_DIR`).
  First watering by the household: 2026-10-02. A household member's earlier watering dates
  to confirm.
- One time-of-day series (same plants, one day, several times) for the sun-exposure model.
- Public herb photos (Pl@ntNet, Kaggle herb sets) labelled by Kash for condition, to reach
  ~100 cases for the Toloka round.
- Outcome photos: every later photo of a plant that already has a case becomes a labelled
  transition (state, action, weather, outcome).

Existing datasets carry training; Kash's photos are the eval set. No herb dataset with
water/heat/light labels was found in four research sweeps (the drought sets found cover
lettuce and ten garden ornamentals), so this labelled set is itself an asset.

### 3.3 Risk gate (first code written)

Question: can a listed VLM on Token Factory identify these herbs and describe their
condition at all?

1. `GET /v1/models` with the key; record whether Nemotron 3 Nano Omni, Super, and Ultra
   are listed and their ids.
2. Send one photo of each herb to the best listed VLM, zero-shot and 4-shot.
3. Pass: species top-1 correct for at least 4 of 6 herbs and a sensible condition
   description. Fail: Pl@ntNet API does species, the VLM does condition only.

Either outcome is fine. It must be known by day 2 because it decides the observe stage.

### 3.4 Friction log

The private working repo's `FRICTION.md` starts on day 1: one line per snag with any tool (what, where, workaround).
It becomes the judged feedback submission.

## 4. Eval and judges

### 4.1 Three layers of truth, cheapest first

1. **Deterministic** (free): species top-1/top-3; water-stress and heat/light-stress
   0-3 scores vs labels (exact and within-one accuracy, mean absolute error); "fine,
   leave it" precision and recall; confidence calibration curve; twin property checks.
2. **AI judges** (Token Factory): three judges from different families (Nemotron 3 Super,
   DeepSeek, gpt-oss-120b; Ultra is excluded because it is the model under test), plus Claude, OpenAI, and a local Ollama model as labelled
   non-Nebius columns. Fixed six-line rubric, each 1-5: species, diagnosis, evidence
   grounding, action correctness, harm avoidance, uncertainty stated. Each judge scores every
   case twice with alternatives in swapped order (position-bias check, new code).
3. **Human gold** (Toloka, $100 credit): ~100 cases, three independent experts each, same
   rubric. The Toloka call asks for help with quorum and quality control; only the rubric
   and task shape are shared.

### 4.2 Headline metric

Quadratic-weighted Cohen's kappa (the rubric is ordinal 1-5) between each AI judge and the
human consensus (median of the three raters; ties resolved toward the lower score), per
rubric line, with bootstrap confidence intervals and repeat runs. Single-run kappa is known to wobble (0.91
vs 1.00 on the same cell in the earlier project). Every judge is first validated on a small
golden cell before its scores count.

### 4.3 Rules carried from the earlier eval work

- The judge must differ from the model under test (held-out rule).
- The pipeline under test always runs on Token Factory; only the judges vary.
- Keep the backend fixed within a comparison (CLI vs API of the same model disagreed).
- Rubric fingerprint in the cache key, so a rubric edit invalidates cached scores.
- A deterministic mock run with a frozen baseline is the offline regression test.

### 4.4 Tooling

LangSmith datasets hold cases; each config (which VLM, which recommend model, prompt
version, twin evidence tier, Tavily on/off) is one experiment over the same cases.
Comparing implementation branches is comparing experiments. Toloka labels and human
outcome taps come back as feedback rows.

**Backtesting.** Open-Meteo's Previous Runs archive gives the forecast as it was issued
1-7 days earlier, so for any past case the twin can be run on what we *would* have known
that day and scored against what actually happened. This turns every outcome photo into a
forecast-skill measurement, not just a label.

## 5. The twin: proactive risk forecasting

The twin is a set of small pluggable risk models. Each takes weather features and species
thresholds and returns a daily probability for the next 14 days under each action branch.

### 5.1 Risks and their rules (published thresholds)

| Risk | Driver | Rule source |
| --- | --- | --- |
| Water stress | bucket water balance in mm over the pot's surface area: + rain (mm, × a cover factor 0-1 for pots under cover) + watering (ml ÷ pot area) − ET0 (mm) × Kc; substrate depth and water-holding capacity (default 0.15 m, 40% by volume) turn mm into volumetric content; irrigation trigger ~0.25 m³/m³ for basil. Kc per herb from FAO-56 Table 12 ("mint" 0.60-1.15; herbs default to "small vegetables" 0.70-1.05) until the knowledge pack supplies a better value | FAO-56 (Allen et al. 1998); container-herb trials (Currey 2019); basil set-point study |
| Frost / cold | forecast minimum vs species threshold; pots treated as 2-3 °C less hardy than in-ground figures (roots are exposed; stated as an assumption, not sourced) | basil chilling injury 7.5-10 °C, severe at ≤5 °C, blackened at 0 °C (PMC 2023) |
| Fungal: basil downy mildew | ≥4 h leaf wetness (this risk uses the stricter RH ≥95% from the source paper) for infection; ≥7.5 h dark at RH ≥95% for sporulation, optimum 18-20 °C | Cohen 2017, UMass, Rutgers/Cornell |
| Fungal: grey mould | RH >90% or wetness ≥6 h at 15-21 °C; outbreak when weekly wetness >7 h/day and >9.5 night hours at 9-21 °C | UC IPM; greenhouse rule |
| Fungal: mint powdery mildew | 20-30 °C, warm days, cool nights, high RH or shade; dies above ~32 °C | UC IPM (qualitative) |
| Heat / light | hours above species heat threshold; daylight hours and direct-sun hours from pvlib with the garden's horizon | pvlib; extension guidance |
| Bolting | coriander: daylength >12-14 h or >24 °C; parsley: cold spell then long days | OSU extension |
| Growth stall | growing degree days and daylength; AquaCrop biomass | AquaCrop-OSPy |
| Pests: aphids, slugs | weather rule × "seen near you" modifier. Slugs: active 3-20 °C, peak ~18 °C, wet soil, recent rain. Aphids: development above ~4-6.5 °C, ~430 degree-days per generation. Modifier: iNaturalist / NBN Atlas / GBIF research-grade observations of the pest taxon within 20 km in the last 14 days, normalised by total insect records (observer effort), vs the same fortnight in earlier years | Rothamsted slug papers; aphid thermal-sum literature; citizen-science APIs (called live 2026-10-02, no key) |

**Leaf wetness proxy.** No sensor, so: an hour is "wet" when RH ≥ 90% (correct 87-92% of
the time against sensors; Sentelhas 2008), or dew-point depression < 2 °C, or a rain gauge
hit. This is the general proxy (grey mould, powdery mildew); basil downy mildew keeps the
RH ≥95% threshold its source specifies. Wet hours per day come from the Netatmo median, falling back to Open-Meteo.

**Season and frost context.** Open-Meteo's archive (ERA5, 1940+) gives growing degree days,
frost days, and daylength for this year against a 1991-2020 baseline, so "this autumn is
running warm/cold" is a computed signal. London first autumn frost (tmin ≤ 0 °C at the
grid point, 1991-2024, own computation from that archive, grid runs warmer than a station):
P10 21 Oct, P50 14 Nov, P90 2 Dec. Met Office Kew averages agree (air-frost days: Oct 1.0,
Nov 5.3, Dec 9.9). The P10 date falls inside the hackathon window, so basil frost risk is
a live demo scenario, not a hypothetical. iNaturalist phenology histograms (flowering,
budding, fruiting by month and place) give observed timing for bolting checks.

### 5.2 Evidence tiers (same pipeline, three evidence sources)

- **Tier 1: rules.** The published thresholds above. Always available.
- **Tier 2: physics simulator surrogate.** AquaCrop-OSPy with the published basil water
  productivity (WP* 18.1 g/m²) and a shallow 0.15-0.2 m "pot" soil, run thousands of times
  across weather and watering policies; a small surrogate model fitted to those runs;
  sanity-checked against the container-herb trial and the greenhouse-challenge curves
  (lettuce, tomato: shape only, never training); calibrated on Kash's outcome photos. This
  is sim-to-real and the honest "world model" claim.
- **Tier 3: generative world model.** Cosmos (or a diffusion model) renders a predicted
  state image. Visualisation only; its trust score is shown honestly low. Direction, not
  claim.

Rule: a tier is shown only if it produced a real output. Tier 3 renders "not available"
rather than a mocked answer. The UI shows what each tier says side by side; judges score
each; the user taps which turned out right when the next photo arrives. Those taps feed
judge calibration now, surrogate calibration in week 3, and tier 3 fine-tuning later.

### 5.3 Branching

- **Action branching.** Six actions: water now, water lightly, move to shade, move to sun,
  bring indoors, do nothing. One decision at day 0, then a hold policy ("water again when
  the bucket drops below X"). Each move changes the environment the twin sees, with fixed
  v1 assumptions marked as such: **indoors** = Tmin 16 °C, ET0 × 0.5, no rain, light at
  30% of outdoor; **shade** = direct-sun hours 0, ET0 × 0.7, Tmax − 3 °C; **sun** = the
  garden's full horizon profile. Horizon 14 days. 200 Monte Carlo samples per branch, drawing
  species thresholds and today's moisture from their uncertainty ranges. Output: per
  branch, per risk, per day, a probability; summarised as better / same / worse vs do
  nothing. The recommend stage reasons over this table.
- **Implementation branching.** Every variant is a config and one LangSmith experiment
  (section 4.4).
- **Multi-step sequences** are explored by the harness through the fast simulator, not
  shown in the UI.

### 5.4 Photo as a sensor

A photo shows the soil surface only, which dries first; the plant's leaves respond to
root-zone water. So leaf cues (droop, curl, dullness) outweigh soil cues, and both only
nudge the twin's water estimate. The UI shows the estimate next to what the photo said.
One case where they disagree is the limitation example in the write-up.

### 5.5 Out of scope

Learned dynamics trained directly on real transitions (tens of samples by the deadline:
would fit noise); generative images as dynamics truth; nutrients; pruning; repotting.

### 5.6 Testing

The twin is pure functions: property tests (water never negative; more ET0 means drier;
colder nights raise frost risk monotonically) plus one worked example by hand per risk.

## 6. Learning modules (each bounded, each with a measurable output)

| Module | Credit / tool | Output |
| --- | --- | --- |
| Local vs cloud | M4 Max via MLX/Ollama vs Token Factory | table: latency, cost, kappa for the same VLM and judge |
| Tavily research agent | Tavily | species knowledge packs with sources; one agentic loop |
| Judge calibration | Token Factory + Toloka + LangSmith | kappa table with CIs per judge per rubric line |
| Serverless hosting | Nebius AI Cloud | public demo URL, uptime to 15 Dec |
| Batch eval | Token Factory batch inference (half price) | eval runs over the case set |
| Fine-tune (stretch) | Token Factory LoRA | a judge or observe model tuned on the gold set |
| Cosmos (stretch) | Nebius DevPod + NGC container | tier 3 visualisation |
| Voice (last) | ElevenLabs | spoken recommendation |

## 7. Build order

1. **Data + risk gate** (days 1-2): repo scaffold, adapters, `/v1/models`, VLM gate, case
   ingest from EXIF, friction log.
2. **Core loop** (week 1): observe, environment, research, bucket twin v1, recommend, web
   page, JSON endpoint, tracing, offline tests, deploy.
3. **Eval** (week 2): rubric, judges, kappa with CIs, mock baseline, HTML report, LangSmith
   experiments, Toloka task designed and sent.
4. **Twin v2** (week 2-3): risk models with published thresholds, AquaCrop surrogate (tier
   2), action branching, evidence tiers in the UI, outcome-photo loop.
5. **Modules** (week 3): local vs cloud, batch eval, Toloka results folded in, serverless
   hardening.
6. **Submission** (week 4): curated repo, README, video, feedback write-up, name. Cosmos and
   voice only if everything above is green.

Riskiest unknown, gated first: whether any listed VLM can see herb condition at all.

## 8. Testing strategy

- Unit tests per stage against recorded provider responses (scripted adapter pattern from
  the earlier project); the suite runs offline in seconds.
- One integration test hits real Token Factory on a fixture photo. It is opt-in (pytest
  marker, skipped without `HERBTWIN_NEBIUS_API_KEY`), run manually before a PR; the offline
  suite is what pre-push runs.
- Deterministic mock run with a frozen baseline guards the eval harness.
- Every behaviour change lands with a test that fails without it.

## 9. Open questions

- Is Nemotron 3 Nano Omni listed on Token Factory? (Risk gate step 1.)
- Are FLUX schnell / SDXL still served? (Decides the cheapest tier 3.)
- Does the Serverless Endpoint accept an arbitrary FastAPI container with auth off? (Check
  during deploy; fallback is any outside host calling Token Factory.)
- The household's watering dates before 2026-10-02.
- Does Netatmo's public-data endpoint work with an app token and no owned device? (A forum
  thread says a user token is needed.) It returns latest readings only, so 14-day history
  means polling and storing. If either blocks, Environment Agency gauges + Open-Meteo only.
- Does Perenual's free tier cover the six herbs (species ids under 3000)? If not, Tavily
  alone.
- Is the EA LiDAR DSM tile for the garden worth the setup, or is a time-of-day photo series
  enough for the horizon profile in v1? (Default: photo series in v1, LiDAR in week 3.)

## Appendix A: sources found so far

### Hackathon
- Devpost page and Official Rules: https://nebiusglobalaihackathon.devpost.com/

### Token Factory and Nebius AI Cloud
- Model catalog: https://tokenfactory.nebius.com/model-catalog.md
- Nemotron on Token Factory: https://nebius.com/services/token-factory/nemotron
- Vision API example: https://docs.tokenfactory.nebius.com/api-reference/examples/vision-capabilities.md
- Image generation: https://docs.tokenfactory.nebius.com/api-reference/examples/image-generation.md
- Batch inference: https://docs.tokenfactory.nebius.com/data-lab/batch-inference
- Embeddings: https://docs.tokenfactory.nebius.com/api-reference/inference/create-embeddings.md
- Fine-tuning: https://docs.tokenfactory.nebius.com/post-training/how-to-fine-tune.md
- Docs index: https://docs.tokenfactory.nebius.com/llms.txt
- Serverless overview: https://docs.nebius.com/serverless/overview
- Serverless endpoints quickstart: https://docs.nebius.com/serverless/quickstart/endpoints
- Serverless jobs: https://docs.nebius.com/serverless/jobs/manage
- Serverless cookbook: https://github.com/nebius/serverless-ai-cookbook
- Physical AI repo (Cosmos guidance): https://github.com/nebius/nebius-physical-ai
- Cosmos 3 Reasoner hackathon note: https://github.com/nebius/nebius-physical-ai/blob/main/docs/hackathon-cosmos3-reasoner.md

### Plant identification and stress from photos
- AgEval benchmark: https://arxiv.org/html/2407.19617v1
- AgroBench (ICCV 2025): https://arxiv.org/abs/2507.20519
- LLM over-diagnosis study (MDPI 2025): https://doi.org/10.3390/su172310466
- Nemotron Nano 12B v2 VL: https://huggingface.co/nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16
- Nemotron 3 Nano Omni: https://huggingface.co/blog/nvidia/nemotron-3-nano-omni-multimodal-intelligence
- NeMo Data Designer crop-disease recipe: https://docs.nvidia.com/nemo/datadesigner/recipes/image-generation/crop-disease-detection-images
- Lab-to-field accuracy drop review: https://pmc.ncbi.nlm.nih.gov/articles/PMC13236948/
- Pl@ntNet-300K: https://github.com/plantnet/PlantNet-300K
- Pl@ntNet identify API: https://my.plantnet.org/doc/api/identify
- Herb classification (Kaggle): https://www.kaggle.com/datasets/ai4a-lab/herb-plant-classification-dataset
- Herb dataset (Mendeley): https://data.mendeley.com/datasets/fmpf798zcn/1
- Soybean leaf wilt classification: https://github.com/ARoS-NCSU/Soybean-Leaf-Wilt-Classification
- Soybean wilting MIL paper: https://doi.org/10.3390/agriculture15060614
- HortNet417v1 (potted peach wilting): https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8659954/
- Cosmos-Reason2-8B: https://huggingface.co/nvidia/Cosmos-Reason2-8B

### Soil moisture and water status from images
- Surface moisture from phone photos (PLOS ONE 2026): https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0341904
- Across soil types (R² 0.78): https://www.sciencedirect.com/science/article/abs/pii/S2352938525002083
- Leaf-movement water stress from time-lapse: https://arxiv.org/abs/2512.11605

### Twin tooling
- pyfao56: https://github.com/kthorp/pyfao56
- pyet: https://github.com/pyet-org/pyet
- PyETo: https://github.com/woodcrafty/PyETo
- AquaCrop-OSPy: https://aquacropos.github.io/aquacrop/
- AquaCrop basil parameters: https://www.researchgate.net/publication/342987630_Performance_Evaluation_of_AquaCrop_Model_in_Simulating_Basil_Ocimum_basilicum_L_Growth_under_Different_Soil_Fertility_Stress_in_Controlled_Greenhouse_Conditions
- AquaCrop sensitivity (WP*, KcTr): https://doi.org/10.1080/01904167.2023.2280142
- SIMPLE crop model: https://www.sciencedirect.com/science/article/abs/pii/S1161030118304234
- Container nursery ET scheduling: https://www.researchgate.net/publication/257417812_Substrate_water_status_and_evapotranspiration_irrigation_scheduling_in_heterogenous_container_nursery_crops
- Container herb water-content trial (Currey 2019): https://doi.org/10.3390/agronomy9110667
- Basil irrigation set-point study: https://www.researchgate.net/publication/323643016_Sensor-based_irrigation_management_of_soilless_basil_using_a_new_smart_irrigation_system_Effects_of_set-point_on_plant_physiological_responses_and_crop_performance
- Open-Meteo UKMO model: https://open-meteo.com/en/docs/ukmo-api
- Open-Meteo Python client: https://github.com/open-meteo/python-requests
- pvlib horizon shading: https://pvlib-python.readthedocs.io/en/stable/gallery/shading/plot_simple_irradiance_adjustment_for_horizon_shading.html
- Hemispherical photography: https://en.wikipedia.org/wiki/Hemispherical_photography
- Garden sunlight assessment (Alabama Extension): https://www.aces.edu/blog/topics/landscaping/how-much-sun-do-i-get-guide-to-sunlight-assessment-in-the-garden/

### Disease, cold, and bolting rules
- Basil downy mildew biology (Cohen 2017): https://apsjournals.apsnet.org/doi/10.1094/PHYTO-01-17-0017-FI
- Basil downy mildew fact sheet (UMass): https://www.umass.edu/agriculture-food-environment/vegetable/fact-sheets/basil-downy-mildew
- Basil downy mildew management review: https://apsjournals.apsnet.org/doi/10.1094/PHP-02-21-0041-FI
- Botrytis (UC IPM): https://ipm.ucanr.edu/home-and-landscape/botrytis-blight-or-gray-mold/
- Greenhouse Botrytis outbreak rule: https://www.sciencedirect.com/science/article/abs/pii/0261219494901589
- Powdery mildew (UC IPM): https://ipm.ucanr.edu/home-and-landscape/powdery-mildew-on-ornamentals/
- Mint rust (RHS): https://www.rhs.org.uk/disease/mint-rust
- Hutton criteria: https://www.ipmdecisions.net/documents/factsheet-hutton-criteria-late-blight-model/
- Basil chilling injury: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10352081/
- Coriander bolting (OSU): https://extension.oregonstate.edu/news/how-grow-cilantro-leaves-or-coriander-seeds

### Time-series and phenotyping datasets
- Autonomous Greenhouse Challenge 1 (cucumber): https://data.4tu.nl/articles/_/12717758/1
- Autonomous Greenhouse Challenge 2 (tomato, Kaggle mirror): https://www.kaggle.com/datasets/piantic/autonomous-greenhouse-challengeagc-2nd-2019
- Autonomous Greenhouse Challenge 3 (lettuce, RGB-D): https://data.4tu.nl/articles/_/21960932/1
- Autonomous Greenhouse Challenge 4 (dwarf tomato): https://data.4tu.nl/datasets/fa102772-32db-4b30-bace-12f2016722ce/1
- IPK barley drought time-lapse: https://zenodo.org/records/4932327
- Open Plant Phenotyping Database: https://vision.eng.au.dk/open-plant-phenotyping-database/
- CVPPP Arabidopsis: http://www.plant-phenotyping.org/CVPPP2014-dataset
- TERRA-REF: https://terraref.org/data/access-data.html
- Hydroponic Thai basil (Mendeley): https://data.mendeley.com/datasets/vx4jy7wyvd/1
- Basil yield on IoT vertical farms: https://github.com/emnabouzid13/Machine_Learning_Based_Basil_Yield_Prediction_in-IoT_Enabled_Indoor_Vertical_Hydroponic_Farms
- IoT Agriculture 2024 (Kaggle, low provenance): https://www.kaggle.com/datasets/wisam1985/iot-agriculture-2024
- iNaturalist phenology annotations: https://forum.inaturalist.org/t/download-plant-phenology-annotations/6528
- Nature's Calendar (not sharing data currently): https://naturescalendar.woodlandtrust.org.uk/
- LettuceVisSim: https://arxiv.org/pdf/2609.12505

### Synthetic images
- LesionDiff: https://www.sciopen.com/article/10.1016/j.cj.2026.01.011
- Diffusion augmentation review: https://arxiv.org/html/2507.18376v1
- Cosmos-Predict2.5: https://github.com/nvidia-cosmos/cosmos-predict2.5
- Cosmos cookbook: https://nvidia-cosmos.github.io/cosmos-cookbook/index.html
- Aigen case study: https://www.nvidia.com/en-us/case-studies/aigen/

### LLM-as-judge
- Expert vs LLM judge agreement: https://arxiv.org/abs/2410.20266
- farmer.chat eval (no human agreement reported): https://arxiv.org/html/2603.03294v2
- Judge's Verdict: https://openreview.net/forum?id=jVyUlri4Rw
- Trust or Escalate (ICLR 2025): https://proceedings.iclr.cc/paper_files/paper/2025/file/08dabd5345b37fffcbe335bd578b15a0-Paper-Conference.pdf

### Comparable products and projects
- Greg: https://greg.app/support/
- PlantWhisperer (CHI 2026): https://arxiv.org/abs/2603.00598
- PlantNeeds: https://github.com/dragonsterm/PlantNeeds
- PlantPilot: https://github.com/DavidGavilla/PlantPilot
- Plant-Pulse (mocked dashboard): https://github.com/Yashah01/Plant-Pulse and https://plant-pulse-dun.vercel.app/

### Additional environment and knowledge sources (fourth sweep)
- Open-Meteo Previous Runs API (archived forecasts, for backtesting): https://open-meteo.com/en/docs/previous-runs-api
- Open-Meteo Historical Forecast API: https://open-meteo.com/en/docs/historical-forecast-api
- Open-Meteo Air Quality API (UV index, CAMS pollen): https://open-meteo.com/en/docs/air-quality-api
- Met Office Weather DataHub (UK site-specific forecasts, free tier ~360 calls/day): https://datahub.metoffice.gov.uk
- Copernicus CDS, ERA5-Land (hourly reanalysis, 9 km, 1950+): https://cds.climate.copernicus.eu
- NASA POWER (daily solar and ET, coarse grid): https://power.larc.nasa.gov/docs/tutorials/service-data-request/api/
- Meteostat (nearby-station observations): https://dev.meteostat.net
- EA LiDAR Composite DTM/DSM 1 m, OGL: https://environment.data.gov.uk/survey
- Google Solar API (shade layers; paid, UK garden coverage unconfirmed): https://developers.google.com/maps/documentation/solar/overview
- SoilGrids (low value for pots): https://docs.isric.org/globaldata/soilgrids/
- Perenual plant API (structured care fields; free 300 calls/day): https://perenual.com/docs/api
- Permapeople API: https://permapeople.org/knowledgebase/api-docs/
- Kew POWO API (taxonomy only): https://powo.science.kew.org/api/2/
- GBIF API (UK occurrence, phenology): https://www.gbif.org/developer/summary
- PEP725 pan-European phenology: https://pep725.eu
- Trefle (status unreliable in 2026): https://trefle.io
- OpenFarm (shut down 2025; do not use): https://github.com/openfarmcc/OpenFarm
- Mint leaves dataset (fresh/dried/spoiled): https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10641137/
- Herbs and Plants dataset, 15k images, 22 species (commercial, unverified): https://datarade.ai/data-products/herbs-plants-dataset-15k-images-for-botanical-recognitio-oort
- Basil hyperspectral drought study: https://www.sciencedirect.com/science/article/pii/S2772375526005551
- Lettuce drought RGB dataset: https://doi.org/10.3390/app16178439
- Garden plants RGB drought classification (10 species, 6,000 images): https://pmc.ncbi.nlm.nih.gov/articles/PMC13341794/
- NemoClaw: https://github.com/NVIDIA/NemoClaw
- Hermes Agent + NemoClaw blog: https://developer.nvidia.com/blog/deploy-self-evolving-agents-for-faster-more-secure-research-with-a-hermes-agent-and-nvidia-nemoclaw/
- NeMo Agent Toolkit (profiling and evaluating agents): https://github.com/NVIDIA/NeMo-Agent-Toolkit
- Cosmos Reason2-8B on build.nvidia.com (free dev API, NIM): https://build.nvidia.com/nvidia/cosmos-reason2-8b
- Nemotron Nano 12B v2 VL on build.nvidia.com: https://build.nvidia.com/nvidia/nemotron-nano-12b-v2-vl

### Gap-filling sweep (replacements for the dead ends)
Plant-care data:
- OpenPlantDB (CC0, 294 plants, JSON/CSV/Postgres): https://github.com/cwfrazier1/openplantdb
- OpenFarm crops rescue (CC0, Wayback recovery, 340 crops): https://github.com/thefullnacho/openfarm-crops-rescue
- Indoor plant care dataset (Unlicense; light, temperature, humidity, watering): https://github.com/biologiste95/plant-dataset
- fronds (MIT, ~60 houseplants): https://github.com/timoneiro/fronds
- Wikidata SPARQL (taxonomy; hardiness property P8193, sparse): https://query.wikidata.org/
- PFAF (reference only: licence bars use in apps): https://pfaf.org/

Pest and disease signals:
- iNaturalist observations API (live-tested; Aphididae taxon 52381): https://api.inaturalist.org/v1/observations
- NBN Atlas records API (live-tested; radius in km): https://records-ws.nbnatlas.org/occurrences/search
- GBIF occurrence API (live-tested; Aphididae taxonKey 3042; bounding box): https://api.gbif.org/v1/occurrence/search
- Rothamsted Insect Survey aphid bulletin (weekly, no API): https://insectsurvey.com/aphid-bulletin
- IPM Decisions platform (open DSS models, CC BY 4.0): https://www.ipmdecisions.net/
- Fight Against Blight outbreaks API (potato only, pattern reference): https://blight.hutton.ac.uk/api/outbreaks?year=2026
- University of Worcester pollen and fungal spore forecasts (weekly web only): https://www.worc.ac.uk/pollen

Phenology and season:
- Open-Meteo archive API (ERA5 daily, 1940+; GDD, frost days, daylength): https://archive-api.open-meteo.com/v1/archive
- iNaturalist phenology histogram (term_id 12 = plant phenology; 13 flowering, 14 fruiting, 15 budding): https://api.inaturalist.org/v1/observations/histogram
- Met Office HadUK-Grid (station-grade gridded climate, OGL, CEDA account): https://www.metoffice.gov.uk/hadobs/hadukgrid/
- Met Office Kew 1991-2020 averages: https://www.metoffice.gov.uk/research/climate/maps-and-data/location-specific-long-term-averages/gcpuckhb6
- gardencalc.uk frost dates (Met Office derived): https://gardencalc.uk/

Hyperlocal weather:
- Netatmo public weather data API (OAuth app; crowdsourced stations): https://dev.netatmo.com/apidocumentation/weather
- Environment Agency flood-monitoring rainfall API (no key, OGL, 15-min): https://environment.data.gov.uk/flood-monitoring/doc/reference
- Met Office DataHub land observations (free tier 360 calls/day): https://datahub.metoffice.gov.uk
- openSenseMap API (keyless, bbox filter): https://api.opensensemap.org/boxes
- Breathe London developers (AQMesh pods, temp/humidity as side channels): https://www.breathelondon.org/developers
- Leaf wetness from RH (Sentelhas 2008, Agricultural and Forest Meteorology): https://doi.org/10.1016/j.agrformet.2007.09.011

Dead ends (do not retry): OpenFarm (shut 2025), Trefle (status unreliable), Nature's
Calendar (not sharing), Weather Underground PWS (station owners only), Met Office WOW
(being retired 2026), PFAF (licence bars app use), Rothamsted online database (private,
ends 2022), Open-Meteo CAMS pollen as a mould proxy (no spores).

### Reusable code (local)
- An earlier eval project: adapters, judge provider table, kappa + bootstrap CIs, judge cache
  and stability sweep, sqlite trace store with sink seam, baseline freeze, HTML report,
  scripted-adapter test pattern; also a compact eval gate and a contract-JSON export idea.
