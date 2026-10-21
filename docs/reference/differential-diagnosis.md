# Differential diagnosis: telling look-alike problems apart

The cues that separate causes which look the same in a photo, with the classic failure
first: overwatering and underwatering both cause wilting. Swept 3 Oct 2026 from eight
extension and RHS pages, three Wikipedia extracts and a few abstracts; several extension
sites refused automated fetches. Rows marked **[unsourced]** are general horticultural
knowledge not verified in this sweep. No open-licence visual nutrient key was found, and
no study measuring how often people or apps confuse over- and under-watering.

## Sources and licences

| Key | Source | Licence position |
|---|---|---|
| S1 | NC State Extension Gardener Handbook ch. 7 Diagnostics, content.ces.ncsu.edu/extension-gardener-handbook/7-diagnostics | NC State copyright; CC BY tags on the page are for figures only |
| S2 | same handbook ch. 1 Soils and Plant Nutrients, Table 1-4 | same |
| S3 | same handbook ch. 18 Plants Grown in Containers | same |
| S4 | UMD Extension, Overwatered Indoor Plants, extension.umd.edu/resource/overwatered-indoor-plants | copyright, facts only |
| S5 | UW-Madison, Edema, hort.extension.wisc.edu/articles/edema/ | copyright |
| S6 | UW-Madison, Fungus Gnats on Houseplants; Houseplant Care | copyright |
| S7 | RHS, Frost damage | copyright, facts only |
| S8 | RHS, Nutrient deficiencies | copyright, facts only |
| S9 | Ohio State, 20 Questions on Plant Diagnosis (PLPATH-GEN-3), ohioline.osu.edu/factsheet/plpath-gen-3 | copyright 2017 |
| S10 | Wikipedia: Etiolation, Edema (plants), Leaf scorch | CC BY-SA 4.0 |
| S11 | Else et al. 1995, Plant Physiology, doi:10.1104/pp.109.3.1017 (abstract) | |
| S12 | Siddiqua et al. 2022, Agronomy, doi:10.3390/agronomy12081869 (abstract) | CC BY 4.0 |
| S13 | Forestry Research 2025, doi:10.48130/forres-0025-0007 (abstract) | CC BY |

All copyrighted sources are paraphrased here; nothing is copied.

## Symptom table

| Symptom | Most likely causes | Discriminating cue | Source |
|---|---|---|---|
| Wilting | drought; overwatering or root rot; vascular problem | **not separable from foliage alone**; excess water shows the same symptoms as root rot or drought. Soil moisture decides it. | S4, S1 |
| Wilting with yellowing of lower and inner leaves | overwatering (root hypoxia) | the primary overwatering sign; scorch and leaf drop follow later | S4 |
| Wilting with brown crisp margins | underwatering; soluble salts; xylem problem | marginal burn points to lack of water, salts or a transport problem; compost shrunk from the pot wall confirms drought | S1, S4 |
| Why wet roots wilt | hypoxia | low oxygen damages fine roots so the plant cannot take up water; in tomato, flooding cut root hydraulic conductance and leaf water potential fell within 2 hours | S4, S11 |
| Corky or translucent blisters under older leaves | oedema | blisters on undersides turning tan and corky; linked to wet warm soil, humid cool air, low light; not a pest | S5, S10 |
| Small dark flies around the pot | fungus gnats | commonly associated with overwatered plants | S6 |
| Soft, foul-smelling base or roots | root or crown rot | rot often smells; root-rot pathogens are a likely sign of overwatering; healthy roots are white or tan | S1, S6, S3 |
| Green algae on compost, mushy stem base, slow onset, no recovery after watering | overwatering | conventional cues | **[unsourced]** |
| Rapid collapse with a dry light pot, recovering within hours of watering | underwatering | conventional cue | **[unsourced]** |
| Uniform pale yellow, older leaves first | nitrogen deficiency | nitrogen is mobile; yellowing spreads old to young; plant spindly | S2, S8 |
| Purple or red on older leaves, dark green, stunted | phosphorus deficiency | mobile; underside and veins; worse in cold or waterlogged compost | S2, S8 |
| Margins of older leaves yellow then burnt | potassium deficiency | mobile; edge browning on mature leaves | S2, S8 |
| Interveinal yellowing on older leaves, veins green | magnesium deficiency | mobile; induced by high-potash feed | S2, S8 |
| Interveinal yellowing on youngest leaves, may whiten | iron deficiency | immobile; also triggered by poorly drained or oxygen-poor soil and high pH | S2, S4 |
| Distorted or cupped young leaves, dead growing tips | calcium deficiency | limited mobility; shoot tips affected | S2 |
| Long weak stems, long internodes, small pale leaves | low light (etiolation) | stretching toward light; pallor evenly distributed | S10 |
| Bleached or burnt patches on leaves facing the sun | sunburn | direct sun burns delicate tissue even at comfortable temperatures; sun-facing-only pattern is **[unsourced]** | S3 |
| Water-soaked dark green, then black; stems collapse | frost | tender foliage blackens after first frost; young growth scorched between veins on exposed and top edges | S7 |
| Damage on tender plants after cold exposure | chilling injury below 10 °C | may appear quickly or weeks later; ask about history | S3 |
| Heat scorch on margins of the exposed side | heat or drought | browning of margins and tips; exposed-side pattern **[unsourced]** | S10 |
| Random spots or hot spots, spreading over time | biotic | living problems start small and spread; abiotic damage does not spread and appears all at once | S1 |
| Uniform damage across the plant or across several species | abiotic | uniform distribution or several plant families affected suggests environment; one family suggests pest or pathogen | S1 |
| Spores, mildew, ooze, insects, frass, webbing | biotic, as a suspect | a sign makes the organism a suspect, not the proven cause | S1 |
| Spot type | fungal vs bacterial vs viral | dry spots with structures inside are fungal; water-soaked spots turning tan are often bacterial; mosaic suggests virus | S1 |
| Autumn yellowing or dieback of a perennial | normal senescence | ask what is normal for the plant first; old leaves pick up fungal spots at end of life; shortening days induce hardening and low temperature drives senescence | S9, S1, S7, S13 |

## Decision tree for the observe and recommend prompts

- **Step 0. What is normal?** Identify the plant and its habit (variegation, deciduous, annual or biennial, season). In autumn, for a herbaceous perennial or an annual at the end of its cycle, consider senescence before stress. See the "October to November, normal" column in `herb-care-packs.md`.
- **Step 1. Signs present?** Insects, webbing, frass, mildew, mould, ooze.
  - Yes: biotic suspect. Still check watering; gnats and root rot point back to overwatering.
  - No: go to step 2.
- **Step 2. Distribution.**
  - Whole plant, uniform, sudden: abiotic or a root or stem problem. Go to step 3.
  - Random spots or patches, spreading: likely biotic. Classify the spot type.
  - Lower parts only: shade, or disease progressing upward.
  - One side only: light or temperature exposure. Ask which side faces the sun, a wall or a draught.
- **Step 3. Wilting?** Do not guess. Ask for soil moisture at finger depth and pot weight.
  - Wet or heavy: overwatering. Supporting cues: lower and inner leaves yellow, oedema, gnats, sour smell, soft base.
  - Dry or light, compost pulled from the pot wall, crisp margins: underwatering.
  - Moist and neither: root-bound, salts, heat, vascular disease.
- **Step 4. Chlorosis without wilting.** Which leaves?
  - Old leaves: uniform is nitrogen; interveinal is magnesium; margins are potassium; purple is phosphorus.
  - New leaves: interveinal is iron (check waterlogging and pH first); distorted tips are calcium.
  - All leaves pale with stretched stems: low light.
- **Step 5. Necrosis.**
  - Black, water-soaked, after a cold night: frost or chilling.
  - Bleached or tan patches on the sun-facing side: sunburn.
  - Margins only: drought or salts.
- **Step 6. Output.** Give the top two causes with the one check that separates them. Never give a single confident cause for wilting from a photo alone.

## What a photo can and cannot show

| Evidence | Where it comes from |
|---|---|
| which leaves are affected, chlorosis pattern, margin vs patch necrosis, leggy growth, oedema (if the underside is shown), visible pests or mildew, compost shrunk from the pot edge, standing water in a saucer | **visible in a photo** |
| soil surface wetness (dark compost looks wet either way), limp vs crisp texture, algae or mould on compost, gnats | **sometimes visible, low confidence** |
| soil moisture at depth, pot weight, smell, drainage holes, days since last watering, recovery after watering | **must ask the user** |
| onset speed, spread over time, a recent cold night, a move, repot or feed, whether neighbours show it | **must ask (history)** |

**Rule.** If wilting or generalised yellowing is the main symptom, ask the soil-moisture
question before naming a cause. The sources themselves say the foliage symptoms overlap.

## How the pipeline uses this

- The twin breaks the tie the photo cannot: a pot the bucket says is near capacity with a
  wilting plant points to overwatering; a pot the bucket says is depleted points to
  drought. This is the strongest argument for having a twin at all.
- "Ask the user one question" is a valid recommendation and must score well on the
  uncertainty rubric line (see `evaluation-methods.md` section 7).
- The 20 cm rule for raters: the same decision tree is the instruction sheet for Toloka
  raters, so judges, raters and the model argue from the same cues.

## Published frameworks

S1 is a 10-step diagnostic procedure with symptom-to-cause lists; S9 is the "20 questions"
guide. Both are copyrighted; paraphrase, do not copy. S12 reviews plant-disease apps across
three app stores; its abstract gives no confusion rate. Bailey-Serres and Voesenek 2008
(doi:10.1146/annurev.arplant.59.032607.092752) is the standard flooding-physiology review.
