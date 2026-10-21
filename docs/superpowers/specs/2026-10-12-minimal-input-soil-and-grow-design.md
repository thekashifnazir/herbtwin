# Minimal-input soil, spot and what to grow, design spec

Drafted 12 Oct 2026; Kash approved D67 to D76 as proposed the same day and answered the
open questions (section 13). Implementation plan:
the private working repo's `2026-10-12-soil-spot-and-grow.md`. Evidence:
`docs/reference/soil-area-and-what-to-grow.md` (cited below as "ref §N"), gathered 11 to
12 Oct by the soil investigation stream (the private working repo's `2026-10-12-soil-investigation.md`).
Decisions run from D67 (D56 to D66 live in the phase D spec and the handoff).

## 1. Intent

Today the app answers "what does this plant need now?". This adds three answers about the
**spot**, from the least the person has to give:

1. **What soil is this?** Bought compost or garden soil; sandy, loamy or clayey; lime or
   not; how it drains.
2. **What do I need to know about my spot?** How many hours of direct sun it gets by
   month, how many frosts to expect and when, what the soil means for planting.
3. **What could I grow here now?** A short list of UK edibles to sow or plant this month
   (and next), each with why it fits and what would make it fail.

**Minimum input:** one photo and the location the app already resolves (photo GPS, phone
location, typed place: `where.py`). On top of that, **at most two one-tap questions**,
each asked only when its answer would change what we say (section 4).

**Success:**
- On the 4 test-garden spots with solved geometry (ref §6, orientation), the sun class
  (sun / part shade / shade) from one compass tap matches the worked case at every spot,
  and the equinox hours are within ±1.5 h.
- Against RHS monthly "sow and plant now" lists for 12 months and 4 settings (pot, clay
  ground, sandy ground, part shade), good now and worth a try together recall at least 85%
  of the RHS picks that suit the setting and fit its pot, with **zero hard errors** on that
  profile and on a cold and a mild one (section 9; amended 12 Oct, below).
- No question is asked whose every plausible answer gives the same list (checked by
  simulation over 500 GB points, section 9).
- The spot read adds no more than one vision call (about $0.001, median 11 to 13.5 s,
  ref §3 and §6) and runs while the person answers the compass question.
- With none of the new data files present, the app behaves as today and every offline
  test passes.

## 2. Non-goals

- **Texture from the photo.** On 92 public photos the vision model was worse than always
  answering "sandy loam" (exact class 14% vs 35%; within one class 45% vs 72%; ref §6).
  We never state texture from a photo.
- **Sun or shade from the vision model.** It fell for reflected light, mirror-reversed a
  shadow, called a sunny shaded corner overcast, and sunny photos took a median 41 s with
  7 of 27 calls returning no JSON (ref §6, shadow control). The model is not asked.
- **Indoor and windowsill light** (still D55's open item). A windowsill spot gets only the
  calendar's "any time, windowsill" crops (pea shoots, microgreens, potted chives), with
  no sun estimate.
- **Ornamentals.** The calendar holds 155 edibles (83 vegetables, 31 herbs, 35 fruit,
  6 edible flowers). Tulips stay a correct miss (ref §4).
- **Soil chemistry beyond pH and lime.** No N/P/K, no contamination reading. A fixed note
  covers lead for food crops in old urban ground (UK allotment screening level 80 mg/kg;
  98% of sampled Newcastle allotments exceeded it; ref §1).
- **Automatic hard-shadow solving** in the first build. The worked case (ref §6) was a
  manual solve; it stays a dev tool until section 6's cross-check proves it is needed.
- **Shifting sowing windows for 2026's warmth.** 2026 is the warmest Jan to Sep in 143
  years (England 12.54 °C) and HadCET degree days to 5 Oct are 25% above the 1991 to 2020
  mean (ref §6, checks). We say so in a note; we do not move windows (no data to fit how
  far).
- **Practical Plants (PFAF) in the app.** Treat as CC BY-NC-SA; dev-time only (ref §5).
- **A learned ranker.** 7,414 trait rows ranked raw found 1 of 15 RHS picks (ref §4).
- Outside Great Britain the soil priors are missing (BGS and UKCEH cover GB); outside the
  UK the calendar does not apply and the spot answer says so, as season norms do today.

## 3. User flow (D67)

```
photo ──► (EXIF time, GPS read; EXIF stripped, as today)
   │
   ├─ while the photo is read (11–13 s): QUESTION 1, compass tap  ── skip allowed
   │
   ├─ silent: spot read (vision: setting, compost or soil, colour, organic matter)
   │          location lookups (1 km grid: soil texture prior, lime, pH, frost, sunshine)
   │          coldest night (Open-Meteo ERA5-Land archive, cached per 1 km cell)
   │          light now (C1 exposure reading, when EXIF has a time)
   │
   ├─ value-of-information check ─► QUESTION 2, squeeze test, only if it changes the list
   │
   └─► answer: soil card, spot card (sun hours by month, frosts), grow list in tiers
            └─ any skipped question stays offered under the answer (B2 refine)
```

**Entry.** The upload page gets a second button, "What can I grow here?", beside "What
does my plant need?". The choice is the person's intent, not a question. The existing
observe stage cannot serve it: its prompt assumes a potted herb and a photo with no plant
stops the run at `is_plant=false` (`stages/observe.py`). A plant answer also links to
"About this spot", which reuses that photo's location and reading.

**Why the compass goes first.** It needs no photo result, the person is standing at the
spot right after taking the photo, and it fills the 11 to 13 s the vision call takes.
Sun is the input that moves the list most ("shade, then bed vs pot, then pH", ref §4), so
it is worth asking on every outdoor spot.

**Answer first, then refine** (as D38). If a question is skipped, the answer shows
without it and the question stays under the answer; answering it later re-runs only the
code steps (no new vision call, no new lookups), as B2's refine does.

### What we infer without asking

| Fact | From | How sure (evidence) | Said to the person |
|---|---|---|---|
| Setting: pot, trough, raised bed, open ground, windowsill | spot read | reliable; one close-up misread as open ground until context was added (ref §3) | yes, editable chip |
| Pot size band: under 5 L, 5–20 L, over 20 L | spot read | untested; scale is ambiguous in photos | as an assumption, editable chip |
| Medium: bought compost or mineral soil | spot read | one-directional: no compost called soil; 11% of soils called compost (ref §6) | "bought compost" may be stated; "soil" is stated only when the location prior or squeeze agrees |
| Peat vs peat-free | spot read | 2 of 6 right (ref §6) | no |
| Colour band, organic matter high or low | spot read | stable: same material 93% on repeats (ref §6) | in the soil card |
| Texture band prior | 1 km grid: BGS Soil Parent Material | four sources agreed at the test garden (ref §2); farmland-based, blind to imported soil | "the maps suggest clay loam" with the source |
| Lime (free carbonate) | BGS Soil Parent Material | as above | only when present |
| Topsoil pH range | UKCEH Countryside Survey 1 km | modelled for farmland classes, not gardens (ref §2) | as a range, with "a £5 kit settles it" |
| Frost: air-frost nights by month, ground-frost nights a year, coldest-month mean minimum | HadUK-Grid 1 km, 1991–2020 | station-based; beats ERA5 in towns (London 16 vs about 36 nights; ref §6) | yes |
| Coldest night of a typical winter | Open-Meteo ERA5-Land archive, median of 30 annual minima | about 9 km grid, runs cold in towns (ref §2): errs safe for hardiness | as "typical coldest night" |
| Sunshine hours a year | HadUK-Grid 1 km | 1,515 h test garden, 1,560 h London cell (ref §6) | in the spot card |
| Light at the moment of the photo | C1 exposure reading (`light.py`) | physical, factor 2 to 3 (phase C spec) | used only as the sun cross-check (section 6) |

## 4. The two questions and when each is asked (D68, D69)

### Question 1: the compass tap

**Wording:** "Stand at the spot and face the way it gets open sky (away from any wall or
fence behind it). Raise your phone to the top of the tallest thing in that direction,
a fence, hedge or house, or the horizon if there is nothing, and tap."

**What one tap records:** the heading the phone faces (the spot's aspect) and its pitch
(the height of the main obstacle in front, in degrees). Obstacle height drives sun hours
more than orientation does (ref §6, uncertainty), so one tap captures both.

**How:** the DeviceOrientation API, read in the page on the tap.
- Android Chrome: `deviceorientationabsolute` (alpha against north).
- iOS Safari: `DeviceOrientationEvent.requestPermission()` on the tap itself (it must run
  inside a user gesture), then `webkitCompassHeading` and `webkitCompassAccuracy`.
- The phone is held upright with the camera forward, so heading is computed from the full
  alpha/beta/gamma rotation (the W3C worked example), not from a flat-phone heading. The
  probe (section 12, step 0) confirms which formula holds on each OS.
- UK magnetic declination is about ±1°: ignored.
- A live camera preview with a crosshair helps aim at the obstacle top. It costs one
  camera permission prompt; without it the page says "look along the top edge of the
  phone".

**Asked when:** every spot read, unless one of these holds.

| Condition | Instead |
|---|---|
| No orientation sensor or permission refused (desktop, older phones) | after the read, an 8-way tap "Which way does it face?" (N, NE, ... NW, not sure); obstacle height falls back to defaults |
| The spot read says windowsill or indoor | not asked; the tap, if given, is dropped |
| A signed-in person gave a heading for a spot at the same rounded place in the last 60 days (B3 history) | reused, shown as "using your reading from 3 Oct" |

### Question 2: the squeeze test

**Wording:** "Take a pinch of soil from 5 cm down, wet it until it holds together, and
push it out between thumb and finger. What happens?"

| Choice | Means | Band |
|---|---|---|
| Gritty, falls apart, no ribbon | sand dominates | sandy |
| Smooth or soapy, ribbon under 2.5 cm | balanced | loamy |
| Sticky, ribbon 2.5 cm or longer | clay dominates | clayey |
| Skip | | prior stays |

Novices name the lab class 27 to 41% of the time and 71 to 78% counting neighbouring
classes (ref §1, Salley et al. 2018); three bands are coarser than the 12 classes, so the
band call should do at least as well as the neighbour figure. Given, it gets weight 0.75
(session choice, from that range).

**Asked when all of these hold** (the value-of-information rule, D69):
1. The setting is raised bed or open ground, and the medium is not bought compost.
   Pots and troughs never get it: map priors say nothing about a pot (ref §1) and the
   calendar's container rules do not depend on texture.
2. More than one texture band is plausible: some band other than the top one has a prior
   above 0.2 (prior built below).
3. **It changes the answer:** running the grow engine (section 7) once per plausible band
   changes at least one crop in the top 5, or moves one between tiers, or adds or removes
   a "needs a raised bed or grit" warning.

If (1) holds but (2) or (3) fails, the soil card still offers the test as an optional
tap ("Want to check? Squeeze test, 1 minute").

**The texture prior** (session choice, open to change):

| Situation | Prior on the map's band | Neighbouring bands |
|---|---|---|
| Open ground, map band from BGS, cell not urban | 0.70 | 0.15 each |
| Open ground in an urban cell (built-up land cover) | 0.50 | 0.25 each |
| Raised bed (soil likely brought in) | 0.40 | 0.30 each |
| No map value (outside GB, or no polygon) | 1/3 each | |

The photo's sandy/loamy/clayey lean nudges this only when its confidence is 0.5 or more
(right 78% of the time there, n = 37; ref §6): its band is multiplied by 1.5, then the
prior is renormalised. With these numbers, open ground in a rural cell does not pass rule
(2) on its own (neighbours at 0.15), so a map-confident rural bed is not asked unless the
photo lean points to a neighbour (which lifts it to about 0.21); urban cells and raised
beds always pass (2).

**When the squeeze and the maps disagree by two bands** (sandy vs clayey), the squeeze
wins and the soil card says so: "Your test says sandy; the maps say clay. Soil may have
been brought in. We went with your test." The person touched the soil; the map did not.

**Why not the origin question** ("was this soil here already or brought in?", ref
headline): its only use for texture is to weight the map prior, which the squeeze answer
replaces outright, and the setting from the photo (raised bed vs open ground) already
weights it. Its other use, food safety in old urban ground, is covered by the fixed
lead note. Two questions stay the cap.

## 5. Data model (D70)

All new models live in `schemas.py`, beside the ones they extend.

| New or changed | Fields | Fits onto |
|---|---|---|
| `SpotRead` (new) | `setting: Literal["pot","trough","raised_bed","open_ground","windowsill","unknown"]`, `pot_size: Literal["small","medium","large","unknown"]`, `medium: Literal["compost","soil","unknown"]`, `compost_kind` (lean only, never shown), `colour: str` (Munsell-style band), `organic_matter: Literal["high","low_medium","unknown"]`, `texture_lean` + `texture_lean_conf`, `backed_by_wall: bool \| None` | the spot read's reply, like `Observation`; `setting` folds to the existing `Container` (pot, trough → pot; raised_bed, open_ground → ground) |
| `TexturePrior` | `probs: dict[band, float]`, `source: Literal["squeeze","map","map+photo","none"]`, `map_class: str \| None` (BGS label), `urban: bool` | `Spot.texture` |
| `PhRange` | `low`, `high`, `lime: bool \| None`, `source: Literal["ukceh_cs","kit","none"]` | `Spot.ph` |
| `Aspect` | `heading_deg`, `pitch_deg`, `accuracy_deg`, `source: Literal["compass","tapped_direction","history","none"]` | `Spot.aspect` |
| `SunHours` | per month: `(low, mid, high)` clear-day direct-sun hours; `june_class: LightClass \| None`; `method: Literal["compass","direction","defaults"]`; `cross_check: Literal["agrees","disagrees","not_run"]` | `Spot.sun`; `june_class` reuses `LightClass` (sun, part_shade, shade) from C1 |
| `FrostNormals` | `air_frost_by_month: list[float]` (12), `ground_frost_year`, `coldest_month_min_c`, `typical_coldest_night_c`, `sunshine_year_h`, `sources` | `Spot.frost` |
| `Spot` (new) | `read: SpotRead`, `texture`, `ph`, `aspect`, `sun`, `frost`, `notes` | `AnalysisRecord.spot: Spot \| None` (default None keeps old records parseable, as C1 did) |
| `GrowList` (new) | `month`, `good_now`, `worth_a_try`, `coming_up`, `not_here` (each a list of `GrowPick`: crop id, name, what to do this month, chips, reasons, sources) | `AnalysisRecord.grow: GrowList \| None` |
| `Told` | add `squeeze: Literal["gritty","smooth","sticky"] \| None`, `heading: HeadingTap \| None` (validated: 0 ≤ heading < 360, −90 ≤ pitch ≤ 90, accuracy ≥ 0, or an 8-way direction) | user input stays validated at the boundary, as B2 |
| `TellMe` | add `"soil_texture"`, `"aspect"` | `confidence._tell_me` (section 8) |
| Supabase `answers` | `spot jsonb`, `grow jsonb` (one migration) | B3 table |

**Location precision.** Lookups use the rounded location (2 decimals, about 1 km), never
the raw GPS, so a point may land in the neighbouring 1 km cell. Accepted: neighbouring
cells rarely differ in band, and raw GPS stays inside `where.py` (D29).

## 6. Sun hours (D71)

**Geometry, in code, no model call.** `src/herbtwin/sun.py`, pure functions:

1. **Sun path:** solar azimuth and elevation for the 15th of each month, every 10 minutes
   from sunrise to sunset, at the location (NOAA solar-position equations; tested against
   NOAA calculator values).
2. **Horizon profile:** 36 sectors of 10°.
   - Front half (aspect ±90°): the tapped pitch over aspect ±60°, the default beyond.
   - Back half: 45° if the spot read says a wall or fence is right behind it, else 20°.
   - Default with no pitch: 20° (a 1.8 m fence about 5 m away). Session choice.
3. **Hours:** per month, the 10-minute steps with the sun above the horizon sector it
   sits in. These are **clear-day** hours; the HadUK sunshine normal is shown beside them
   ("about a third of days are sunny here in March"), never multiplied in.
4. **Range:** low and high from heading ±15°, pitch ±5° and the defaults ±10°; with an
   8-way tap, heading ±22.5°; with no aspect, every aspect.

**Sun class for the crop filter.** RHS sun categories are defined on summer sun, so the
spot's class comes from its June hours: 6 h or more is sun, 3 to 6 h part shade, under
3 h shade. This follows RHS: full sun is more than 6 h of direct sun at midsummer, partial shade 3–6 h; RHS's moderate (2–3 h) and deep (under 2 h) shade both map to shade (https://www.rhs.org.uk/garden-design/shade-gardening). When low and high fall in
different classes the class is **borderline**. Winter crops (in the ground only Oct to
Mar) also get a note when December hours are under 1 h: "no direct sun Nov to Feb; growth
stops, pick for a spring harvest".

**Cross-check with the photo's light** (C1, already built). When the photo has an EXIF
time and C1's reading is decisive (direct sun at 0.7 of open sky or more, or deep shade
below 0.2), compare it with the geometry's prediction for that minute:
- they agree: `cross_check="agrees"`, no change;
- they disagree: `cross_check="disagrees"`, the range widens to every aspect with the
  tapped pitch, and borderline crops drop to "worth a try". The card says "the photo's
  light did not match the compass; sun hours are less sure".
Bright shade (0.2 to 0.7) never counts as a disagreement: reflected light reads bright on
a sun-averted face (ref §6, the sleeper trap).

**Overcast fallback.** The compass method needs no sun, so an overcast photo (4 of 6 days
in the garden series, ref §6) loses only the cross-check (`not_run`), with no penalty.

**Worked check (S3 test):** on the solved geometry the method must give, within ±1.5 h:

| Spot | Mar / Sep | Jun | Dec |
|---|---|---|---|
| Strip bed (middle) | ~3.6 h | ~9 h | ~0.4 h |
| Herb trough | ~7 h | ~11 h | ~0.8 h |
| Pot row (east-facing wall) | ~6 h | ~8 h | ~0.8 h |
| Corner pot | ~1.4 h | ~5.5 h | 0 |

That is a check that one tap plus defaults reproduces the full solve, not an independent
truth: the solve itself was calibrated (11 of 11 lit/shade after raising the hedge 5°).

## 7. The "what to grow" engine (D72)

**Data:** the 155-crop UK calendar built by `scripts/build_crop_calendar.py` from
`data/crop_calendar/curation.json`: sow indoors, sow outdoors, plant out and harvest
months; container minimums (litres, depth, ground only); sun (full 91, full or part 61,
part or shade 3); soil (`clay_ok` true 79, false 33, unknown 43; `needs_drainage`; pH: any
107, acid required 3); RHS hardiness; overwinters outdoors (yes 77, with protection 26,
no 52); mild-areas-only notes; sources and evidence tier per row (129 C, 26 D).
Calibrated to mid-England frost dates (ref §6, calendar).

**Step 1, window.** A crop is a candidate this month when the month is in its sow
outdoors or plant out months (or sow indoors, shown as "start on a windowsill").
`coming_up` lists next month's starts. Month is the photo's EXIF month, else today.

**Step 2, hard filters** (a crop that fails goes to `not_here` with the reason):

| Filter | Rule | Uses |
|---|---|---|
| Container | in a pot or trough: out if `ground_only` (5 crops); out if the pot size band is below `min_litres` or `min_depth_cm`; with size unknown, kept with "needs at least N L" | `SpotRead.pot_size` |
| Sun | out if the spot's June class is below the crop's (`full` needs sun; `full_or_part` needs part shade or better); borderline → "worth a try" | `SunHours.june_class` |
| Frost, sowing and planting | a frost-tender crop (RHS hardiness H1–H3 in `hardiness_rhs`; tender annuals with no rating such as basil or courgette count as tender) planted or sown outdoors this month is out if this month's air-frost normal is 0.5 nights or more. `overwinters_outdoors="n"` is NOT used here: 18 of its 52 rows are hardy spring-sown crops (main peas, spring onion sets, potatoes, summer radish) | `FrostNormals.air_frost_by_month` |
| Hardiness, overwintering | for a crop left out over winter: out if its RHS rating's minimum is above the typical coldest night; in a pot, one rating less hardy (RHS: containers get colder; metal worst, ref §4); `with_protection` → kept with "fleece in cold spells" | `typical_coldest_night_c` |
| Mild areas only | `mild_areas_only` is free text in today's curation (38 rows, e.g. "October-November and February outdoor sowings are for milder areas"). S4 first adds a structured `mild_months` list per row (filled from that text and reviewed by hand); a month in `mild_months` then counts only where annual air-frost nights are 30 or fewer (London 16 passes; test garden 53 does not). Session choice | `FrostNormals` |
| pH (ground only) | `acid_required` is out where the pH range's low end is above 6.0 or lime is present; in a pot it stays with "use ericaceous compost" | `PhRange` |

**Step 3, soil fit (ground only), demotes rather than excludes** (soil can be fixed):
`clay_ok=false` or `needs_drainage` on a spot with P(clayey) ≥ 0.5 → "worth a try" with
"raised bed, modules or grit" (garlic, onions, strawberries, Mediterranean herbs, ref §4);
`clay_ok=true` on clay → a "suits clay" chip.

**Step 4, tiers and order.**
- `good_now`: passes every filter on the mid estimates **and** on the low ones, no soil
  demotion, sources agree on this month.
- `worth_a_try`: passes on mid but not low (borderline sun, unknown pot size), a soil
  demotion, a mild-area window, or sources disagree.
- Within a tier: sun margin (June hours over the class threshold), then evidence tier
  (C before D), then months to first harvest (shorter first). At most 8 shown per tier.
  No model call ranks or writes the list; the page text is built from the row's facts.

**Source disagreements.** 48 crops have a logged disagreement between RHS and Garden
Organic (ref §6). When this month is inside one source's window and not the other's, the
crop is "worth a try" with both windows named: "RHS: November to March. Garden Organic:
September to April." That is the rhubarb case, the one RHS October pick the calendar
missed.

**Uncertainty on the page.** Each pick carries four chips, each with its source:
- Sun: fits / borderline / unknown (from compass, direction or defaults);
- Soil: fits / fix needed / not known (squeeze, maps or none);
- Frost: fine / fleece / not needed (HadUK, ERA5-Land);
- Timing: now / from next month / sources differ.
The spot card lists every assumption with where it came from, and each skipped question
sits under the list as "Point your phone to firm up sun" / "Squeeze test to firm up soil".
No "N in 10" is shown for the list: there is no outcome data to measure it (section 9).

**Expected for the test garden strip bed in October** (to be confirmed by S4's tests,
not a claim): if the spot read calls it a raised bed, the squeeze is asked; maps say clay loam; June about 9 h, so
sun; 1.4 air frosts in October, 53 a year, so not a mild area. December sun is about 0.4 h,
so winter crops get the "no direct sun Nov to Feb" note. Good now: garlic (clay: modules
or grit) and spring cabbage plugs. Worth a try: shallots (only if the squeeze is not
sticky) and rhubarb (sources differ). Left out here: broad beans in October (a
`mild_months` sowing; sow in March) and winter salads (better in a sunnier pot). This
matches the hand-built garden plan in `data/external/probes-2026-10-12/garden-plan/`.

## 8. Confidence and "tell me" (D73)

**The plant answer gains two factors**, hand-set and small like C1's `light` (no data to
fit them), recorded as hand-set in `data/confidence/weights.json` provenance:

| Factor | Chip | Effect | Weight (proposed) |
|---|---|---|---|
| `soil_texture` | Soil | missing when unknown; raises when a squeeze band (or a strong map prior on open ground) supports a watering or drainage call for a plant in the ground; lowers when clay contradicts `water`; neutral for pots | raises 0.1, lowers −0.2 |
| `sun_geometry` | Light | feeds `light.light_factor` as a stand-in class when there is no multi-visit class: the spot's June class from a compass tap | uses the existing `light` weights; no new weight |

The `soil_feel` factor (2 cm down, B2) is untouched: it is moisture now, not texture.

**`_tell_me` gains two options,** competing on weight with the three it has:
- `aspect` ("If you point your phone the way it faces, I can tell you how much sun it
  gets") when the action is `move_light` or `leave_normal`, the plant is outdoors and
  there is no light class; weight = `light.raises` + `plant_model.raises` / 2;
- `soil_texture` ("If you do a 1-minute squeeze test, I can tell you how it drains") when
  the plant is in the ground and the action is `water` or `dont_water`; weight =
  `soil_texture.raises` (0.1, the new factor's own weight above).

**The grow answer's own confidence** is the tiers and chips above, not the measured
level scale. Its factors map onto the same chip names (Soil, Light, Weather, Season) so
the strip looks the same, but it shows no "N in 10" until section 9's data exist.

## 9. Evaluation (D74)

Public data first; the test garden is a supporting check (memory: public data first).

| What | Data | Measure | Target | Cost |
|---|---|---|---|---|
| Soil texture prior | LUCAS 2018 topsoil, GB points with lab texture and pH (free ESDAC form, personal licence; Kash signs) | BGS band vs lab band; UKCEH pH range vs lab pH | band accuracy above the "always loamy" baseline; pH inside the range at least 70% | $0 |
| Spot read: setting, medium | 141 public soil photos (`data/external/soil-photos/`); the 114 labelled garden photos (the private working repo's `garden_photos.csv` scene column) | setting accuracy; medium in both directions | setting ≥ 90%; no compost called soil | about $0.25 |
| Solar geometry | NOAA calculator values at 3 UK points × 4 dates | azimuth and elevation error | under 0.5° | $0 |
| Sun hours | the worked case (section 6); held-out garden photos with C1 readings not used in the hedge calibration | hours within ±1.5 h; lit/shade agreement on held-out photos | 4 of 4 spots; ≥ 80% agreement | $0 |
| Compass | step 0 probe: 10 taps at 3 garden spots, one beside the metal trough, against the solved axis (191° down the garden, 11° west of south) | heading error | median under 15°, worst under 30° | $0 |
| Grow list | RHS monthly "sow and plant now" pages (eval labels only, never shipped) × 12 months × 4 settings | recall of setting- and pot-fitting RHS picks within good now and worth a try; hard errors; recall in the top 8 (reported, not gated) | tier recall ≥ 0.85; hard errors 0 | $0 |
| Ask rate | simulation: 500 random GB land points × 5 settings × 12 months | share of reads that ask the squeeze; share of asks where some plausible answer changes the top 5 | the second is 100% by construction; report the first | $0 |

**Amended 12 Oct (Kash), after the S4 eval:** top-8 recall of 0.7 cannot be reached (a
perfect ranker scores 0.49, as RHS lists 35+ picks in March and April), and the frost
rules below contradicted RHS's own spring picks (peas, potatoes, lettuce, radish). The
frost filter now holds a tender crop back only by the months this place's last spring
(first autumn) frost runs later (earlier) than mid-England's, and the frost hard error
covers warm-season crops only: frost-tender and never outdoors before May (courgette,
tomato, beans, squash). Detail: `data/external/probes-2026-10-12/grow-recall/FINDINGS.md`
(local) and PR #93.

**Hard errors** (any one fails the grow gate): a warm-season crop (as amended above)
listed outdoors in a month with 0.5 or more air-frost nights; an acid-requiring crop listed for limy or
alkaline ground; a `ground_only` crop listed for a pot; a crop listed for a pot below its
minimum size when the size is known.

**Supporting checks on the test garden:** Kash's squeeze test on the raised bed (pending,
the only texture ground truth we have, ref §7); the strip bed, trough, pot row and corner
pot run through the full flow with their solved geometry.

## 10. Data sources and licences (D75)

| Source | Licence | Ships in the app? | How it is held |
|---|---|---|---|
| BGS Soil Parent Material Model 1 km | OGL | yes, with "Contains British Geological Survey materials © UKRI" | rasterised onto the 1 km grid file |
| UKCEH Countryside Survey topsoil pH 1 km | OGL | yes, with UKCEH credit | same grid file |
| Met Office HadUK-Grid 1 km normals 1991–2020 | OGL; needs a free CEDA login to download | yes, with "Met Office HadUK-Grid, via CEDA" | same grid file |
| Open-Meteo ERA5-Land archive | CC BY 4.0 (data), free API | yes, live call, cached per cell | not stored beyond cache |
| UK crop calendar (our curation) | facts with citations; no source prose (README "Licence and use") | yes, with each row's source links reachable from the page | `curation.json` in git; built `calendar.json` (decision in section 13) |
| Plant Variety Database | CC BY 4.0 | yes, attributed where days-to-harvest is used | as now |
| Soilscapes (LandIS identify) | terms not checked | **no** until checked; drainage then comes from the texture band | eval only |
| ISRIC SoilGrids | CC BY 4.0 | not used at run time: null over built-up cells, 3–12 s | eval only |
| Practical Plants (PFAF) | treat as CC BY-NC-SA | **no** | dev only |
| LUCAS 2018 topsoil | ESDAC personal licence, no redistribution | **no** | eval only |
| RHS pages | RHS copyright | facts and links only; month lists as eval labels | never stored as text |

**The grid file.** One build script writes a compact land-only 1 km British National Grid
file holding: BGS texture band and carbonate, UKCEH pH, HadUK air frost by month, ground
frost a year, coldest-month mean minimum and sunshine a year. It sits in
`data/external/spot-grid/` (gitignored, like the sources) and is copied into the image by
the private working repo's `deploy.sh`. The BNG transform already written in `scripts/haduk_normals.py`
moves into `src/herbtwin/bng.py` so the app and the script share it. With the file
missing, the spot answer says "soil and frost maps are not available here" and the
offline tests use a small fixture grid.

## 11. Risks and what would change the plan

- **A phone compass in a garden may be off by more than 30°** (metal troughs, steel
  fences, uncalibrated sensors). This is the riskiest assumption: sun hours, the strongest
  filter, rest on it. Probed first (section 12, step 0). If the median error is over 30°,
  the 8-way tap becomes the main input and the compass a convenience.
- **People may not aim at the obstacle top**, giving a pitch of 0°. The pitch is clamped
  to the default when under 5° and the spot read sees a fence or hedge.
- **Map priors miss made ground,** above all in cities: BGS has London values, but a
  London garden may sit on decades of imported soil. Urban cells get the weaker prior
  (section 4) and raised beds weaker still.
- **The squeeze test needs dirty hands and damp soil.** Many will skip. Then soil-sensitive
  crops stay "worth a try" and the list leans on clay-tolerant picks.
- **Mid-England windows** run 2 to 3 weeks early for the north and late for Cornwall
  (calendar README). The frost filter catches tender crops; hardy crops' windows are not
  shifted.
- **The grid file's size** in the Cloud Run image is unmeasured. If it is over 100 MB,
  store it at 2 km or keep only England and Wales.
- **Time.** Phase D runs to 23 Oct and the submission week starts 24 Oct. S1 to S6 below
  are about 4 to 5 days of build. If they do not fit before 30 Oct, the spot answer ships
  as a smaller cut (S1, S3, S4: compass plus grid plus list, no squeeze and no spot read)
  or after the submission.

## 12. Build plan (D76)

Each step is one PR (branch named), built in order; S2 and S3 touch disjoint files and
may run in parallel.

| Step | Branch | Delivers | Proves it |
|---|---|---|---|
| 0 | none (probe, throwaway) | a one-page probe on the live HTTPS site: tap to record heading, pitch and accuracy | Kash taps 10 times at the strip bed, the trough (metal) and the pot row; compare with the solved axis and the obstacle pitch from ref §6. $0, about 10 minutes of Kash's time |
| S1 | `chore/spot-grid-file` | `src/herbtwin/bng.py`; `scripts/build_spot_grid.py` (BGS, UKCEH, HadUK onto one 1 km grid); `spot_priors.py` lookup; fixture grid | offline tests: the transform, the lookup, the missing-file path; the two worked points give ref §2 and §6's values |
| S2 | `feat/spot-read` | the spot read: its own prompt and schema (`stages/spot.py`), run beside observe in spot mode | recorded fixtures offline; paid: 114 garden photos + 141 public, about $0.25 |
| S3 | `feat/sun-hours` | `sun.py`: sun path, horizon, monthly hours with range, June class, C1 cross-check | NOAA values; the worked case table within ±1.5 h |
| S4 | `feat/grow-engine` | calendar loader, window, filters, soil demotion, tiers, disagreements; `evals/grow.py` | a test per filter and per hard error; the RHS 12-month recall run |
| S5 | `feat/spot-questions` | the two question cards, DeviceOrientation script, 8-way fallback, `Told` fields, the value-of-information rule, refine reuse, `soil_texture` and `sun_geometry` factors, `_tell_me` options | the rule asks only when the list changes (table tests); the 500-point ask-rate simulation; factor tests |
| S6 | `feat/spot-page` | the "What can I grow here?" entry, soil and spot cards, grow list with chips, attributions, JSON API, Supabase columns | page check on the 4 garden spots; offline tests on rendering and missing data |
| S7 | `docs/spot-eval-results` | the evaluation table filled in (LUCAS when Kash's form clears) | the numbers |

Checks per PR as phases B to D: `uv run ruff check . && uv run ruff format --check .`,
`uv run pytest -q`, the step's paid check quoted first; a fresh code-reviewer on each
diff before Kash's merge prompt.

## 13. Decisions for Kash

| # | Proposed | Kash |
|---|---|---|
| D67 | The flow: separate "What can I grow here?" entry; compass asked during the photo read; answer first, skipped questions stay under it | approved 12 Oct 2026 |
| D68 | Two questions only: compass tap (heading and obstacle pitch in one tap) and squeeze test; the origin question dropped | approved 12 Oct 2026 |
| D69 | The squeeze is asked only for soil in the ground, when two bands are plausible and the list changes between them | approved 12 Oct 2026 |
| D70 | The data model in section 5, stored on the record and in Supabase | approved 12 Oct 2026 (planning: spot answers get their own `spots` table, since `answers.plant_id` is required) |
| D71 | Sun hours from geometry with defaults; the C1 light reading as the only cross-check; no vision model for sun | approved 12 Oct 2026 |
| D72 | The grow engine: filters, soil demotion, two tiers, disagreements shown | approved 12 Oct 2026 |
| D73 | Two hand-set confidence factors and two "tell me" options for the plant answer | approved 12 Oct 2026 |
| D74 | The evaluation in section 9, with LUCAS via the ESDAC form (Kash signs) | approved 12 Oct 2026; the ESDAC form is not signed, so LUCAS stays an optional later eval |
| D75 | Ship only OGL, CC BY and our own curation; Soilscapes and PFAF stay out | approved 12 Oct 2026 |
| D76 | Build order S1 to S7 after the step 0 compass probe | approved 12 Oct 2026: S0 to S7 before the 30 Oct submission |

**Open questions, answered by Kash on 12 Oct 2026:**
1. **When:** before the 30 Oct submission, the full build (S0 to S7), not the smaller cut.
2. **`calendar.json`:** committed to git at `data/crop_calendar/calendar.json` (facts and
   links), rebuilt by `scripts/build_crop_calendar.py`; tests and deploy need no RHS cache.
3. **The ESDAC form for LUCAS 2018:** not signed. LUCAS stays an optional later evaluation
   (its soil photos are unpublished anyway, ref §6).
4. **Phones for step 0:** the Galaxy S24+ (Android Chrome, `deviceorientationabsolute`),
   and an iPhone if one is to hand.
5. **The 2026 warmth note:** shown on the grow list, short: "This season is running warm
   (Met Office record), so windows may run late."

Merges for this build are autopilot under Kash's grant (a fresh code-reviewer on each PR,
every check green). Planning changed two details, recorded with the rest in the plan's
"Decisions taken while planning": the grid file is committed to git (3.4 MB) rather than
copied in by the private working repo's `deploy.sh` (section 10), and spot answers get their own `spots`
table (section 5, D70).

Details not put to Kash, chosen by this draft and open to change: the texture prior
numbers, the 0.2 plausibility line and the 1.5 photo nudge (section 4); the squeeze weight 0.75; the horizon
defaults 20° and 45°; the ±15° heading range; the June-hours class thresholds (RHS-based, see section on sun class); the 0.5 air-frost-night threshold; the 30-night mild-area line;
one hardiness rating off for pots; at most 8 picks per tier.
