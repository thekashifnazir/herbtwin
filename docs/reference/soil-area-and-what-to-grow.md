# Soil, area and what to grow

What the app can know about a garden's soil, climate and "what could I grow here" from the
least user input: a photo, the location and the date. Gathered 11 to 12 Oct 2026 by nine
research agents and three cheap probes. Each claim carries an evidence tier (see
`risk-models.md`); "tested" means the call or run was made on that date.

## Headline

- **Location gives a good prior for native ground, nothing for a pot.** For the test
  garden (in England, outside London), four independent sources agreed on a clayey,
  slowly draining soil.
- **A photo gives the setting and the material, not the texture.** It reliably tells pot
  from bed and gives colour and organic matter. It never called a compost mineral soil,
  but it called 11% of mineral soils compost, and peat vs peat-free is a guess. It does
  not give sand/loam/clay, and that drives the growing advice: on 92 public photos it did
  worse than always answering "sandy loam" (section 6). Its texture confidence is only
  weakly calibrated, so always ask.
- **One question closes the gap:** the wet squeeze (ribbon) test. Ask a second question,
  "was this soil here already or brought in?", only when origin matters.
- **"What to grow" is feasible as filters over trait data plus a curated UK crop list with
  sow/plant months.** It is not feasible as a ranker over a large trait database alone.

## 1. Working out the soil type

### Order of evidence

| Setting | Step 1 (no user effort) | Step 2 (one tap) | Step 3 (optional) |
|---|---|---|---|
| Pot or trough | photo: compost vs soil, peat-free bark/fibre vs heavy loam-based vs light peat; signs of tired compost | "what did you fill it with, and when?" | none |
| Bed or open ground | location lookups (section 2) plus photo (colour, clods, cracks, stones, turf) | squeeze test: gritty / silky / sticky; does it ribbon? | vinegar fizz (lime); pH kit; drainage hole; lab lead test before food crops |

Map lookups are skipped for a pot: maps say nothing about it.

### Hand tests (what each buys)

| Test | Time | Tells you | Reliability |
|---|---|---|---|
| Feel/ribbon | 5 min | texture class | experts named the lab class 66% of the time (91% counting neighbouring classes); novices 27–41% (71–78% with neighbours) [A, Salley et al. 2018 SSSAJ] |
| Jar sedimentation | 48 h | sand/silt/clay split | dominant fraction only; the clay layer is hard to read [C, Clemson HGIC] |
| Drainage hole, ~30 cm | 1–2 days | drainage | under ~2.5 cm/h, or water standing after 12 h, means poor [C, UF/IFAS; Kentucky extension] |
| Vinegar fizz | 1 min | free lime/chalk | presence only [C, RHS soil types] |
| pH colour kit or handheld meter | 10 min | pH | kits and handheld meters reliable; cheap probe meters not [A/C, J. Extension 2001] |
| Red cabbage juice | 30 min | pH extremes only | clear change only below ~5.5 or above ~7.5 [D] |
| Worm count, 20 cm cube | 15 min | soil health, not type | ~16+ worms suggests good health; benchmark from secondary sources [C, AHDB] |

### Containers

- RHS for Mediterranean herbs: John Innes No 1 plus up to 25% coarse grit; John Innes No 3
  for bay [C, RHS herbs in containers].
- Telling composts apart [D]:
  - loam-based: heavy, visible mineral soil;
  - peat-free: bark or wood-fibre bits, can be dry on top and wet below;
  - peat: light, even, dark;
  - garden soil in a pot: dense, crusts.
- Tired compost: it shrinks from the wall, water runs down the sides, the rootball is
  light and dry, the surface crusts or mosses, roots circle [C, RHS; UC Master Gardeners].
  Peat mixes that dry out repel water; fix by bottom-watering [C].

### Urban and food-growing safety

- UK screening level for lead on allotments is 80 mg/kg. 98% of sampled Newcastle urban
  allotment soils exceeded it, yet most vegetables stayed under food limits. Leafy and
  root crops carry the most risk, tree fruit the least [A/C, Newcastle University 2019].
- A postal heavy-metal panel costs about £68. Test old urban ground before growing food.
  Bought compost in pots is low risk.
- BGS London Earth (about 6,400 London topsoil samples, lead included) is a paid licence;
  free element maps exist [C].

## 2. What the location tells us

All endpoints were tested on 11 Oct 2026, are free and need no key unless noted.

| Fact | Source and endpoint | Latency | Notes |
|---|---|---|---|
| Soil texture class, parent material, carbonate | **BGS Soil Parent Material Model 1 km**, local file (OGL) | <1 s | has values over London, unlike SoilGrids; needs a point-in-polygon lookup |
| Topsoil pH and bulk density | **UKCEH Countryside Survey 1 km**, local file (OGL) | <1 s | modelled for farmland classes, not gardens |
| Soil landscape class | Soilscapes via LandIS ArcGIS `.../Soilscapes_Cranfield/MapServer/identify` | ~0.1 s | "unclassified" over built-up London |
| Bedrock and superficial geology | BGS OGC API `collections/bgsgeology625k{bedrock,superficial}/items?bbox=` | ~0.2–0.7 s | 1:625k; small drift patches can be missing |
| Global soil grid | ISRIC SoilGrids `rest.isric.org/soilgrids/v2.0/properties/query` | 3–12 s | **null over built-up cells**; 90% range ~3–93% clay where it answers [A, Poggio 2021] |
| Frost dates, annual minimum, warmth so far this year | Open-Meteo archive `archive-api.open-meteo.com/v1/archive`, `models=era5_land` | ~0.4 s | fix the model when comparing years; the grid runs colder than town centres; for frost risk prefer the HadUK-Grid 1 km normals (section 6) |
| Soil temperature and moisture now | Open-Meteo forecast `soil_temperature_{0,6,18,54}cm`, `soil_moisture_*` | ~0.15 s | not yet wired into `stages/environment.py` |
| Wall sunlight by aspect | PVGIS `re.jrc.ec.europa.eu/api/v5_3/seriescalc`, `printhorizon` | ~1 s | horizon is terrain only, not buildings |
| Pests within 10 km | NBN Atlas `records-ws.nbnatlas.org/occurrences/search?...&radius=10` | ~0.2 s | counts reflect recording effort, not abundance |
| Flood areas | EA `environment.data.gov.uk/flood-monitoring/id/floodAreas?lat&long&dist` | ~0.8 s | |
| Air quality, pollen | Open-Meteo air-quality API | – | |
| Hosepipe ban | none (water-company pages) | – | needs a postcode-to-supplier lookup; check by hand |
| 1 km frost days, sunshine normals | Met Office HadUK-Grid on CEDA | – | **free CEDA login needed** to download files (tested: redirects to login); OGL. 1991–2020 normals fetched 12 Oct 2026 (section 6) |

Cautions:
- Open-Meteo `sunshine_duration` gives 2,737 h/yr for London against Kew's measured
  1,693 h (about 60% high). Use radiation fields or Met Office normals instead [C].
- 2026 is the warmest growing season on record, confirmed by Met Office observations
  (section 6). ERA5 and ERA5-Land put growing degree days (base 5 °C) to 5 Oct about 12%
  above 2018/2022/2025 at both test points.

### Worked examples

**Central London (generic point; ERA5 grid, which runs cold here: see section 6 for HadUK-Grid normals):**
- last spring frost median 6 Apr (1 year in 10 after 23 Apr);
- first autumn frost median 13 Nov (earliest 21 Oct);
- typical coldest night −4.7 °C;
- H4 plants survive normal winters;
- Kew 1,693 sunshine hours a year;
- Thames Group clay under terrace gravels.
Soil maps are null or unclassified over built-up cells [C].

**A UK test garden:** four sources agree.
- BGS parent material: loam to clay, medium-heavy, deep.
- Countryside Survey: pH 7.7.
- Soilscapes: slowly permeable, seasonally wet, loamy and clayey.
- SoilGrids: about clay loam, pH 6.2–6.6.
- Prior: deep clay loam over mudstone, wet in winter, pH about 6.5–7.7.
- Frost: last spring frost median 11 Apr, first autumn frost median 14 Nov, worst night
  −10.9 °C.

## 3. What a photo can and can't give (probe, 11 Oct 2026)

Setup:
- the observe model `zai-org/GLM-5.3-Flash` through the repo adapter;
- json_schema output, temperature 0, 1024 px, EXIF stripped;
- 6 garden photos (raised bed close-ups and wide shots, the whole garden, a pot), 3 runs
  each, plus a context variant and a `google/gemma-3-27b-it` comparison;
- 25 calls, about $0.025 total, median about 11 s per call.

| Reliable from a photo | Not reliable |
|---|---|
| setting (pot vs bed; one close-up misread as open ground until context was added) | texture class: clay loam 8, loam 3, sandy loam 1 across 12 bed runs; 2048 px changed the label, not its accuracy |
| bought compost vs mineral soil | origin (native vs imported): "garden soil" 11 of 12 |
| colour band (about 10YR 4/3–5/4 bed, 10YR 2/1 pot) | drainage, stoniness |
| organic matter high (compost) vs low–medium (soil) | peat-free vs peat (2 of 3) |
| structure: clods, freshly dug, turf turned in | moisture in wide shots |

Adding a line of context (country, month, "raised bed") fixed the setting and lowered organic matter.
It did not change texture or origin. Rule for the app: texture confidence below 0.5 means
"ask the squeeze question". Phone-camera Munsell colour reaches about 3.75 ΔE under
controlled light and is worse in daylight [A]. No usable UK labelled soil-photo dataset
exists (the Kaggle/Roboflow sets use Indian soil classes).

## 4. What to grow

### The data probe (11 Oct 2026)

A filter-and-score over 7,414 Practical Plants (PFAF-derived) species, with hardiness,
pH, shade, height and edibility filters. Its top 25 was checked against 15 RHS October
picks:
- Raw ranking found 1 of 15. It was full of junipers, weeds and unnamed species.
- With a plant-height cap and a "known crop" boost from the Plant Variety Database and
  EcoCrop food categories, it found 6–7 of 15 (genus-level match).
- Correct misses: blueberry (needs acid soil), tulips (not food).
- Real misses: rhubarb, peas, spring cabbage. No dataset carries UK sow and plant months.

What changes the list most:
- **shade**, then bed vs pot (size), then pH (only for acid-lovers);
- the `sun` field is useless (93% say full sun); `shade` is the one that discriminates.

Verdict:
- Data works as filters.
- Quality needs a curated list of about 150–250 UK-grown edibles, seeded from the Plant
  Variety Database species list (CC BY), with per-crop UK sow and plant month windows.

### RHS-sourced picks for mid-October, small space [C unless marked]

| Crop | Where | Harvest | Note |
|---|---|---|---|
| Garlic (softneck) | pot ≥25 cm deep or ground | Jun–Jul | needs cold; on wet clay start in modules |
| Broad bean 'Aquadulce Claudia' / 'The Sutton' | ground / pot ≥40 cm | from May | late Oct–Nov in mild areas |
| Pea shoots, microgreens | windowsill | 1–4 weeks | any time |
| Chives, mint (lift and pot a piece) | windowsill | all winter | autumn division |
| Lamb's lettuce, land cress, winter lettuce | pot ≥30 cm or ground | Nov–Mar | fleece in cold spells |
| Onion sets ('Radar') | container ≥45 cm or ground | Jun–Jul | avoid waterlogging clay |
| Round peas ('Meteor') | ground or wide pot | May–Jun [D] | mild areas |
| Spring cabbage plugs | pot or ground | Apr–Jun | firm soil; net against pigeons |
| Tulips | pot or ground | Apr–May | plant in November |
| Blueberry (compact) | pot, ericaceous compost | Jul–Sep | not on chalk or alkaline soil |
| Rhubarb crown | ground or pot ≥50 cm | spring 2028 | bare-root Nov–Mar; raised bed on heavy clay |

Corrections to common advice:
- Sage and rosemary cuttings are a late-spring or summer job; layering suits autumn.
- Strawberries are best planted in Aug–Sep.
- Spring cabbage is sown in July; buy plugs in autumn.
- Coriander sown in autumn needs cover.
- Oregano dying back in October is normal: a firm crown means it is dormant
  (`seasonal-norms.md`).

Soil type changes the picks:
- **Heavy clay:** suits broad beans, brassicas, mint, chives and rhubarb. Garlic, onions,
  strawberries and Mediterranean herbs need modules, raised beds or added grit.
- **Sandy:** suits Mediterranean herbs; add organic matter for beans and brassicas.
- **Chalky:** no blueberries.
- **Metal containers** get very cold in winter: wrap them and move them against a wall. H4
  herbs (rosemary, tarragon) are most at risk [C, RHS].

## 5. Data held, and licences

New, in `data/external/soil-and-crops/` (not in git; each folder has a README with
source, licence and fetch date):

| Set | Licence | Use |
|---|---|---|
| BGS Soil Parent Material Model 1 km | OGL | shippable soil prior |
| UKCEH Countryside Survey topsoil pH / bulk density 1 km | OGL | shippable pH prior |
| Practical Plants (PFAF-derived), 7,414 species | **treat as CC BY-NC-SA** (wiki footer; PFAF's own page contradicts itself) | dev-time filter only; do not ship as app data without PFAF permission |
| Munsell renotation (RIT) | free, no formal licence | colour mapping |

Already held: ECOCROP facts, Ellenberg/EIVE, PLANTATT, Plant Variety Database (CC BY 4.0)
(see `trait-databases.md`).

Needs an account:
- LUCAS topsoil: one ESDAC form per survey year; no redistribution. Worth it only for texture/pH priors, not soil photos (section 6);
- HadUK-Grid: free CEDA account (fetched 12 Oct 2026; see section 6).

Paid, skip:
- BGS London Earth;
- LandIS NATMAP.

## 6. Added 12 Oct 2026: scoring, calendar, frost grid and orientation

Scripts and raw outputs for every probe below are in `data/external/probes-2026-10-12/`
(local, not in git).

### Soil texture from a photo, scored on a public set

- **Set:** GLM-5.3-Flash was run on 141 public, labelled soil photos
  (`data/external/soil-photos/`):
  - lab-measured tray samples;
  - jar samples;
  - US soil-survey profile pits;
  - 3-class patches;
  - growing media.
  184 calls, $0.23, median 13.5 s per call.
- **Texture (92 images with a full USDA class label):** the model did **worse than always
  answering "sandy loam"**. Exact class: 14% against the baseline's 35%. Within one
  neighbouring class: 45% against 72%. Sandy, loamy or clayey: 54% against 58%.
  - It called 19 of 32 sandy loams "sand".
  - It answered "unknown" on 7 of the 12 clays.
- **Calibration:** weak. At texture confidence ≥ 0.5 the sandy/loamy/clayey call was right
  78% of the time (n = 37); exact class gained nothing. No answer had confidence above 0.8.
- **Material:** safe in one direction. No compost photo was called mineral soil, but 11% of
  mineral soils were called compost. Peat vs peat-free was right 2 of 6 times.
- **Repeats:** the same image gave the same exact class 76% of the time, the same
  sandy/loamy/clayey call 83%, and the same material 93%.
- **Rule for the app:**
  - never state texture from a photo;
  - use the sandy/loamy/clayey lean only as a soft prior when confidence is ≥ 0.5;
  - always ask the squeeze question;
  - "bought compost vs soil" may be stated.
- **Label caveats:** none of the images is a casual garden photo. Clay is thin (12 images),
  and so is growing media.

### UK crop calendar as data

- 155 crops (83 vegetables, 31 herbs, 35 fruit, 6 edible flowers), in
  `data/external/soil-and-crops/uk-crop-calendar/` (local only).
- Fields: sow indoors, sow outdoors, plant out, harvest months, hardiness, container size,
  sun and soil notes. Each row has sources and an evidence tier (129 tier C, RHS or Garden
  Organic; 26 tier D).
- Calibrated to mid-England frost dates, with mild-area-only months flagged.
- Check against the RHS mid-October list: 11 of 12 found. Rhubarb was missed because RHS and
  Garden Organic disagree on crown planting. 48 crops have source disagreements, logged in
  `disagreements.md`.
- The build scripts are in the probes folder, not in `scripts/`. Move them there before the
  app depends on the calendar.

### Frost and sun normals (Met Office HadUK-Grid 1 km, 1991–2020)

- Free CEDA login; OGL. The files are in `data/external/haduk-grid/`.

| Normal | A UK test garden | Central London |
|---|---|---|
| Air frost nights / year | 53 | 16 |
| Ground frost nights / year | 102 | 67 |
| Mean minimum, coldest month | 0.9 °C | 3.5 °C |
| Sunshine hours / year | 1,515 | 1,560 |
| Air frosts in Oct / Nov | 1.4 / 5.6 | 0.1 / 1.1 |

The two sources measure different things. The ERA5 grid (about 9 km, via Open-Meteo)
counted about 36 nights below 0 °C a year for central London, against HadUK-Grid's
16 air-frost nights. The coarse grid misses the urban heat island, and HadUK-Grid is
built from station records. For frost risk, use HadUK-Grid. Its London sunshine
(1,560 h) is lower than Kew's 1,693 h because the cell and the station differ.

### Garden orientation and sun hours from photos (worked case)

- **Method:** geometry, not the vision model (which called sunny photos "overcast"):
  - a pinhole camera model from the 35 mm-equivalent focal length;
  - sun positions from the EXIF capture time and a city-level location;
  - hard shadows on gridded paving;
  - one photo with the sun in frame (`20261004_131430`), which fixed that camera's heading
    to ±2°.
- **Result:** surfaces placed to about ±10°.
  - The test garden runs south from the house: down the garden is about 191° true (11° west of south); the retaining wall faces about 11° (N by E).
  - The patio-side retaining wall faces north. The strip bed on top is open to the south,
    with a 1.8 m fence and a 6–7 m hedge about 10 m beyond.
  - The pot-row wall faces east.

| Spot | Mar / Sep | Jun | Dec |
|---|---|---|---|
| Strip bed (middle) | ~3.6 h | ~9 h | ~0.4 h |
| Herb trough | ~7 h | ~11 h | ~0.8 h |
| Pot row (east-facing wall) | ~6 h | ~8 h | ~0.8 h |
| Corner pot | ~1.4 h | ~5.5 h | 0 |

- **Uncertainty:** ±1–2 h at the equinoxes. Obstacle heights drive the hours more than
  orientation does.
- **Lit/shade check:** the model matches 11 of 11 lit/shade observations after raising the
  hedge 5°. That is a calibration, not an independent check.
- **Failure modes:**
  - overcast days (4 of 6 days here);
  - unknown phone tilt;
  - unphotographed sky sectors;
  - **reflected light** on a sun-averted face, which fooled a naive "lit means sun-facing"
    rule.
- **Cheapest robust input:** record the phone's compass heading and tilt at capture
  (DeviceOrientation), with shadow geometry as a cross-check.
- **Phone compass tested, 12 Oct: it failed.**
  - Kash's 10 taps at the strip bed (Galaxy S24+, Chrome) read 334°, steady to 2°. The
    true heading is 191°, an error of 143°.
  - Three independent checks back 191°: two sun-in-frame photos (4 and 12 Oct) and the
    house outline on the map.
  - Google Maps' beam on the same phone was also tens of degrees out.
  - The app now asks for an 8-way direction instead
    (`data/eval/reports/2026-10-12-compass-probe.summary.json`).
  - A steady phone reading can still be badly wrong, so a sun-in-frame photo at a known
    time is the better automatic check.

### Checks closed 12 Oct 2026

**Is 2026 really that warm? Yes.**
- **Sources:** Met Office HadUK-Grid areal monthly series and HadCET daily (recent days
  provisional) [C]:
  - `metoffice.gov.uk/pub/data/weather/uk/climate/datasets/Tmean/date/{England,Midlands,UK}.txt`
  - `metoffice.gov.uk/hadobs/hadcet/data/meantemp_daily_totals.txt`
- **Jan–Sep mean temperature:** 2026 ranks **1st of 143 years** for England (12.54 °C) and
  for the Midlands (12.49 °C). It is 0.7–0.8 °C above the previous best (2022, 2025) and
  above every 1991–2020 year (England 9.62–11.53 °C).
- **Apr–Sep:** 1st as well.
- **HadCET growing degree days (base 5 °C), 1 Jan to 5 Oct:** 2,248, **1st of 255 years**.
  That is 25% above the 1991–2020 mean and 9–16% above 2025, 2022 and 2018, consistent
  with the ERA5 estimate.

**Is LUCAS worth a sign-up for soil-photo ground truth? No.**
- LUCAS field photos are open, with no account
  (`gisco-services.ec.europa.eu/lucas/photos/<year>/...`). Only the point, cover close-up and
  landscape shots are published. The surveyors' soil-sample photos are internal control
  photos and are never released.
- So **no** points have both lab texture and a published bare-soil close-up.
- A 9-point UK 2018 sample showed soil in 3 photos: enough for colour and structure, not
  texture.
- The free ESDAC lab-data form (personal licence, aggregated results only) is worth it
  only if we later want local texture/pH priors.

### Shadow positive control: can the vision model read sun and shade?

- **Setup:** GLM-5.3-Flash on photos with known answers (hard shadows, the sun in frame,
  overcast controls, the reflected-light trap), 3 runs each. Two prompts: blind, and with
  the capture time's solar azimuth/elevation given. About $0.37.
- **Sunny vs overcast:** right 27 of 31 times. A shaded corner on a clear day was called
  overcast.
- **Shadow direction** (within 45°, where the camera pose is known): 5 of 9. One answer was
  mirror-reversed. It said "no visible shadows" with the sun in frame.
- **Lit/unlit for named surfaces on sunny photos:** 14 of 20. It called the north-facing
  sleeper sunlit in 4 of 11 sunny runs.
- **Reflected-light trap:** fooled. Given the sun position, it reasoned "lit, so it faces
  the sun" and put the north-facing sleeper face facing SW.
- **Giving the sun position did not help** (thin evidence: only 3 of 27 sunny calls parsed): surface facing right 0 of 3 times, and camera
  heading within 30° only on the sun-in-frame photo.
- **Cost of sunny photos:** they trigger very long reasoning. 7 of 27 blind calls returned
  no JSON even at 8,192 tokens, with a median of 41 s (overcast photos, either prompt: 9–14 s).
- **Verdict:** sun exposure comes from geometry (EXIF time, location, hard shadows) and a
  compass reading at capture. The model is at most a cross-check on "is the sun out", never
  on which way a surface faces or whether it is lit.

### Wet or dry compost from a photo (probe, 12 Oct 2026)

- **Ground truth:** hours since the last water input. Waterings on 1 and 2 Oct; rain of
  7.3 mm ending 7 Oct and 3.5 mm ending 9 Oct; no watering after 2 Oct. Only one finger test
  exists, so the finger test could not be the target.
- **Pixel darkness (CIELAB L\*) of bare compost** (corner pot, 15 photos):
  - L\* below 10 appeared only within about 8 h of a big water input (4 of 7 such photos,
    0 of 8 photos more than 24 h after one).
  - The darkening fades in about 5 h on a bright day.
  - "Wetted in the last 2 h" vs the rest: AUC 0.79 (overcast/bright 0.90, sunny 0.50).
  - Herb trough (19 photos, compost covered with dead foliage): AUC 0.73 for wetted within
    24 h.
- **Lighting confound:** the spread between dry sessions (L\* 9–22) is as large as the
  wet–dry difference. Normalising against terracotta or the trough wall made it worse,
  because terracotta darkens when wet too.
- **Vision model:** it answered "damp" for 57 of 66 photos. Wet vs dry was at chance (30 of
  52). It never called freshly watered compost "wet", because peat-free compost is near-black
  either way. 330 calls, $0.19.
- **Literature:** RGB darkening tracks moisture under controlled light (smartphone SVR
  R² 0.95). In the field a grey card does not fix colour, and transfer between phones fails.
  A dry patch of the same material in the scene is the best reference [A].
- **Rule for the app:**
  - never drive watering advice from photo darkness or from the model;
  - at most, use darkness to confirm "watered in the last ~6 h", on bare compost, in flat
    light, compared with the same user's earlier photo from the same viewpoint;
  - always ask the finger test, and track dry-down in the twin from rain and reported
    watering.

### Weeds as soil clues (probe, 12 Oct 2026)

- **Test garden:** 50 photos, 2 runs each. Zero usable non-sown species: the garden is laid
  turf, fresh beds and clean paving.
- **Species ID** on 20 public UK weed photos (iNaturalist research grade, CC0/CC BY):
  correct species as top pick 14 of 20, correct genus 20 of 20. It stopped at genus for the
  two strong indicators: sheep's sorrel (acid) and soft rush (wet).
- **Common weeds barely discriminate:** R (pH) is 6–7 for 18 of 20, so a typical weed list
  agrees with the soil prior but cannot move it. Only N (fertility) spreads widely.
- **Literature [A]:**
  - mean N tracks productivity well (r 0.91, Hill & Carey 1997);
  - mean R stops discriminating above about pH 4.75 (Schaffers & Sýkora 2000);
  - mean F is weak;
  - the best case for pH is an error of about 0.64 units, from 271k survey plots
    (Wamelink 2019);
  - disturbed or young communities lag behind their soil (Dzwonko 2001).
- 147 calls, $0.23.
- **Rule for the app:** not an automatic clue. At most an optional step, used only with 5 or
  more non-sown species at confidence 0.5 or above from close-ups. Use only N, plus
  strong-indicator flags (sheep's sorrel or heather for acid; rushes for wet). Never let it
  override the pH or wetness prior.

### Frost alert for a metal trough (backtest, 12 Oct 2026)

- **Truth:** a SYNOP station 33 km from the test garden, via Meteostat (CC BY-NC, so dev
  only), winters 2024–25 and 2025–26. Forecasts as issued come from Open-Meteo Previous Runs.
- **Today's twin threshold** (forecast minimum ≤ 2 °C) fired on 66 and 36 nights. It caught
  every hard frost (≤ −3 °C), but 89% of those alerts were false.
- **Recommended three tiers:**

| Tier | Rule | Backtest | Action |
|---|---|---|---|
| Season start | first night forecast ≤ 0 °C at 2-day lead | 19 Nov both years | get the trough ready: against the house wall, pot feet, wrap |
| Hard frost tonight | forecast ≤ −2 °C at 1-day lead, sent about 16:00 | caught every hard frost; about half of alerts were not ≤ −3 °C, and all but one in two winters were still air frosts | wrap or move the trough; fleece rosemary and tarragon |
| Freezing spell | 3 or more nights in a row forecast ≤ −2 °C | 1 spell each winter (7–11 Jan 2025, 2–5 Jan 2026), no false spells | shed or porch, or full wrap |

- **Clear-calm adjustment:** dropped; only 11 of 422 nights qualified.
- **Forecast bias:** the 1-day forecast was unbiased against the station (+0.1 °C, typical
  error 1.1 °C); the 2-day forecast ran +0.75 °C warm.
- **Root zone (simple heat model, 16 L trough):** freezing water holds moist compost near
  0 to −1.5 °C. Single frosts of −4 to −6 °C left the root zone at −0.2 to −1.3 °C; only
  multi-night spells reached −5 to −8 °C. The heat-loss rate is the big unknown; a £10
  min/max probe would pin it down.
- **Per-plant risk** (root-zone figures assumed from published root-kill tables):
  - rosemary and tarragon (H4): below about −5 °C air, or a −4 to −5 °C root zone;
  - sage (H5) and garlic chives: roots at about −6 to −8 °C;
  - parsley: leaf scorch at −5 to −7 °C;
  - mint, lemon balm and ferns: no action;
  - basil: +5 °C.
- **Wiring:**
  - a night minimum from hourly temperature in `stages/environment.py`;
  - a frost-alert model in `schemas.py`;
  - the tier rule in `stages/twin.py`, replacing the fixed pot penalty;
  - container material in the private working repo's `plants.json`;
  - delivery could ride the daily reminder job, but would need a 16:00 run and an opt-in.

### A worked garden plan

`data/external/probes-2026-10-12/garden-plan/` (`plan.json`, `plan.md`, and the build
script that checks every month against the calendar) shows the output the design in
`docs/superpowers/specs/2026-10-12-minimal-input-soil-and-grow-design.md` aims for. It covers,
per spot of the test garden:
- sun profile and medium;
- actions for existing plants;
- ranked picks filtered from the calendar;
- a month-by-month plan from Oct 2026 to Sep 2027.

## 7. Gaps

- No ground truth yet for the test garden's texture. A squeeze test is pending.
- No casual garden photo with lab-measured texture exists in the public set, and LUCAS
  does not publish its soil photos. The best ground truth is a user's own squeeze test.
- The hedge height and the unphotographed SE sky limit the sun-hour estimates.
- Location can't see imported topsoil, rubble, compaction, walls, shade or frost pockets.
  The photo and one or two questions (squeeze, compass) must cover those.

## 8. Build evaluation, Oct 2026

The "What can I grow here?" answer (plan phases S0 to S6, live from 12 Oct) measured
against its design's evaluation list (spot spec section 9). Every free number was re-run
on 13 Oct in the `docs/spot-eval-results` worktree. The paid spot read was run twice:
with GLM-5.3-Flash on 12 Oct (S2), and with `google/gemma-3-27b-it` on 13 Oct, because
GLM was down on Token Factory that day and the backup model read most photos
(`photo-model-fallback.md`). The Gemma run has 4 more garden photos (labelled since
12 Oct), so the two rows are not quite the same set; 4 photos do not explain the gap.

| What | Data | Measure | Target | Result |
|---|---|---|---|---|
| Soil texture prior | LUCAS 2018 | BGS band vs lab; pH in range | above "always loamy"; ≥ 70% | not run: the ESDAC form was not signed (Kash, 12 Oct); optional later |
| Spot read, GLM (12 Oct) | 86 garden + 136 public photos | setting accuracy; compost called soil | ≥ 90%; 0 | **0.93** (met); **1** (missed: a trough close-up); soil called compost 5.2%; $0.24 |
| Spot read, Gemma (13 Oct) | 90 garden + 136 public photos | setting accuracy; compost called soil | ≥ 90%; 0 | **missed: 0.78** (70 of 90); **3** (missed); soil called compost 12.7%; 1 public photo gave no answer; $0.02 |
| Solar geometry | astral (NOAA equations), 3 UK points × 4 dates | azimuth, elevation error | < 0.5° | met: all 25 tests in `test_solar.py` and `test_sun_worked_case.py` pass; worst error 0.005° against astral's reference values (S3 also matched pvlib within 0.01°) |
| Sun hours | the worked case (section 6) | each table cell within ±1.5 h | 4 of 4 spots | **missed: 1 of 4 spots**, 8 of 12 cells. Strip bed March, pot row June and corner pot March and June miss; the June sun class always holds |
| Lit or shaded | 76 garden photos, 47 with a decisive light reading | geometry agrees with the photo | ≥ 80% | **missed: 0.617** |
| Compass | S0 probe: 10 taps at the strip bed | heading error | median < 15°, worst < 30° | **failed:** median 143.3°, worst 143.7°; the app asks for an 8-way direction instead |
| Grow list | RHS monthly picks × 12 months × 4 settings | two-tier recall (good now + worth a try); hard errors | ≥ 0.85; 0 (amended 12 Oct from recall@8 ≥ 0.7) | met: **0.90** (415 of 461), **0** hard errors. Reported, not gated: recall@8 0.157 (0.32 of its ceiling); recall as shown, 8 per tier, 0.33 |
| Ask rate | 500 GB points × 5 settings × 12 months (30,000 reads) | share asked; share of asks where a plausible answer changes the top 5 | report; 100% by construction | asked on **23.8%**; the top 5 changes in **94.9%** (short of 100%); the list as a whole changes in 100% |

Sources: `data/eval/reports/2026-10-12-spot-read.summary.json`,
`2026-10-13-spot-read.summary.json`, `2026-10-12-compass-probe.summary.json` and
`2026-10-12-grow.summary.json` (the 13 Oct re-run matched it exactly), all under
`data/eval/reports/`.

### Live check with the backup model (13 Oct, revision `herbtwin-00017-6sp`)

One strip bed photo (location data removed, a city-centre postcode typed in, direction
"S") through the live page:
- **The log shows the backup taking over:** GLM timed out after its 90 s
  (`zai-org/GLM-5.3-Flash failed ... reading with google/gemma-3-27b-it for the next
  300 s`). Gemma's read took about 4 s, and the answer opened 95 s after the upload.
- **The answer:** Raised bed (right), "Looks like garden soil", the maps' clayey band,
  colour 10YR 4/3, the squeeze question offered. About 9 h of June sun from the
  direction picked; 47 air frosts a year.
- **The list:** garlic, spring cabbage, shallot, chamomile and onion sets lead "Good now".
  Broad bean, lettuce and peas are under "Not here". Spring cabbage still shows "Frost:
  not known".
- **Gemma's speed varies:** three timed spot reads the same afternoon took 54 s, 4 s and
  4 s. Each photo cost 585 input tokens whatever its file size (4–5 MB), so the provider
  shrinks the image itself; sending smaller photos would not save tokens. The 226-photo
  run took about 75 minutes for the same reason.

### What fell short, and why

- **Compost called soil (GLM, 1 photo):** a close-up of the trough's compost read as
  garden soil. Without a squeeze the page only says "Looks like garden soil"; "Garden
  soil" needs the squeeze to agree. Changing the setting to pot or trough resets the
  medium to compost.
- **Gemma's setting, 0.78:** half the 20 misses are pots read as open ground: the corner pot 7
  of 19, the pot row 3 of 23. Trough close-ups
  read as a raised bed or a pot 6 of 10 times. Two bed close-ups read as open ground, which
  changes little, since both are garden soil. Counting raised bed and open ground as one,
  Gemma gets 0.80, still under 0.90. Wide shots of the trough (26 of 27) and the pot row
  (20 of 23) are mostly right.
- **Gemma's compost called soil, 3 photos:** two trough close-ups and one corner pot, the
  same kind of photo GLM missed once. All 3 were also read as raised bed or open ground,
  so the page used the maps' band and asked the squeeze until the setting was corrected.
- **Sun hours, 1 of 4 spots (8 of 12 cells):** one direction tap sees only what is in
  front of the spot. The strip bed's March hours depend on a fence to the east, and the
  corner pot has a fence right beside it. The pot row's June (9.7 h against 8 h solved)
  is not yet explained. Only the herb trough matches on all three dates. No other set of
  defaults did better than 2 of 4 spots.
- **Lit or shaded, 0.617:** the same one-tap horizon misses, plus the light reading's proxy
  sky, and photos framed away from the spot they are filed under. Not tuned away: the taps
  come from the worked case.
- **Compass, 143° out:** the phone's reading was steady to 2° and still wrong. Google
  Maps' beam on the same phone was also tens of degrees out. A steady reading is not a
  right one, so the app asks for a direction instead.
- **Ask rate, top 5 changes in 94.9%, not 100%:** in 5.1% of asks every plausible answer
  changes only crops below the top 5, so the question changes the list but not what a
  person sees first.
- **Grow list, recall as shown 0.33:** the right crops are in the tiers (0.90), but only 8
  per tier show before "more". The RHS lists name more crops a month than a small spot
  needs.

### What it means for a person using the page

- The setting (pot, trough, bed) is read right about 9 times in 10 with GLM and 8 in 10
  with Gemma, and a wrong one is one tap to fix. A pot or trough is always treated as bought compost.
- From the photo alone the page says only "Looks like garden soil": the maps give a band,
  and the squeeze test settles it.
- Sun hours are a class (full sun, part shade, shade), not a promise. A spot with a
  fence or wall beside it, not behind it, can read sunnier than it is.
- The direction is a tap, not the phone's compass.
- While GLM is down, most reads go straight to Gemma. The first read after each 5-minute
  pause, or on a fresh server, waits about 90 s for GLM before Gemma answers. A pot can
  then show as open ground about 1 time in 5. The list is then built for open ground, with no pot-size
  check, so a tree can show as "good now" until the person taps "Pot". The answer page's "Not right? Change the
  setting" row is the fix, and it costs no model call. When GLM is back, it goes first
  again.

### Follow-ups for Kash to choose

- The wet squeeze test 10–15 cm down in the strip bed. The topsoil read gritty, but the
  lump was only slightly wet.
- Identify the seedlings in the corner pot.
- Yes or no on adding Open-Meteo soil temperature and moisture, and HadUK frost, to the
  weather step.
- A "wall or fence beside it" chip, for the sun-hours misses above.
- A hardiness rating for spring cabbage, so it stops showing "Frost: not known".
- Also open: a "topsoil over clay" answer to the squeeze question; LUCAS lab data if the
  ESDAC form is signed later; a second compass check on another phone or on iOS.

Re-run the numbers (from a worktree; `$MAIN` is the main checkout, which holds the photos):

```bash
uv run pytest tests/test_solar.py tests/test_sun_worked_case.py -q
uv run python scripts/eval_sun_crosscheck.py --main "$MAIN"
uv run python scripts/eval_grow.py
uv run python scripts/simulate_ask_rate.py --points 500 --seed 7
# paid: dry run first (it quotes $0.23 at GLM's rate; Gemma cost $0.02); a same-day
# run overwrites that day's summary file
HERBTWIN_OBSERVE_MODEL=google/gemma-3-27b-it uv run python scripts/eval_spot_read.py --main "$MAIN" --dry-run
HERBTWIN_OBSERVE_MODEL=google/gemma-3-27b-it uv run python scripts/eval_spot_read.py --main "$MAIN"
```
