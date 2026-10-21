# Phase C: follow up and learn, design spec

Agreed with Kash on 6 Oct 2026, section by section. Roadmap:
the private working repo's `2026-10-04-roadmap.md` (phase C, 16 to 20 Oct). Phase B spec:
`docs/superpowers/specs/2026-10-05-phase-b-ask-and-remember-design.md`. Decisions are
numbered from D47 (D37 to D46 live in the phase B spec).

## 1. Intent

Phase B remembers each plant. Phase C makes the app **learn from what it remembers**: it
reads how much light the plant gets from the photo itself, checks on the next photo
whether the last advice worked, and, with the person's permission, pools those checks so
confidence can later be refitted on real outcomes.

**In scope:** light from the photo (C1); follow-up and scoring of earlier advice (C2);
opt-in to share scored pairs (C3).

**Out of scope:** re-photo reminders (moved to phase D, D47: they need a scheduled job,
which belongs with deploy, possibly as a Nebius Serverless Job); the confidence refit
itself (waits for about 50 scored pairs); the side modules (Nemotron vision on Nebius AI
Cloud, fine-tuning a small model), which get their own specs.

**Success:**
- A daylight garden photo with exposure data gets a light class (sun / part shade /
  shade), the light factor is no longer always "missing", and the advisor sees a LIGHT
  block.
- The side-by-side comparison meets the step-0 bar in section 4 through the real code
  path (direction right on at least 9 of 10 public change pairs, at most 1 false change
  in 10 same pairs).
- A signed-in person's second photo, inside the window for the earlier main action,
  asks "did you do it?" once and stores a result.
- The pooled export contains only opted-in users' pairs and no photo, user id or typed
  text.
- With no Supabase keys set, the app behaves as today apart from C1, and every offline
  test passes.

## 2. Shape (D47)

One spec, three PRs, built in order. C2 and C3 both touch the history tables and the
answer page, so they run one after another.

| PR | Branch | Delivers |
|---|---|---|
| C1 | `feat/light-from-photo` | Exposure read, sky ratio, light class, light factor, LIGHT block |
| C2 | `feat/score-earlier-advice` | Frozen prediction per answer, "did you do it?", side-by-side result, `advice_scores` |
| C3 | `feat/share-scored-pairs` | `user_settings`, the one-time ask, the export script, privacy text |

## 3. C1: light from the photo (D50, D51)

**Read (in `where.py`, beside the date and GPS reads):** from the EXIF IFD,
`ExposureTime`, `FNumber`, `ISOSpeedRatings`, `ExposureBiasValue`, `BrightnessValue`,
`Flash`, `DateTimeOriginal` and `OffsetTimeOriginal`. All 83 garden photos (Galaxy S24+)
carry every one of these; none carries GPS or a compass direction.

**Light at the plant:** EV100 = log2(N² / t) − log2(ISO / 100), corrected by the exposure
bias; lux ≈ 2.5 × 2^EV100 (verified on 2 Oct: 11k at 10:00, 41k at 12:00, 100 at dusk;
error a factor of 2 to 3). When shutter, aperture or ISO is missing but `BrightnessValue`
is present, EV100 = Bv + 5 (APEX). The probe (section 3a) found the two routes agree
within 0.17 EV on all 83 garden photos; a disagreement of more than 1 EV is logged and the
shutter route wins.

**Open sky:** the environment stage adds Open-Meteo's hourly `shortwave_radiation` (free,
verified 6 Oct) for the photo's date, interpolated to the photo's minute (each hourly
value is the mean of the hour before its label). The hour comes from `DateTimeOriginal`
with `OffsetTimeOriginal`, so summer time is exact. Sky lux ≈ W/m² × 120.

**One photo says "now", not "this spot" (D53).** fraction = photo lux / sky lux. A single
photo gives the light **at that moment**: in direct sun (fraction about 0.7 or more), bright
shade (about 0.2 to 0.7), or deep shade (below about 0.2). The probe showed a spot's
reading is steady over minutes but moves with the sun over the day (the pot row read 0.08
to 0.35 in shade and 1.6 to 2.1 in direct sun at 10:27 and 12:32 on 2 Oct), so one photo
cannot say whether a spot is sunny. Cut-offs are confirmed in the C1 plan against the
garden photos.

**The plant's light class builds over visits.** For a signed-in plant, each visit's "now"
reading is kept with its time (in the stored answer). With readings at two or more
different hours, the plant gets a class: sun (direct sun at most daylight readings), part
shade (direct sun at some hours, shade at others; the hours are named, e.g. "morning
sun"), or shade (no direct-sun reading). Signed-out, or with one reading, the class is
"not known yet" and only the "now" reading is used.

**Missing, as today, when:** no exposure data by either route; the hour is unknown; sky
below about 50 W/m² (dusk, night); the flash fired; or the fraction is above 3 (no real
plant gets three times open-sky light; the probe's three such readings, 3.4 to 7.7, were
not sky in frame, and a pixel check for sky found none of them, so the pixel check is
dropped).

**The plant's need:** `KnowledgePack.sun` (`full`, `partial`) and the RHS position read
in B5 (`full sun`, `partial shade`, `full shade`) map onto sun / part shade / shade;
anything else is "unknown".

**Light factor (D51, session choice, open to change):** modelled on the soil-feel factor.
It uses the plant's class when known, otherwise the "now" reading only when it is direct
sun or deep shade at midday (10:00 to 15:00 local). It raises confidence when light
supports the chosen action (for example `move_light` and a sun-loving plant reads shade,
or `leave_normal` and light matches need), lowers it when it contradicts the action
(`move_light` when light already matches need), and is neutral otherwise. The weight is
hand-set and small, recorded as hand-set in `data/confidence/weights.json` provenance;
there is no data to fit it.

**LIGHT block for the advisor** (fenced like the others, data not instructions): "At 14:00
the plant was in bright shade (about 30% of open-sky light). One moment only: it may get
sun at other times. Earlier visits: direct sun at 10:30 and 12:30, shade by 16:00, so
morning sun. Rosemary wants full sun."

**Indoor photos:** the same fraction is computed and reported ("well below open sky, as
expected indoors"); no class is built, since window light varies across a room.

**Tests:** offline tests on fixture EXIF (each tag missing in turn, the BrightnessValue
route, flash, bias, offset times), the "now" cut-offs, the over-3 drop, building the class
from several readings, the factor effects and the block text. A free script,
`scripts/check_light.py`, runs over the garden photos (public proxy point, not the garden)
and prints fractions and "now" readings per spot and time.

### 3a. Probe result (6 Oct, free, throwaway)

83 garden photos, Open-Meteo hourly sky at a public proxy point: no flash on any photo;
BrightnessValue route minus shutter route mean +0.01 EV, sd 0.06, max 0.17; fraction
quantiles p10 0.13, p50 0.30, p90 1.75; photos minutes apart at one spot agree, the same
spot moves from about 0.1 in shade to about 2 in direct sun across a day.

## 4. C2: follow-up and scoring (D48, D54)

**Gap closed first:** today the "if you do" lines are text only and are not saved with
the answer, so there is nothing to score against. C2 adds a **prediction**, saved inside
the stored answer at the moment it is given, so a later score tests what was actually
said.

**How a change is seen (D54, after probes b and c, section 4a):** not by reading each
photo on its own and subtracting (the single-photo reading misses droop on soft herbs).
Instead the vision model sees **both photos side by side** and says whether the later one
is more, less or the same on one signal. Each comparison is made **four times**: two
prompts (plain; with each photo's time of day and C1 light "now") in both orders (earlier
first, later first). A change counts only when all four agree; any disagreement, an
answer below medium confidence, or a token overrun (retried once at a higher budget) is
**can't tell**. About $0.002 per follow-up. The model is the current vision model; Gemma
is ruled out (it favours one position whatever the order).

**Prediction rules** (a small table in code, each row with a source; the C2 plan fixes
the wording):

| Main action | Signal compared | Expected | Window |
|---|---|---|---|
| `water` | posture (droop) | less droop, or same if none before | 1 to 7 days |
| `dont_water` | posture (droop) | not more droop | 1 to 7 days |
| `leave_normal` | dead or browning tissue | not clearly more | 3 to 21 days |
| `shelter` | dead or browning tissue | not more | 3 to 21 days |
| `treat_or_remove`, `prune`, `isolate` | dead or browning tissue | not more (less sure) | 3 to 21 days |
| `move_light`, `feed` | leaf colour | same or greener (less sure) | 7 to 21 days |
| `repot`, `change_soil`, `mulch`, `humidity`, `rotate`, `check_pests`, `ask_first`, `other` | none | not scored | |

Posture comparison is proven by probe c. Tissue and colour comparisons are **gated**: the
C2 plan's step 0 runs the same four-call check on pairs for them (public series and
garden pairs); a signal that fails is stored as "not scored yet" and its rows stay in the
table for later. Watering works in hours to a day (the parsley recovery on 2 Oct showed
within four hours), so its window is shorter.

**At the follow-up photo:** when the person picks a plant on "which plant is this?" (or
before taking the photo, from My plants), the page shows the earlier photo with "Take it
from the same spot, at about the same time of day if you can." Probe c found almost every
false change came from a different camera angle or framing.

**The ask:** when the new photo is linked to a visit inside the window for its main
action, the answer page asks once: "On 2 Oct we suggested watering. Did you do it?" with
yes / partly / no / skip. It is one of the phase B questions under the answer, not a gate
before it.

**Result:** the comparison gives **improved / no clear change / worse / can't tell**
against the prediction. It is also **can't tell** when:
- C1 light "now" puts one photo in direct sun and the other in shade (harsh sun causes
  temporary droop; on 2 Oct the parsley recovery coincided with the move into shade);
- either photo is poor, or the species reading differs between them;
- the person chose skip.
"No" (did not do it) stores the comparison as **not done**, with no verdict on the
advice (useful later as a comparison). One-step changes (the mint on 2 Oct) are below
what the comparison resolves; they come out as no clear change or can't tell, and that is
accepted.

**Storage:** a new table `advice_scores` (earlier answer id, later answer id, action,
prediction, signal, did-it, result, the four raw answers, prompt version, model, scored
at), owner-only under row-level security like `plants` and `answers`, and removed with
the account.

**Shown:** one line in the history ("Last advice: water (you did it). Since then: less
droop."), and the same line in the advisor's HISTORY block. "Can't tell" is shown as
"couldn't tell from these two photos" with the reason.

**Tests:** offline tests of the rules, the four-call agreement, each did-it value, the
window edges, the light-mismatch and poor-photo cases, with a scripted mock model; RLS
checks added to the private working repo's `rls.sh`; and a paid check, `scripts/check_scoring.py
--yes-paid` (about $0.20), that re-runs probe c's pairs through the real code path and
must meet the step-0 bar below.

**Step-0 bar (C2 plan):** on probe c's pairs, the four-call rule gets the direction right
on at least 9 of 10 public change pairs, gives at most 1 false change on 10 same pairs,
and calls the 3 parsley recoveries "improved" (or "can't tell" when the light check
fires). Below the bar, C2 ships as data collection only: did-it and both photo ids are
stored, no result is shown.

### 4a. Probe results (6 Oct, throwaway, $0.21 in all)

- **b, single-photo reading ($0.03, 20 garden crops read twice):** `water_stress`
  identical 18 of 20, but 15 crops read 0 every time and both disagreements were on the
  5 above 0; agreement with the owner's v1 scores exact 7 of 20 (Spearman 0.30); 0 on
  every mint and lemon balm crop the owner scored 2; a prompt change moved one crop by 2.
  Report the private working repo's `2026-10-06-probe-reading-stability.md`.
- **c, side by side ($0.18, 39 pairs in both orders):** on 10 public change pairs
  (Fittonia, blossom, lettuce; wheat left out because the model read its on-screen angle
  labels), direction right 20 of 20 calls; but one call reports a change on 10 of 20
  same-pair calls, almost all from a different viewpoint. Four calls agreeing: 9 of 10
  right, 0 of 10 false changes, 7 of 13 garden pairs can't tell. Adding the species'
  natural habit did not help (comparing a plant with itself already allows for it);
  adding time and light helped a little. Report
  the private working repo's `2026-10-06-probe-pairwise-droop.md`.

## 5. C3: opt-in to share scored pairs (D49)

**Store:** a new table `user_settings` (user id, `share_scored_pairs` default false,
`asked_at`), owner-only, removed with the account.

**Ask:** once, just after the first sign-in: "Help improve advice for everyone? We'd share
how past advice turned out, never your photos." Yes / No. Changeable on My plants. (C2 needs the stored photos from B3; signed-out checks are never compared.)
Signed-out users are never asked: without an account there is no earlier visit to score.

**Pool:** `scripts/export_scored_pairs.py` reads only opted-in users' `advice_scores` and
writes, per pair: a random pair id (not the user id), species, month, region (coarser
than the stored rounded place), the before and after signals, action, prediction, did-it
and result. No photos and no typed text (typed questions can carry personal details). It
reads across users, so it uses the Supabase admin key, run by Kash locally (session choice;
D39 used the admin key only for delete).

**Withdrawal:** the export is rebuilt from scratch at every refit and never kept, so
switching off takes effect at the next refit.

**Refit:** not in phase C. The script reports counts per action; the refit waits for
about 50 scored pairs.

**Also:** the consent text on the index page and `docs/SUPABASE.md` gain the sharing
sentence.

**Tests:** RLS checks for `user_settings`; the export leaves out non-opted users, user ids
and typed text; the ask appears once and not again after an answer.

## 6. Error handling

- Missing or odd EXIF never fails an answer: light goes to "missing" and the reason is
  logged.
- An Open-Meteo hourly failure leaves light "missing"; the daily weather path is
  unchanged.
- A scoring or settings write failure is logged and the answer is still shown; the
  did-it ask stays answerable on the next visit.

## 7. Decisions

| # | Decision | Kash |
|---|---|---|
| D47 | Phase C as three PRs: C1 light, C2 scoring, C3 opt-in; reminders move to phase D; side modules get their own specs | "sounds good" |
| D48 | Scoring compares the new photo's reading with the earlier prediction; the person is asked only "did you do it?"; follow-ups count at 3 to 21 days | "A" |
| D49 | Opt-in shares scored pairs only, no photos, off by default, asked once at sign-in | "A" |
| D50 | Light = photo lux / open-sky lux for that place and hour, as sun / part shade / shade against the plant's need | "A" |
| D51 | Fill light gaps from metadata: offset time, flash, exposure bias, BrightnessValue, a pixel check for sky in frame (the pixel check dropped by D53) | "yes" |
| D52 | Sections 2 (C2) and 3 (C3) as presented | "yes if these make sense", "sure sounds good" |
| D53 | After the light probe: one photo gives light "now"; the plant's light class builds from readings at different hours over visits | "yes" |
| D54 | After probes b and c: C2 compares the two photos side by side, four calls must agree, results improved / no clear change / worse / can't tell, same-spot prompt at follow-up, light mismatch = can't tell | "do that follow up, we are well within budget and it's worth it" |

Details not put to Kash, chosen by the session and open to change: the light-factor
effects (section 3), the "now" cut-offs and the over-3 drop (set in the C1 plan),
the per-action windows (D48's 3 to 21 days, shortened to 1 to 7 for watering and lengthened at the start for colour), the gating of tissue and colour comparisons (section 4), the 50-pair refit threshold, and the
admin-key export.
