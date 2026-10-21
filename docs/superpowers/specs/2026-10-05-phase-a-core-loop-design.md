# Phase A: the new core loop, design spec

Agreed with Kash on 5 Oct 2026, section by section, in session `phase-a-design-kickoff`.
Roadmap: the private working repo's `2026-10-04-roadmap.md` (phase A, 5 to 11 Oct). Original
design: `docs/superpowers/specs/2026-10-02-herb-digital-twin-design.md`. Decisions are
numbered from D26 (D1 to D25 live in the plan 2 documents). Evidence for each decision
is in section 11 and in the private working repo's `2026-10-05-docs-phase-a-core-loop-design.md`.

## 1. Intent

Kash's purpose: help someone understand what to do for their plant, **including "do
nothing, this is normal for this time of year"**; gather everything possible from other
sources and ask only what cannot be got another way; give clear actions, the reasons,
**what would happen if they did each**, and an honest confidence built from every factor.

Phase A delivers the mint case end to end: a photo of mint that looks dead in October
gives "Leave it. This is normal for October", with what happens if you leave it, water
it or cut it back, a confidence word and number, and the factors that raised or lowered
it.

**In scope:** one answer engine replacing `advise` + `recommend`; season, weather, care
facts and plant model feeding it; consequences per action; factor-built confidence; the
location chain (the one ask phase A adds); the photo's own date; the new results screen;
a test per factor; expert match held.

**Out of scope (later phases):** soil feel and last-watered questions, the typed question,
plant history and follow-up chat (B); light from exposure, reminders, outcome scoring (C);
deploy (D).

## 2. Flow (D27)

```
photo ─► observe (GLM-5.3-Flash: species, condition, soil surface, indoor/outdoor,
      │           pot/ground, photo quality)
      ├► where and when: photo GPS → phone location → typed place → none; photo date
      ├► research (care facts)        ├► weather (14 days back, 14 ahead)
      ├► season: normal_for(matched name, photo month, "UK")
      ├► plant model (twin): 14-day outcome per mapped action
      ├► advise ×3 (Nemotron Super; everything above in the prompt)
      ├► consequences (per action: plant model, outcome table, or "no reliable data")
      └► confidence (code: factors → word + measured "N in 10" + strip)
         ─► Answer ─► results page / JSON
```

- **One engine.** `advise` (tested against experts) is the only decider. `recommend` and
  its template block are retired; `twin` stays as the plant model and becomes evidence.
- **Asked three times** (D27): one call at temperature 0 and two at 0.7, in parallel.
  The primary is the majority; with no majority, the temperature-0 answer. Agreement
  (3/3, 2/3, 1/3) is a confidence factor. Reason: even at temperature 0 the primary
  changed on repeat 32% of the time (section 11.1).
- **Reply format unchanged** (`Advice`: actions, primary, answer, ask, confidence
  high/low). Asking for extra fields broke the format on 30 to 46% of replies and cost 2
  to 3 points of accuracy (section 11.1). Everything new is computed in code around it.
- **Model:** Nemotron Super (`nvidia/nemotron-3-super-120b-a12b`), the advisor measured
  against experts. The app's `recommend` model setting (Ultra, untested) goes.

## 3. The parts

| Part | Does | New / changed |
|---|---|---|
| `species.py`, the plant-name matcher (D32) | One vocabulary replacing three (`research.py` SYNONYMS, `evals/report.py` COMMON_NAMES, norms `common_names`). Splits "Rosemary (Salvia rosmarinus)" into both names; tries full name, binomial, then genus ("rosa x" → `rosa`; "Mentha sp." → `mentha`). A genus never borrows a species norm: it resolves only to a genus-level entry. Returns the matched key plus how it matched (exact, binomial, genus, none). | New |
| `observe` | Adds `setting: indoor \| outdoor \| unknown`, `container: pot \| ground \| unknown`, `photo_quality: good \| poor` with `quality_note` (blurred, dark, plant small, several plants). | Changed |
| Where and when | Location chain (section 6) and the photo's own date (EXIF `DateTimeOriginal`, else the file's `mtime`, flagged). | Changed |
| Season | `normal_for(matched key, photo month)`; UK only (outside the UK box: no norm). Returns the norm or "no norm". | New (uses #49) |
| `advise` | Same reply format. The prompt gains: WHERE (indoor/outdoor, pot/ground), WEATHER (last 14 days summary, today, next 7 days, frost nights), SEASON (status, normal signs, problem signs, next change; or "no norm for this plant"), CARE FACTS, PLANT MODEL (each mapped action: better/same/worse than leaving it, and why). Called ×3; adapter gains a `temperature` argument (fixed at 0 today in `openai_compat.py`). | Changed |
| Consequences (D34) | Per action. Plant-model actions: better/same/worse than leaving it plus a short why (days until dry, waterlogged by, frost nights), in code. Prune/treat/feed/repot: the sourced action-outcomes table (#51), `outcome_for(plant, action, month, problem)`. **Prune:** the table row. **Treat** (`treat_or_remove` in `OutcomeAction`): only when a problem is named; the advisor prompt lists `problems_for(plant)` so it can name one, and the name is matched whole-phrase in its answer (never a near miss). **Feed/repot:** the row for this month, or, when the plant has rows for other months only, "best done in <months>" from those rows. Otherwise "no reliable data on what this changes". **No extra model call.** Literature lines are marked "less sure". | New |
| `confidence.py` (D26, D28) | Factors → score → level, measured "N in 10", factor strip, "if you tell me X" line (section 5). Weights in `data/confidence/weights.json`, fitted by `scripts/fit_confidence.py` with provenance (sets, n, date, AUROC). | New |
| `Answer` | Replaces `Recommendation` in `AnalysisRecord` and the JSON API (section 7). | Changed |
| Web | Location chain on the form, photo date, layout B v2 (section 8). | Changed |

**Plant model action mapping:** `water_now`, `water_lightly` → `water`; `do_nothing` →
`leave_normal`; `bring_indoors`, `move_to_shade` → `shelter`; `move_to_sun` →
`move_light`. Indoors (from `observe`) the plant model and frost are switched off; in
the ground its weight drops (it assumes a 25 cm pot).

**Genus-level norms (D32):** `mentha` gets 12 genus rows (all UK garden mints die back to
the rhizome) at one tier lower; already on main (#51, `norms_uk.json`). Measured: 6 of 25
GLM mint names (24%) are genus-only or a hybrid and would otherwise get no norm. The
matcher work must rebuild `data/eval/sets/seasonal_uk.jsonl` (32 mint-rust items get
`norm_key` "mentha") and update `tests/test_seasonal_set.py:95-96, :116`, which still
assert None, in the same change.

## 4. Data flow and the advisor prompt

The advisor sees facts, not instructions from data: norm text, care facts and weather
are quoted as data blocks. The system prompt keeps D24/D25 (always a best action; the
soil check with every watering answer) and adds: "Use SEASON to decide whether what the
photo shows is normal now; if the photo shows a listed problem sign, it is not normal."
A risk measured in section 11.1: `leave_normal` is the advisor's most common primary and
right only 0.26 to 0.34 of the time. The season block could push that further; section 10
measures it with and without the block.

## 5. Confidence (D26, D28)

**Built in code; the model is never asked for a number.** Start from the chosen action's
track record against experts (its measured hit rate as primary), then add each factor's
weight:

| Factor | Raises | Lowers | Missing |
|---|---|---|---|
| Advisor | said high | said low | — |
| Agreement (3 asks) | 3 of 3 | 1 of 3 | — |
| Format repair needed | — | yes (repaired answers right 0.30 to 0.34 vs 0.40 to 0.44) | — |
| Species | top-1 ≥ 0.7, exact match | < 0.4, genus-only match, not a plant | — |
| Photo quality | — | poor | — |
| Season | photo sign listed as normal now (for leave it) | sign listed as a problem; no norm (for leave it) | no norm, outside UK, no location |
| Season evidence | tier A or B | tier D | — |
| Plant model | its outcome backs the action | disagrees (water, shelter, leave) | indoors, no weather |
| Plant model margin | far from a tipping point | within 2 days of one | — |
| Pot or ground | pot (model fits) | ground (model weight down) | unknown |
| Weather | forecast available (water, shelter) | — | fetch failed, no location |
| Forecast distance | frost/dry call within 3 days | call 8+ days out | — |
| Weather explains symptom | yes (e.g. wilting after 10 dry warm days; basil blackened after a night below about 10 °C) | — | — |
| Care facts | verified | generic fallback | — |
| Soil | surface visible and consistent | surface contradicts the action | soil feel (phase B asks) |
| Indoor / outdoor | known | — | unknown (weather and plant model weigh less) |
| Light, history | — | — | always missing in phase A |

- **Weights:** advisor, agreement, repair and track record are fitted on the expert sets
  (cross-fitted between Stack Exchange and MIRAGE). The rest are set by hand, each with
  a direction test, and re-checked on the seasonal set and Kash's garden labels.
- **Levels (3), each tied to what to do:** "Not sure: check first", "Could go either
  way: do the quick check first, or take the low-risk step", "Likely right: go ahead,
  and keep an eye on it" (renamed 16 Oct from "Fairly sure" and "Sure", which
  over-claimed at 5 and 7 in 10). The number shown is the **measured** hit
  rate of that level ("about 6 in 10"), never a guess; today's best top level reaches 6
  to 7 in 10, so no level claims 9.
- **Strip** (shown as chips): Season, Photo, Plant model, Agreement, Weather, Soil, Light,
  History, each ▲ raised, ▼ lowered or ? missing.
- **"If you tell me X, I can tell you Y":** the missing factor with the largest weight
  for the chosen action (usually soil feel for watering; location when none was given).
  Phase A shows the line; phase B asks.
- **Season timing (D33):** no general "season running early or late" factor. Weather
  signals and people's records (iNaturalist "this year near you", Woodland Trust Nature's
  Calendar) added nothing beyond the calendar date (sections 11.3 and 11.6), and on
  herbaceous plants frost added nothing overall either (11.8), nor did landscape greenness
  from satellite (11.9). **One narrow use stays:** in the norm's first dieback month only (the month whose status first includes
  `normal_dieback`, or `next_change_month` of the month before), nights below 5 °C in the
  last 14 days are a small hand-set factor for "leave it, normal dieback": cold nights
  raise it, none lower it. Near the change point that separated dead from alive at 0.64
  vs 0.52 for the date alone (11.8). Shown in the strip under Weather ("3 cold nights this
  fortnight"). Cold nights also stay as symptom evidence (basil blackening).

## 6. Where and when (D29, D30)

- **Location chain:** (1) photo EXIF GPS, silent; (2) browser geolocation, one tap; (3) a
  typed town or postcode via the Open-Meteo geocoding API (free, no key); (4) none: the
  answer still comes back with weather, plant model and season missing and confidence
  lower, plus "tell me where" in the "if you tell me" line. No IP lookup. This moves the
  once-only location ask from phase B into phase A.
- **Privacy:** coordinates are rounded to 2 decimals (about 1 km) before anything is
  stored or logged; raw GPS is never kept. Photos are not stored (cases keep meta only).
- **Season region:** inside a GB + Ireland box (lat 49.8 to 61.0, lon -10.7 to 1.9) the
  UK norms apply; outside it, season is "missing".
- **Developer default:** `HERBTWIN_HOME_LAT/LON` becomes optional and is used only as the
  last fallback when set (Kash's local testing); deploy leaves it unset.
- **Date:** the photo's EXIF date (`cases.read_taken_at`) when present, else its `mtime`
  (for a fresh upload, about the upload time) with a "date assumed" note. Today `web/app.py:44` uses upload time.

## 7. The Answer

```python
class Factor(BaseModel):
    name: str  # "season", "photo", "plant_model", ...
    effect: Literal["raises", "lowers", "missing"]
    detail: str  # "mint dies back in October (RHS, tier D)"


class ActionCard(BaseModel):
    action: CareAction
    when: Literal["today", "this_week", "keep_an_eye"]
    because: str  # one line naming the evidence
    if_you_do: str  # consequence, or "no reliable data on what this changes"
    if_you_do_from: Literal["plant_model", "outcome_table", "norm_rule", "none"]
    less_sure: bool  # literature-based consequence


class CompareRow(BaseModel):
    action: CareAction
    vs_leaving_it: Literal["better", "same", "worse", "unknown"]
    why: str


class Answer(BaseModel):
    headline: str  # "Leave it. This is normal for October."
    do: list[ActionCard]  # at most 3; primary first, tagged "today"
    dont: ActionCard | None  # the tempting move the plant model rates worse
    watch: str  # from the norm's problem signs: what would change this
    tell_me: str | None  # "If you tell me X, I can tell you Y"
    level: Literal["not_sure", "fairly_sure", "sure"]
    in_ten: int  # measured hit rate of the level, 1..10
    factors: list[Factor]
    compare: list[CompareRow]  # every choice vs leaving it (closed card on the page)
    runs: list[Advice]  # the 3 advisor replies, for audit
    assumptions: list[str]
```

Time tags come from code: primary "today"; other actions "this week"; the watch line
"keep an eye on". The primary card's "because" is the advisor's answer, first sentence;
other cards take theirs from the norm or outcome row. The "Don't" card appears only when
the plant model rates a tempting action (usually watering) worse than leaving it.

## 8. Results screen (D31)

Layout B, revised (mockups in the session's visual companion, `results-layout-v2.html`):
plant and where/when on top; the headline; the confidence chip and factor strip; **Do**
cards, each with its "because" and one "→ if you do" line; a **Don't** card when there is
one; **Keep an eye on**; the "if you tell me" box; then two closed cards: **Compare all
choices** (every action vs leaving it: better, same or worse, and why) and **Weather,
plant model and sources**. Phone first. The old observation-scores table and risk table
move inside the second closed card.

## 9. Errors

- `observe` fails or says "not a plant": no answer; the page says what went wrong.
- One or two of the three advisor calls fail: answer from the rest; agreement shows the
  real denominator ("2 of 2"). All three fail: the page shows what was seen and "could
  not form advice"; the failure is recorded.
- Weather, research, season or plant model fail: that factor shows "missing", confidence
  drops, the answer still comes back (as today's partial-failure handling).
- Location none or outside the UK box: weather/plant model and/or season missing, said
  plainly.
- Every caught error is logged with the real exception; nothing is swallowed.

## 10. Testing (D35)

1. **One test per factor (free, offline):** for each row of the factor table, flip only
   that input (season known vs missing, species sure vs unsure, indoor vs outdoor, pot vs
   ground, plant model agrees vs disagrees, ...) and assert confidence moves the stated
   way; plus property tests (adding a missing factor never lowers confidence for an
   action it supports).
2. **Units:** the name matcher on the GLM name formats seen in cached runs; majority vote
   and tie rule; the plant-model action mapping; consequences source selection; the
   location chain (EXIF with and without GPS, rounding, geocode failure); photo date;
   the Answer built from mock advisor replies; the page renders each block.
3. **Expert match (paid, about $0.60):** the merged advisor ×3 on the same Stack Exchange
   150 and MIRAGE 200 questions (context blocks marked "not available"). Must hold
   primary match at or above 0.413 and 0.445 (within the interval), and must not raise
   the `leave_normal` share.
4. **Season (paid, about $1.40):** the seasonal set (#50), UK subset as the headline, with
   and without the SEASON block. Must beat the month-only shortcut (76%); confidence must
   be higher on correct "normal" answers than on wrong ones; "no norm" items scored apart.
5. **Confidence honesty:** fit the weights, then report the measured "N in 10" per level
   on held-out data; re-fit whenever weights or the prompt change.
6. **Kash's garden** (round 2 labels, about 10 Oct): supporting check, mint first (the
   public set has no UK "normal" mint).

## 11. Evidence behind the decisions (5 Oct)

All runs against expert primary actions; AUROC = how well a confidence separates right
from wrong answers (0.5 coin, 1 perfect); 95% bootstrap intervals. Throwaway code stayed
in the session scratchpad; spend recorded in the session report.

**11.1 How to build confidence (D26), Nemotron Super, $1.57.**

| Method | Stack Exchange 150 | MIRAGE 200 |
|---|---|---|
| Model's own high/low | 0.58 [0.51, 0.64] | 0.63 [0.57, 0.69] |
| Model states a number out of 10 | 0.60 [0.50, 0.69] | 0.72 [0.65, 0.79] |
| Code: agreement over 3 asks + action track record | 0.71 [0.62, 0.79] | 0.68 [0.60, 0.75] |
| **Mix: code + model's high/low** | **0.72 [0.63, 0.79]** | **0.73 [0.66, 0.80]** |

The stated number was overconfident (says about 6.5 in 10, right about 4 in 10) and
unsteady on repeat (same level 56%, same number 41%); the extra fields needed repair on
30 to 46% of replies and lowered primary match (0.413 → 0.390, 0.445 → 0.414).

**11.2 Literature lines (D34), 51 real advisor answers (prune, treat, other on norms
plants), Claude Sonnet blind judge with A/B swapped (agreement 45 of 51), $0.002.** A
broad code template was worse than saying nothing (8 to 10 of 51 correct and useful; 40%
of its lines invented a fact; treat lines 0 of 4 usable). Nemotron Nano beat that
template, but where the template was empty it roughly tied "no reliable data" and its
real lines invented facts 50 to 88% of the time. Hence: no model call; narrow rules; a
sourced outcomes table.

**11.3 Early or late season (D33), 278 UK and Irish iNaturalist observations, Aug to
Dec.** Month alone AUROC 0.89; a date-and-group baseline 0.937; adding cold-night counts
changed it by -0.002 to +0.001 and the temperature anomaly by -0.001 (all intervals span
zero). Mostly maples; underpowered for herbs.

**11.4 Genus names (D32):** 6 of 25 GLM mint names genus-only or a hybrid.

**11.5 Format repair as a factor (D28):** repaired answers right 0.30 (SE) and 0.34
(MIRAGE) vs 0.40 and 0.44 clean.

**11.6 People's records (D33), free.** iNaturalist "this year near you" (leave-one-out
share of coloured or bare records within 50 km, same fortnight, vs earlier years; n
6,069 UK/Irish observations, 722 positive): gain over a date baseline +0.0006
[-0.0004, +0.0016]; best case (50 km only) +0.003. Nature's Calendar (downloadable
without an account; 27,712 autumn tinting and bare-tree records, thin after 2019): gain
-0.0001 to +0.003, intervals span zero. Herbs and ferns have too few autumn records (29
positives) to say more.

**11.7 The outcomes table (#51) on the same 51 cases, same blind judge, free.** Coverage 15 of 51:
prune 14 of 17, treat 1 of 17 (people describe symptoms rather than name the problem; some
named problems have no row), feed/repot 0 of 17 (rows exist but not for the case's month).
Where it has a line it beats "no reliable data" 10 to 4 (judge agreement 14 of 15) and the
old template 8 to 2; no wrong-problem match; Nano lines were flagged for invented facts
55% of the time vs 10% for the table. Hence the two follow-ups in the consequences row:
let the advisor name the problem from the plant's known list, and say "best done in
<months>" when only the timing is wrong.

**11.8 Frost on herbaceous plants (D33), USA-NPN open status data, free.** 171,785 visits
(1,199 sites, 437 forb species; herbs 9,067 visits, 133 sites, mostly Monarda, Artemisia,
Agastache; no Mentha). Over a baseline of date, month, latitude and species group (AUROC
about 0.81), every frost or cold-night feature gained -0.015 to +0.004 (intervals span
zero). Within 14 days of each site's usual dieback date: herbs, nights below 5 °C in 14
days 0.64 [0.57, 0.72] and frost has happened 0.59 [0.53, 0.65], against 0.52 for the date
alone; all forbs 0.60 and 0.55. US continental climates, not the UK.

**11.9 Landscape greenness (D33), Sentinel-2 via Copernicus Data Space, free.** Does "plants
in general near you are greener or browner than usual" help herbs? Median NDVI in a 2 km
box over the 30 days before each USA-NPN record (2017 to 2025, Aug to Dec), vs the same
window in other years at that site; 340 sites, held-out-site CV. Gain over the date
baseline: herbs +0.001 [-0.004, +0.005] (7,009 rows, 120 sites); all forbs +0.001
[-0.001, +0.003]; within 14 days of the change point herbs -0.003 [-0.026, +0.019], all
forbs +0.021 [-0.003, +0.042] (gone with a 15-day window). On the same rows cold nights
still gain +0.068 [+0.021, +0.133] near the change point for herbs. Copernicus HR-VPP
season start and end dates (reachable with the CDSE keys as a Sentinel Hub collection,
2017 to 2024) on 1,576 UK iNaturalist rows: +0.002 and +0.000. Cloud gaps (about 4 clear
days a window) and mixed land cover in the box limit it. About 16% of the monthly free
quota.

## 12. Dependencies and gates

- **Merged:** #49 seasonal norms (`src/herbtwin/seasonal.py`), #50 seasonal eval set
  (`data/eval/sets/seasonal_uk.jsonl`, labels carry `norm_key`, `uk`, `country`), #51
  action outcomes (`src/herbtwin/outcomes.py`: `outcome_for`, `problems_for`; and the
  `mentha` genus norms).
- **Deploy note (phase D):** the Dockerfile copies only `src/`; `data/seasonal/`,
  `data/outcomes/` and `data/confidence/` must be copied too.

## 13. Cost

Per photo: GLM photo reading about $0.0007, the advisor ×3 about $0.003, everything else
free: **about $0.004 a photo** (about $4 per 1,000). Test runs (sections 10.3 and 10.4)
about $2 in total, within Kash's rule ($2 a run without asking, $15 cap).

## 14. Decisions

| # | Decision | Kash |
|---|---|---|
| D26 | Confidence is built in code from factors; the model's high/low, agreement over 3 asks and the action's track record are factors; the model is never asked for a number | "Yes" |
| D27 | One engine: `advise` sees everything and decides; asked ×3; `recommend` retired; the plant model is evidence | "Yep" |
| D28 | Added factors: indoor/outdoor, pot/ground, photo quality, care facts verified, season evidence tier, weather explains the symptom, format repair, plant-model margin, forecast distance | "agree with them all" |
| D29 | Location chain (GPS → one tap → typed place → none), 1 km rounding, no IP lookup | "Sure" |
| D30 | The photo's own date | "Yes" |
| D31 | Results screen layout B v2 | "sure" |
| D32 | One plant-name matcher with genus fallback; genus-level `mentha` norms | approved after test |
| D33 | No general "season early or late" factor (weather, people's records, frost and satellite greenness all tested); one narrow cold-nights factor in the norm's first dieback month | "Yes to both", "yes to doing more tests"; set on evidence |
| D34 | No extra model call for literature lines; narrow code rules now; a sourced action-outcomes table | "Yes to both" |
| D35 | Testing plan (section 10) | "Sounds good" |
| D36 | The advisor does not see the SEASON block; the norm still sets the headline, the season factor and the watch line. Measured on the UK seasonal set (3 asks, n 83): with the block 0.735 (problems caught 57%), without 0.759 (70%); the block pushed leave_normal and missed real problems | "yes go for it" (5 Oct, evening) |
