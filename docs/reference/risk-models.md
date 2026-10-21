# Risk models for the twin (plan 3 inputs)

Published models, thresholds and climatology for forecasting fungal, heat, bolting, pest
and frost risk for potted herbs in a London garden from a daily weather feed. Swept
3 Oct 2026. Items marked U come from training knowledge and were not opened; everything
else was read that day. Each risk ends with the simplest defensible v1 rule and an
evidence tier.

## Evidence tiers (used across the twin)

Borrowed from GRADE (medicine) and Conservation Evidence (ecology), simplified:

| Tier | Meaning |
|---|---|
| A | peer-reviewed lab or field thresholds for this pathogen, pest or species |
| B | validated model borrowed from a related crop |
| C | extension or RHS guidance without a published model |
| D | heuristic or expert rule |

Sources: GRADE (en.wikipedia.org/wiki/GRADE_approach), OCEBM 2011 levels, Sutherland et
al. 2021 What Works in Conservation, doi:10.11647/obp.0267.

## 1. Fungal and oomycete risk

| Model | Source | Inputs | Form | Thresholds | Validation | Fit |
|---|---|---|---|---|---|---|
| **Magarey generic infection model** | Magarey, Sutton, Thayer 2005, Phytopathology 95:92, doi:10.1094/PHYTO-95-0092 | hourly temperature during wet periods, wetness duration; per-pathogen Tmin, Topt, Tmax, Wmin, Wmax | required wetness W(T) = Wmin / f(T), f a cardinal-temperature function equal to 1 at Topt; infection when wet period ≥ W(T); dry interruptions at RH under 95% shorten the effective wet period by a pathogen-class critical dry period | Wmin 1 to 48 h across pathogens; uniform within Cercospora, Alternaria, Puccinia | 53 lab datasets, mean r 0.83, RMSE 4.9 h | **good**; built for data-poor pathogens; derive hourly T from Tmin and Tmax by sine interpolation |
| **Basil downy mildew** (Peronospora belbahrii) | Cohen et al. 2017, Phytopathology 107:1149, doi:10.1094/PHYTO-01-17-0017-FI; Cohen and Ben-Naim 2016, PLoS ONE, doi:10.1371/journal.pone.0155330 | leaf wetness hours, night RH, temperature | infection needs ≥ 4 h free moisture at 5 to 28.5 °C; sporulation needs ≥ 7.5 h at RH 85 to 95% in the dark at 10 to 26 °C (optimum 18 °C); latent period 5 to 10 days | as stated | fanning that removed nights with ≥ 4 h at RH ≥ 95% cut infected leaves from about 90% to about 1% in three trials | **good**, tier A |
| **Powdery mildew, Gubler-Thomas index** | UC IPM grape, ipm.ucanr.edu/agriculture/grape/powdery-mildew/ | hours per day at 21 to 30 °C | start at index 60 after 3 consecutive days with ≥ 6 h in range; +20 per day with ≥ 6 h, −10 without, −10 if ≥ 35 °C for 15 min; clamp 0 to 100 | 0 to 30 low, 40 to 50 moderate, ≥ 60 high | operational in California viticulture | **partial**, tier B (grape-calibrated) |
| **Botrytis grey mould** | Ciliberti et al. 2015, Phytopathology, doi:10.1094/PHYTO-10-14-0264-R; Broome et al. 1995 (paywalled); RHS grey mould page | temperature, wetness or RH | no infection at RH 65% or at 5 °C; 36 h wetness gave about 75% incidence at 20 to 25 °C, 50% at 15 °C, 20 to 30% at 10 and 30 °C; 6 to 12 h "moderately favourable" | use Magarey with Tmin 5, Topt 20 to 25, Tmax 30, Wmin about 6 to 8 h (U) | partial | **partial**, tier B |
| **Rust** (Puccinia, incl. mint rust) | Magarey 2005 notes Puccinia Wmin is consistent within the genus; mint rust temperature study Can J Plant Pathol 2013, doi:10.1080/07060661.2013.843593 (abstract not retrieved) | as Magarey | Puccinia defaults, Wmin about 4 to 6 h at 15 to 22 °C (U) | | | **partial**, tier B |
| **Phytophthora root rot** | RHS, rhs.org.uk/disease/phytophthora-root-rot | soil moisture layers, bucket state | zoospores swim in water films; disease of waterlogged media, pots included, year-round | rule: sustained bucket at or above capacity | none | **partial**, tier C |

**Leaf wetness without a sensor.** Standard estimators: hours with RH ≥ 90% (site-tuned 87
to 92%), dew-point depression ≤ 2 °C, or classification trees; mean absolute error on the
order of 1.5 to 3 h against sensors (Sentelhas et al. 2008, Agric For Meteorol 148:392;
Rowlandson et al. 2015, Plant Disease, doi:10.1094/PDIS-05-14-0529-FE; Montone et al. 2016,
Int J Biometeorol, doi:10.1007/s00484-016-1165-4). Open-Meteo exposes
`leaf_wetness_probability`, `dew_point_2m`, `relative_humidity_2m`, `precipitation_hours`
and `vapour_pressure_deficit`, so hourly RH is free.

## 2. Bolting

| Species | Source | What is known | Fit |
|---|---|---|---|
| Coriander | RHS grow-your-own | bolts in hot dry weather and with day-length change; shade, water and succession sowing mitigate; no published photoperiod or degree-day threshold found | poor, tier C heuristic |
| Parsley | RHS | biennial: leaves in year 1, flowers after a winter; treat as annual | partial, tier C: plant has overwintered ⇒ expect bolting in spring |
| Basil | RHS | flowers mid to late summer, earlier when crowded; plant out when nights stay above 10 °C | partial, tier C |
| Lettuce, as template | J Agric Sci 1947, doi:10.1017/S0021859600083465; Han et al. 2021, TAG, doi:10.1007/s00122-021-03898-9; 2026 Korean study uses cumulative temperature to bolting | bolting highest May to July with temperatures above 15.5 °C and long days; thermal time since sowing × daylength is the model shape | good as template, tier B |

## 3. Pests, degree-days

| Pest | Source | Thresholds | Fit |
|---|---|---|---|
| Two-spotted spider mite | Exp Appl Acarol 2017, doi:10.1007/s10493-017-0151-9; 2018, doi:10.1007/s10493-018-0241-3 | lower threshold 8.6 to 11.6 °C; egg to adult 128 to 151 degree-days; no development at a constant 10 °C; thrives hot and dry | **good**, tier A: DD = (Tmax + Tmin)/2 − 10 |
| Aphids | Bell et al. 2015, J Anim Ecol, doi:10.1111/1365-2656.12282 (Rothamsted Insect Survey); PeerJ 2026, doi:10.7717/peerj.21239 | first flights advance 0.61 days a year; drivers are accumulated degree-days above 16 °C and winter NAO; Myzus persicae fecundity 29.8 at 10 °C falling to 14.3 at 30 °C; base about 4 to 6 °C and 110 to 130 DD per generation (U) | partial, tier B: presence in London is near-certain, forecast surges on warm dry spells |
| Slugs | Young and Port 1991 and 1993, Crop Protection; Insects 2024, doi:10.3390/insects15100819 | precipitation, RH and temperature are the top predictors; slugs prefer about 125% soil capacity | partial, tier B: rain or wet surface and Tmin above about 5 °C ⇒ active |
| Vine weevil | RHS, rhs.org.uk/biodiversity/vine-weevil | adults spring to summer; larvae damage pots September to March; nematodes work when media are 12 to 20 °C (Heterorhabditis) or 5 to 20 °C (Steinernema); pots are the highest-risk situation | **good**, tier C calendar plus soil temperature |

## 4. Heat

| Quantity | Source | Value |
|---|---|---|
| Root-zone temperature in pots | Ingram, Ruter, Martin 2015, HortScience 50:530, doi:10.21273/hortsci.50.4.530 (review) | photosynthesis falls at root-zone ≥ 32 °C; 38 °C is the upper growth threshold; 42 °C for 6 h a day cut root length 45%; black containers in full sun exceed 45 °C (50 °C figure U) |
| Vapour pressure deficit bands | horticulture practice (Wikipedia VPD); Open-Meteo docs | ideal 0.45 to 1.25 kPa, about 0.85 optimal; above 1.6 kPa transpiration rises sharply |
| Basil heat treatment | Plants 2025, doi:10.3390/plants14050739 | 35/30 °C day/night used as heat stress vs 25/22 |

## 5. Frost climatology, London

Computed from the Met Office Heathrow station file
(metoffice.gov.uk/pub/data/weather/uk/climate/stationdata/heathrowdata.txt), 1991 to 2020:

| Month | Mean air-frost days | Mean Tmin °C |
|---|---|---|
| September | 0.0 | 11.6 |
| October | 0.3 | 8.8 |
| November | 2.7 | 5.3 |
| December | 7.2 | 3.1 |

So any air frost in a given October week is about 5 to 8% likely, rising to 15 to 20% a
week by late November. Central London (St James's Park) is warmer still.

- **Urban heat island:** strongest on clear calm nights; mean about 1.5 to 2 °C, extremes 6
  to 8 °C (U); Howard's 1810s figure 2.1 °C. Wilby 2003, doi:10.1256/wea.183.02; Jones and
  Lister 2009, doi:10.1002/wea.432; Wilby et al. 2011, doi:10.1002/wea.679.
- **Radiative frost:** clear sky, calm, cold surfaces; grass minima run 2 to 4 °C below the
  screen minimum on such nights (Met Office ground-frost definition, magnitude U). No
  quantitative garden-vs-grid study was found; treat the deviation as ±2 °C.
- **Frost forecast error** at 6 h lead: 1.5 to 1.7 °C (Talsma 2023, see literature.md).

## 6. Simplest defensible v1 rules

| Risk | Rule | Tier |
|---|---|---|
| Fungal | wet hours = hours with RH ≥ 90% or rain. Downy mildew: ≥ 4 wet h at 5 to 28 °C plus a night with ≥ 7.5 h RH ≥ 85% at 10 to 26 °C. Powdery mildew: 3 consecutive days with ≥ 6 h at 21 to 30 °C. Grey mould: ≥ 8 wet h at 15 to 25 °C. Root rot: bucket at capacity for 3+ days. | A / B / B / C |
| Heat | Tmax ≥ 30 °C with shortwave ≥ 20 MJ m⁻² (dark pot root zone likely ≥ 38 °C), or daily VPD above 1.6 kPa; severe at Tmax ≥ 35 °C | B |
| Bolting | coriander and basil: accumulate DD base 10 °C from sowing; warn when daylength over 14 h and 3-day mean Tmax ≥ 25 °C or a bucket deficit. Parsley: warn in spring once overwintered. | C |
| Pest | spider mite surge when ≥ 140 DD (base 10 °C) accumulate within 14 days and RH under 60%. Slugs when rain ≥ 1 mm and Tmin ≥ 5 °C. Vine weevil larvae window September to March for pots; nematode window when 6 cm soil is 12 to 20 °C. | A / B / C |
| Frost | risk if forecast Tmin ≤ 2 °C, high if ≤ 0 °C; subtract 2 °C on clear (cloud under 30%) calm (wind under 2 m/s) nights for exposed gardens. Negligible before mid-October, 2 to 3 frost nights a month by late November at Heathrow. | B |
