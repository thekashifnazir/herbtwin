# Container physics for the water bucket

Published values and models for parameterising a FAO-56 style bucket for herbs in a
metal trough and terracotta pots. Swept 3 Oct 2026. About half the wanted quantities
have published numbers; terracotta wall loss, herb-specific pot ET, UK winter waterlogging
and pot cracking have none that could be reached. Values marked "derived" or "assumed" are
arithmetic on published numbers, not measurements. Property tables in the ASHS papers are
images, so only values stated in text or abstracts are reported.

## Parameter table

| Quantity | Value or range | Substrate or condition | Source |
|---|---|---|---|
| Plant-available water (1 to 10 kPa) | 14.0, 14.1, 15.0, 16.9, 16.4% by volume | pine bark with 0, 10, 25, 40, 65% coir | Water 2020, doi:10.3390/w12020362 |
| Container capacity and air space | capacity about 60.7%, air space about 33.2%, total porosity over 90% | pine wood-fibre components | HortScience 2022, 57:304 |
| Air space of peat blends | 10 to 19% by volume | peat with 10 to 50% perlite or pine wood | Jackson and Fields 2014, doi:10.21273/hortsci.49.6.827 |
| Water left at −10 kPa | 29.2, 33.7, 37.1% of pore space | 70:30 peat with perlite, shredded wood, wood chips | same |
| Onset of plant stress | −10 kPa (xylem stress), −16 kPa (chrysanthemum) | substrate matric potential | Caron 1998, Kiehl 1992, cited in same |
| Bark release curve | most water released by −1 kPa | aged pine bark | same |
| Pot height effect | water-holding falls 20% (medium bark) to 42% (fine bark) from 3.8 to 15.2 cm height; capacity falls linearly, air space rises | | Owen and Altland 2008, doi:10.21273/hortsci.43.2.505 |
| Pot geometry effect | air 28% and water 43% in a #1 pot; air 12% and water 59% in a bedding cell, same medium | | Bilderback and Fonteno 1987, doi:10.24266/0738-2898-5.4.180 |
| Plug tray to 15 cm pot | air space differs 10-fold; capacity drops about 20% | peat mixes | Jackson and Fields 2014 |
| Pot wall material | fired clay cools the root zone by evaporation when wet; porous walls raise water demand. **No numbers given** | review | Ingram et al. 2015, doi:10.21273/hortsci.50.4.530 |
| Pot colour | white pots gave 36% more growth than spaced black; black spaced most often above 39 °C | 1.5 L pots, Alabama | Agriculture 2022, doi:10.3390/agriculture12122165 |
| Root heat injury | 45 to 57 °C for 30 min | woody ornamentals | Ingram et al. 2015 |
| Daily ET, container shrub | under 600 mL a day (11.8 mm on pot-top area) most of the cycle; 1.3 L a day at spring flush | Viburnum, 11.4 L pot, Florida | Beeson 2010, doi:10.21273/hortsci.45.8.1260 |
| Bare substrate evaporation | 200 mL a day (4 mm), 160 mL (3.1 mm) under canopy; uncoupled from ET0 of 1.2 to 4.6 mm | same | same |
| Kc on pot-top area | 1.0 to 2.5 over 20 months | woody ornamentals, 15.6 L | Schuch and Burger 1997, cited in Beeson 2010 |
| ETc by season | 5.8 mm (1 April), 13 mm (12 July) | Viburnum, 25 cm pots, Florida | Million and Yeager 2015, doi:10.21273/horttech.25.4.528 |
| Capture factor | 0.5 to 2.5; 1.0 until the plant is wider than the pot; rhododendron 0.6 to 0.7 | upright habit funnels water in, umbrella habit sheds it | Million and Yeager 2015, doi:10.21273/hortsci.50.3.442 |
| Rain effectiveness | 31% of total rain offset irrigation; 79% on days under 12.7 mm, 17% on days of 12.7 mm or more | 24 weeks, Florida | same |
| Rewetting dry peat | capacity about 40% lower at 33% initial moisture; maximum water content down 21.5% after one wet-dry cycle; 15% coir restores it | peat vs coir vs bark | Agronomy 2020, doi:10.3390/agronomy10091389; HortScience 2022, doi:10.21273/hortsci16698-22 |
| Waterings needed to refill | peat without wetting agent: capacity not reached in 10 events even from 50% moisture; coir and bark: 1 event from 50%, not reached in 10 from 25% | | Fields et al. 2014, doi:10.21273/hortsci.49.3.336 |
| Wood fibre wettability | stays hydrophilic after drying; improves rewetting of peat mixes | white peat + wood fibre | Agronomy 2021, doi:10.3390/agronomy11050907 |
| Root killing temperature | young roots −3 to −11 °C; mature roots −8 to −23 °C | woody ornamentals | Studer et al. 1978, doi:10.21273/hortsci.13.2.172 |
| Perennial root injury | tender −2 to −4 °C; intermediate −6 to −9 °C | growing-medium temperature | UMass Extension overwintering fact sheet (Havis table) |
| Winter moisture | moist media freeze more slowly than dry; overwatering promotes root and crown disease | qualitative | UMass Extension |

## Published models with equations

- **CIRRIG (Million and Yeager).** Daily deficit bucket with carry-over. Irrigation requirement = (container ET / capture factor) × (100 / distribution uniformity); rain is credited only up to the current deficit. Worked example in UF/IFAS EDIS EP458. This is the nearest published model to our bucket.
- **Beeson canopy-closure model.** ET volume = ET0 depth × projected canopy area × a water-needs index that decays exponentially with percent canopy closure (r² 0.84 to 0.87). Coefficients not extracted.
- **Milks, Fonteno and Larson 1989**, doi:10.21273/jashs.114.1.48. Five-parameter van Genuchten-type retention curve for container media, combined with pot geometry to predict capacity and air space per pot.

## Default parameter sets

**Trough** (assumed 70 × 17 × 15 cm, about 16 L, top area 0.12 m²):
- available water 0.20 L per L (range 0.14 to 0.30), so about 3.2 L, or 27 mm on the trough area
- "water now" trigger at 40 to 50% depletion
- bare-surface evaporation 3 to 4 mm a day when wet
- Kc on container area 1.0, rising to 2.0 as canopies overhang
- rain capture factor 1.0; rain credited only up to the current deficit
- metal walls (the trough is metal, confirmed by Kash on 3 Oct 2026; the sweep assumed plastic): no wall-loss term, but metal conducts heat, so the root zone on the sun-facing side warms faster than in plastic. Apply the root-zone heat rule in `risk-models.md` section 4 at a lower air temperature for the trough, as a declared assumption; no published figure for metal planters was found.

**20 cm terracotta pot** (assumed 3.5 L, top area 0.031 m²):
- available water about 0.7 L, or 22 mm
- same Kc logic
- at a London summer ET0 of 3 to 4 mm a day: 0.1 to 0.3 L a day and roughly 2 to 7 days from full to stress (derived)
- wall-evaporation multiplier 1.0 to 1.5, a free parameter
- mint and lemon balm at full canopy may shed rain (capture factor below 1)

## The three biggest uncertainties

1. **Substrate.** No accessible paper characterises UK retail peat-free multipurpose compost; the values are US bark, coir and wood-fibre mixes. Nothing was found for loam-based mixes or a true wilting point.
2. **Terracotta and herb ET.** No quantitative clay-vs-plastic evaporation study turned up, and no herb-specific pot ET or measured days-to-wilting. All Kc values are Florida woody shrubs; small isolated pots have strong advection, so Kc on pot area can exceed 2.
3. **Rain and winter.** Rain-effectiveness figures come from spaced nursery pots under Florida storms. No peer-reviewed data on UK winter waterlogging, the root-versus-shoot hardiness offset in degrees, or terracotta frost cracking. Treat winter as rule-based: flag saturation lasting several days, and flag root-ball temperature below about −5 °C for the tender herbs.

## The surface layer (added 3 Oct 2026)

First finger test, about 18 hours after an evening watering on a bright day: "between dry
and damp, cool but not moist" at 2 cm in every container, the trough slightly different
from the pots. The top layer had nearly dried while the pot below was still charged.

- A 2 cm finger test reads the **surface layer**, not the root zone. The bucket's total
  available water cannot be compared with it directly.
- FAO-56's dual coefficient method already has the structure: an evaporable surface layer
  (depth 0.10 to 0.15 m in field soils) holding readily evaporable water that goes within
  about a day, then total evaporable water that goes more slowly. For a pot the layer is
  thinner; treat its depth and capacity as declared assumptions.
- The twin therefore tracks two stores: the surface layer, compared against the finger
  test, and the root zone, which drives stress. Advice follows the root zone: "the top
  dries in a day; underneath it is still fine" is the message that prevents overwatering.
- The finger scale has four levels: dry, cool but not moist, damp, wet.

## How we calibrate without weighing

The literature's answer to uncertainties 1 and 2 is a saturate, drain and weigh test per
container. Pot weighing is not part of this project (see the private working repo's photo protocol). So:

- available water, the wall multiplier and Kc are **declared assumptions with ranges**, shown
  in the twin's `assumptions` list on every result;
- the garden photo series calibrates them indirectly: the known watering on 1 Oct 2026 and
  any later reported watering give dry-down intervals, and the day the raters' wilting
  score first rises is the observation the bucket must reproduce;
- plan 3's Monte Carlo samples these ranges rather than fixing them.

## Not retrieved, worth trying by hand

Mathers 2003 (HortTechnology 13:617), the Pardossi InTech chapter on container ET models,
Michel 2010 (Mires and Peat) and the numeric tables in Gruda 2019. journals.ashs.org
blocks automated fetches; six papers were read through a reader proxy.
