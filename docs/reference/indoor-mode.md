# Indoor mode: variables, light from a phone, and the least a user must tell us

Research for a second mode of the app: plants kept indoors. Swept 3 Oct 2026 by direct
fetch (search interfaces were mostly rate-limited). Items marked **[unverified]** come
from general knowledge and were not fetched; items marked **[inferred]** are arithmetic
on fetched numbers. The outdoor mode stays the main case.

## 1. What changes indoors

| Matters less | Matters more |
|---|---|
| rain, wind, weather-driven evapotranspiration | light class at the plant's spot |
| frost | drainage and standing water |
| foliar fungal disease (homes are dry and leaves stay dry) | overwatering and root rot |
| slugs | fungus gnats, spider mites, mealybug, salt build-up |

The user is the plant's only water source and the plant uses little water, so **the twin
should weight "too wet" above "too dry" indoors.** No validated houseplant watering
recommender or indoor plant twin was found in the literature; CrossRef returned only
sensor build papers without plant-science validation.

## 2. Variables

| Variable | Why it matters | Typical indoor value | Lowest-effort capture | Source |
|---|---|---|---|---|
| Light at the plant | main driver of indoor water use and growth; every species used more water at 150 than at 75 foot-candles | low 270 to 1,080 lux, medium to 5,400, high to 10,800, direct sun above; a north sill can be about 2,150 lux on a clear winter day | the photo's exposure data (section 3), plus window direction and distance | UMD Lighting for Indoor Plants; UGA B1318; Conover and Poole 1992 |
| Water use per leaf area | sets how fast the pot empties | 1.4 to 4.8 mL per cm² of leaf over 6 months at 75 to 150 fc; about 0.08 to 0.26 L per m² of leaf a day, so **15 to 50 mL a day for 0.2 m² of leaf** [inferred] | plant size from the photo; species class | Conover and Poole 1992, J Environ Hort 10(2):11, doi:10.24266/0738-2898-10.2.11 |
| Species and leaf type | cuticular loss was 43 to 80% of transpiration at low light; about a 3× spread across genera | coleus high; ficus, peperomia, pothos low | photo identification | Rajapakse et al. 1988, JASHS 113:910 |
| Air temperature | sets vapour pressure deficit; chilling risk | living room 18.6 °C (Dec) to 21.5 °C (Aug); bedroom 17.8 to 21.7 °C; 26% of living rooms below 18 °C in the heating season | default by month | BRE/DECC Energy Follow-Up Survey 2011, Report 2 (823 English homes) |
| Humidity | ET was higher at 25% than at 60% RH at 20 °C | UK winter about 40 to 60% [unverified]; about 1.0 kPa VPD at 19 °C and 55% [inferred] | default; ask "near a radiator?" | Kerschen et al. 2016, HortTechnology, doi:10.21273/horttech03473-16; UGA B1318 |
| Air movement | minor indoors; draughts and heat registers stress plants | near still | fold into the radiator question | UMD Temperature and Humidity for Indoor Plants |
| Pot material and size | clay loses water through its walls; a large plant in a small pot dries faster | n/a | photo | Clemson HGIC Indoor Plants: Watering |
| Drainage, saucer, cache pot | standing water causes root rot and salt build-up | n/a | one question | UGA B1318; Clemson HGIC |
| Substrate moisture | the state variable | sensor bands: basil 28 to 75%, pothos 15 to 60% (vendor data) | **finger test** | MiFloraDB |
| Night and windowsill temperature | chilling injury in tropicals below 10 °C; basil must not sit on winter sills | a sill behind curtains runs several °C below the room [unverified] | ask "on the sill behind curtains at night?" | NC State Extension Gardener Handbook ch. 18; Penn State Growing Herbs Indoors |

No fetched study compares indoor and outdoor ET for the same plant. The rates above imply
well under 1 mm a day on a pot-area basis, against several mm a day outdoors in summer
[inferred].

## 3. Light from the phone photo

**The photo is the light meter.** A camera chooses exposure from the light in the scene,
and it records that choice in the file.

- Exposure value at ISO 100: EV100 = log2(N² / t) − log2(ISO / 100), with N the f-number and t the exposure time.
- Illuminance estimate: E ≈ 2.5 × 2^EV100 lux (incident-light meter constant C = 250). EV 15 is about 82,000 lux. en.wikipedia.org/wiki/Exposure_value, /wiki/Light_meter
- A phone photo meters **reflected** light, so scene reflectance enters directly: the formula is only an estimate and fails for unusual scenes.
- Plant light: PPFD = lux × 0.0185 for sunlight (54 lux per µmol m⁻² s⁻¹); cool-white fluorescent is 0.0135. apogeeinstruments.com/conversion-ppfd-to-lux/
- Daily light: DLI = mean PPFD × 3600 × hours / 10⁶. Example: 2,000 lux averaged over 10 h is 37 µmol and 1.3 mol m⁻² d⁻¹.

**Checked on our own data (3 Oct 2026, one-off script, not in the repo).** All 55 garden photos carry `ExposureTime`,
`FNumber`, `ISO` and `BrightnessValue`. The estimate tracks the day on 2 October:

| Hour | Median estimated lux |
|---|---|
| 10 | 11,200 |
| 12 | 41,100 |
| 14 | 23,400 |
| 15 | 3,600 |
| 17 | 2,900 |
| 18 (dusk) | 100 |

Range across all photos: 81 to 215,000 lux. None of the 55 carries a compass direction
(`GPSImgDirection`), so window or wall orientation cannot be read from these files.

**Expected error of the lux estimate**

| Method | Error | Source |
|---|---|---|
| plain scene photo (what we get for free) | a factor of 2 to 3: unknown reflectance, metering mode, HDR | estimate |
| white paper filling the frame at the plant's spot | about ±30 to 50% | estimate; the method is UGA B1318's camera-as-meter table (f/2 = 40 fc, f/4 = 150, f/8 = 600, f/16 = 2,400 fc at ASA 25, 1/60 s), which checks out against the physics |
| front camera with a paper diffuser (Photone) | about ±12% plus up to 10% cosine error | vendor, growlightmeter.com |
| phone ambient light sensor | slope 0.88 against a spectroradiometer over 0.1 to 10⁵ lux, R² 0.98 | doi:10.3390/clockssleep4040045 |

Light classes are about 4× wide, so a factor-of-2 estimate still lands in the right class
most of the time. **A spot reading to a daily total is the weak step:** overcast against
direct sun differs by 10× or more, so expect class-level accuracy only. No published
method estimates indoor DLI from one or a few spot readings, and no study says how few
readings characterise a spot.

A 2026 dataset of 5,814 phone photos with lux-meter ground truth needed fixed ISO 50 and
1/50 s exposure (doi:10.1016/j.dib.2026.113134): pixel values alone do not give lux; the
exposure metadata is what carries it.

## 4. Indoor light models

- **Daylight factor:** indoor illuminance as a percentage of outdoor under an overcast sky. Average under 2% is not adequately lit, over 5% is well lit (CIBSE LG10). en.wikipedia.org/wiki/Daylight_factor
- **Falloff from a window** in a typical side-lit room: about 10 to 15% at 0.5 m, 5 to 8% at 1 m, 2 to 3% at 2 m, about 1% at 3 m [unverified textbook values]. Under a 10,000 lux overcast sky: roughly 1,000+, 600, 250 and 100 lux.
- **Distance rule:** even low-light plants usually get too little light more than 3 m (10 ft) from an average window. extension.missouri.edu/publications/g6515
- **Orientation:** south brightest; east and west suit medium-light plants; north suits low-light only. An east window in direct sun reaches 5,000 to 8,000 fc; a south window under wide eaves behaves like north in summer (UGA B1318).
- **Glazing and curtains:** visible transmittance below 0.4 halves the light or worse; clear double glazing about 0.7 to 0.8, net curtains cut 30 to 50% [unverified].
- **Season at 51° N:** outdoor DLI about 3 to 5 mol m⁻² d⁻¹ in December and 35 to 40 in June, so a room interior at 1 to 2% daylight factor gets under 0.1 in winter and under 1 in summer [inferred, unverified inputs].
- **Winter rule of thumb:** assume every window drops one light class from October to February [inferred from UGA's seasonal notes].

**Extension light classes disagree by 2 to 4×.** Pick one table and cite it:

| Source | Low | Medium | High |
|---|---|---|---|
| Missouri G6515 | 50 to 250 fc (540 to 2,700 lux) | 250 to 1,000 fc | over 1,000 fc (10,800 lux) |
| Maryland | 25 to 100 fc, north | 100 to 500 fc, east or west | 500 to 1,000 fc, south; over 1,000 fc = 4 to 6 h direct sun |
| UGA B1318 | 25 to 75 fc | 75 to 200 fc | over 200 fc; "sunny" = at least 4 h direct sun |

Minnesota's page contradicts itself between its foot-candle and PPF figures; do not reuse it.

## 5. What vision can and cannot do

- **Single-image lighting estimation** gives relative lighting, not absolute: Gardner et al. 2017 (arXiv:1704.00090), Garon et al. 2019 (arXiv:1906.03799), DiffusionLight 2023 (arXiv:2312.09168). The first photometrically calibrated indoor HDR dataset is from 2023 (arXiv:2304.12372). Absolute lux still needs exposure metadata.
- **Sky view and openness from a phone:** hemispherical phone photos give canopy openness with RMSE about 0.04 (doi:10.1101/2021.03.17.435793); street-view sky view factor correlates at r 0.86 to 0.99 with 3D models (doi:10.3390/rs9050411). This is what the "phone pointed straight up from the pot" shot is for.
- **Compass:** indoor phone headings are typically 10 to 30° off near steel and electronics [unverified]. Good enough for north, east, south, west; not for eight points.
- **Free in the file when present:** timestamp, GPS, compass direction, exposure, ISO, brightness value. Browser uploads and messaging apps often strip them.
- **Not found:** any paper or app that estimates plant light from a photo of the room.
- **Cannot be inferred from a photo at all:** hours of direct sun and seasonal change; obstructions outside the frame; curtain, blind and grow-light habits; whether the photo was taken where the plant lives; anything absolute if the metadata was stripped.

## 6. How other products capture light

- Photone: front camera at the plant pointed at the light, paper diffuser over the lens; outputs PPFD and DLI.
- Planta: camera light meter held at the plant, returns a light class [unverified].
- Greg: asks window direction and distance, measures nothing [unverified].
- Xiaomi / HHCC Flower Care: a probe that logs lux continuously, so it gives a true daily total.

## 7. Indoor problems and their drivers

- **Overwatering and root rot:** named as the leading killer of potted plants; roots in water get no oxygen, and wilting can itself be a root-rot sign, so watering makes it worse (Clemson HGIC). Low light means slow drying (UMN).
- **Fungus gnats:** up to 200 eggs laid on moist media; larvae 1 to 2 weeks, pupae about 1 week (Wisconsin XHT1128). Adult emergence peaked at 56 to 68% media moisture and fell when drier or wetter (Cloyd and Dickinson 2008, HortScience 43:1528). Drying the compost kills larvae.
- **Oedema:** roots take up more water than leaves transpire; wet compost, humid air or both (RHS).
- **Spider mites:** thrive warm and dry; life cycle 55 days at 10 °C, 12 days at 21 °C (RHS). Second most common houseplant pest; mealybug is first (UGA B1318).
- **Foliar disease incl. powdery mildew:** chances minimal in homes because humidity is low and foliage stays dry (UGA). No indoor mildew threshold found.
- **Tip and margin browning:** soluble salts from fertiliser and saucers; leach monthly (UGA).
- **Cold damage:** below 10 °C for tropicals; symptoms can take weeks to appear (NC State).
- **Scorch:** too much direct light turns leaves pale then brown (UMD).
- **Low light:** leggy growth, older-leaf drop, fading (UMN, UMD); leaf drop on moving indoors eases after a few weeks.

## 8. Pots and substrate indoors

- Empty the saucer after watering; never let the pot stand in runoff (Clemson, UGA).
- Containers without holes suit only thirsty plants such as peace lily; double-pot decorative containers (UGA, NC State).
- Self-watering pots wick from a reservoir without waterlogging; Conover and Poole's rates were measured in these.
- Clay dries faster than plastic or glazed; fully dried peat is hard to rewet (Clemson).

## 9. Rules and thresholds in use

- **Finger rule:** insert a finger to the first joint (about 2.5 cm); water if dry at the tip. Clemson calls it the most accurate gauge but cites no trial.
- Water thoroughly until it drains, then empty the saucer.
- Moisture meters vary widely in accuracy and are affected by fertiliser and soil type (Clemson).
- Plant-monitor bands (vendor): basil 2,500 to 55,000 lux, 5 to 35 °C, air RH 30 to 80%, soil moisture 28 to 75%, conductivity 100 to 2,000 µS/cm.
- OpenPlantBook bands for our plants are in `data-profile.md`.

## 10. Culinary herbs indoors

- **Light:** herbs are "high light", a south or south-west window; most need 6 h of direct sun, or two 40 W fluorescents at 15 to 30 cm for 14 to 16 h. Rosemary, thyme and bay need full direct sun; chives and coriander tolerate 2 to 6 h (Penn State). Mint and parsley: treat as medium [unverified].
- **Basil:** controlled studies use about 13 mol m⁻² d⁻¹ (Eghbal et al. 2024, doi:10.1186/s12870-024-05637-w). A UK winter sill delivers perhaps 1 to 3 [unverified]. Fails below 10 °C; water in the morning because it hates wet roots overnight (RHS).
- **Temperature:** day 18 to 21 °C, night 13 to 16 °C (Penn State).
- **Water:** rosemary, thyme, sage and oregano should dry slightly between waterings.
- **Supermarket pots** fail within weeks from overcrowded sowings, low light and overwatering [unverified].

## 11. Capture design: the least a user must do

**Automatic, from every photo:** species, plant size, pot type and visible symptoms (vision
model); light level at capture (exposure data); time and date; location if present.

**Asked once per plant, three questions at most:**
1. Which way does the nearest window face, and how many steps from it is the plant?
2. Can water drain freely? Holes in the pot, and is it standing in water?
3. Is it by a radiator, or on a sill behind curtains at night?

**Asked at each check-in:** the finger test (dry, cool but not moist, damp, or wet). It
reads the surface layer; see `container-physics.md`.

**Optional upgrades, each cutting the light error:** one photo from the plant toward the
window (orientation, sky fraction, obstructions); a sheet of white paper at the plant; a
second photo at a different time of day.

**Fallback:** if the file has no exposure data (screenshot, messaging app), detect it and
ask the questions instead of guessing.

**Defaults for a UK home** (BRE/DECC survey): living room 20 °C in October, 19 °C in
November, 18.5 °C December to February, 21.5 °C in summer; bedrooms 0.5 to 1 °C cooler;
RH 50% in winter and 55 to 60% in autumn [unverified]; subtract 3 to 5 °C for a night
sill [unverified].

## 12. How the twin changes

The environment source becomes swappable. Outdoors it is the weather feed. Indoors it is a
**room profile**: light class from the photo's exposure plus window direction, distance
and month; temperature and humidity from seasonal defaults adjusted by the radiator and
sill answers; no rain and no frost. Water use scales with leaf area, light class and
species group (Conover and Poole), which is the nearest published model. The finger test
corrects the state at every check-in, because indoor water use is too small and variable
to trust a model alone.

The same exposure-based light estimate also works outdoors and adds a per-photo light
reading to the garden series for free.

## 13. Indoor ground-truth data that can be downloaded

The project owner has no indoor plants, so indoor ground truth must come from public
data. Checked through repository APIs on 3 Oct 2026 unless marked UNVERIFIED. Mendeley's
search API was failing and Roboflow was not searched.

**Phone photos with lux ground truth**

| Source | Size | What was measured | Licence | Fit |
|---|---|---|---|---|
| Buryi 2026, Controlled Smartphone Image Dataset for Workplace Illuminance Estimation (the Data in Brief set), Zenodo concept doi:10.5281/zenodo.20499311, v4 at zenodo.org/records/21514641 | 25 GB: 12 zips of about 2.1 GB, plus small CSVs | 5,814 JPEGs of indoor work surfaces; lux meter at centre or 5 points, 2 to 2,280 lux, median 598; one phone, fixed ISO 50, 1/50 s | CC BY 4.0 | **Cannot validate our exposure-based estimate**: exposure is locked, so it only tests pixel brightness to lux at fixed settings. The CSVs (`annotation_master_latest.csv`, `feature_master_latest.csv`) download without the zips. |
| Its analysis code, zenodo.org/records/20658590, github.com/buryianton/ai-lux-estimation | 8 MB | feature extraction, tree models | MIT | reusable baseline |
| Laval Photometric Indoor HDR (arXiv 2304.12372) | 2,362 HDR panoramas | absolute luminance, calibrated meter, DSLR | signed agreement, academic only, no redistribution | good physics reference, gated |
| Empa HDR Image Database, zenodo.org/records/7861544 | 18 GB, 33 scenes | exposure brackets; absolute calibration UNVERIFIED | CC BY 4.0 | weak |

**Indoor light measurements**

| Source | Size | What was measured | Licence | Fit |
|---|---|---|---|---|
| Kaggle tomassladcik/light-history | 1.5 MB | south-facing home interior, hobby light sensor, 2 Jul to 30 Aug 2026, with solar position | CC0 | **best home lux-by-time series**; one position |
| Irish Residential IEQ, dwelling H002, zenodo.org/records/20117957 | 18 MB | bedroom, kitchen, living room, Oct 2022 to Jul 2024: temperature, RH, CO2, light, motion | CC BY 4.0 | good; light units and sensor position UNVERIFIED |
| UCI Occupancy Detection (id 357) | 20,560 rows | office lux, temperature, RH, CO2, per minute | UNVERIFIED | office only |
| Spectral simulation evaluation, zenodo.org/records/13905298 | 388 MB | spectral irradiance and illuminance in two offices | CC BY 4.0 | niche |

Nothing gives lux by distance from a window across orientations in homes.

**Indoor plant condition images**

| Source | Size | Labels | Licence | Fit |
|---|---|---|---|---|
| Kaggle tarieretimitimi/houseplant-health-classification-dataset | 91 phone images | healthy 67, unhealthy 24 | CC BY-SA 4.0 | small, but the only set confirmed as real phone photos of houseplants in homes and nurseries |
| Kaggle gauravsaklani00/indoor-plant-leaf-health-dataset | 914 images | healthy / unhealthy | CC BY-SA 4.0 | coarse |
| Kaggle abdulahad0296/indoor-plant-disease-detection-dataset | 3.7 GB | disease classes: aloe, cacti, money, snake and spider plant | CC BY 4.0 | disease, not watering or light |
| Kaggle nikitamanaenkov/epipremnum-aureum-money-plant-leaf-image-dataset | 4,298 images | healthy vs unhealthy pothos | CC BY 4.0 | probably a mirror of the Mendeley set |
| Kaggle sanaeab/peace-lily-care-dataset | 4.4 MB | contents UNVERIFIED | ODbL | unknown |

No set labelled overwatered, underwatered, leggy or leaf drop exists on Kaggle, Zenodo
or Hugging Face.

**Sensor time series, water use, care tables**

- Kaggle andresaftari/moniflora-backup-rtdb (0.4 MB, MIT): a real Xiaomi Flower Care log (temperature, soil moisture, conductivity, lux) on a cherry tomato; waterings not marked. The only such log found.
- Kaggle souvikrana17/indoor-plant-health-and-growth-dataset looks synthetic. Do not use as truth.
- Indoor water use: no downloadable dataset. Rajapakse, Kelly, Reed 1988 (JASHS 113(6):910, doi:10.21273/jashs.113.6.910, CC BY-NC-ND) has transpiration of five potted species at 20 µmol, 25 °C, 75% RH in PDF tables that need hand transcription.
- github.com/vrachieru/plant-database: 5,539 species files from the HHCC / Mi Flora database (light and sensor ranges, care text). No licence; legally unclear. Use for comparison only.
- Plantfolio (CC BY-NC-SA) and the FloraDB sample (CC BY-NC) are already in the catalogue.

**What has no public data at all:** images labelled overwatered, underwatered, leggy or
leaf drop; lux by window distance and orientation in homes; houseplant sensor logs with
watering events; indoor pot weight-loss or dry-down series.

**Consequence.** Indoor mode can be grounded for light classes (extension tables, the two
home light series), species light needs (the Tichý indicator values, 8,909 taxa, in
`trait-databases.md`; the OpenPlantBook light bands in `data-profile.md`; the 100
houseplants of the FloraDB sample), room climate (the BRE/DECC Energy Follow-Up Survey
2011) and problem cues (the differential-diagnosis file), but its watering advice cannot
be validated against public data. Validation needs a real indoor plant with a finger test
log, or it ships labelled as lower-evidence.
