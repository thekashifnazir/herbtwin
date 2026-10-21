# Action outcomes (UK): what happens if you prune, treat, feed or repot

What happens if you do a care action now, per plant and month, so the app can show a
sourced consequence beside each recommended action instead of a guessed one. For watering
and moving a plant the plant model computes the consequence; for these four actions there
is no model, so each line comes from published guidance. Built 5 Oct 2026.

- Data: `data/outcomes/outcomes_uk.json`, 218 rows.
- Code: `src/herbtwin/outcomes.py`. `outcome_for(plant, action, month, problem=None)` takes
  the scientific key or any common name the seasonal norms know (any case). For
  `treat_or_remove` the problem must equal the row's `problem` or one of its
  `problem_aliases` (case-insensitive, whole phrase): "rust" on mint is mint rust, on a
  rose rose rust, on chives leek rust. **An unmatched plant, action, month or problem
  returns `None`**, which means "no reliable data", never the nearest row. For prune,
  feed and repot the `problem` argument is ignored. `problems_for(plant)` lists the named
  problems a plant has rows for.
- Each row: `months` it holds for, `if_you_do` and `if_you_dont` (at most 30 words each),
  `caution`, `evidence_tier`, `sources` (URLs, at least one).

## Coverage

| Action | Rows | Notes |
|---|---|---|
| prune | 44 | split by season where advice differs, including "not now" rows (Japanese maple February to June: cuts bleed sap). Harvesting is not pruning: for sage, purple sage, rosemary, thyme, bay and oregano, months outside the pruning window say "Light picking only" and name the window |
| feed | 31 | growing-season rows, plus "not now" winter rows where a source says so (aloe, moth orchid, pothos, snake plant, monstera, fiddle-leaf fig) |
| repot | 26 | spring rows, plus "best avoided" autumn and winter rows for the potted Mediterranean herbs and bay. Oregano's runs November to February only: RHS says to divide it after flowering in late summer or early autumn, so September and October stay open |
| treat_or_remove | 118 | 2 to 5 named problems per plant (median 4) |

All 29 seasonal-norms plants are covered, plus the `mentha` genus (an unnamed mint), which
repeats the spearmint rows one tier lower: the RHS mint guide and the mint pest and
disease pages speak of mint generally.

Problems covered (rows): root rot 15, spider mites 12, aphids 10, vine weevil 9, scale
insects 9, sage and Ligurian leafhoppers 8, mealybugs 8, slugs and snails 6, powdery
mildew 6, rosemary beetle 4, mint rust 3, mint moth 3, then one or two each of leek rust,
rose rust, black spot, blue mint beetle, capsid bugs, bay sucker, basil downy mildew, grey
mould, carrot fly, celery leaf mining fly, allium leaf miner, rose leaf-rolling sawfly,
cuckoo spit, verticillium wilt, coral spot, acer leaf scorch, whitefly, thrips, fungus
gnats and tarragon rust.

## How it was sourced and checked

Six research passes, one per plant group, fetched RHS pages first (grow-your-own, plant
growing guides, pest and disease pages), then university extension (Clemson HGIC, NC
State, UConn, Wisconsin, Maryland, Utah State) and the American Orchid Society. 212 of
218 rows cite an RHS page.

A spot check then found about one row in four claiming more than its page said (for
example "no fungicides are available" where RHS says it recommends not using them). So a
second pass re-read **every row against the raw page text** and fixed 64 of them: hedges
restored ("may", "can", "some species"), months narrowed to what the page states, clauses
the page doesn't support removed, and a few tiers lowered. None needed dropping.

Rules held throughout: no product names and no doses unless the source gives them; when
sources disagree, the cautious wording. Examples: Japanese maple pruning July to October
is a "wait for leaf fall" row because two RHS pages disagree; the RHS advice against
pesticides and fungicides is kept as a caution; spider-mite advice to raise humidity is
left off the snake plant and aloe rows because their own RHS pages say not to mist them.

## Tiers

Tiers follow `risk-models.md`. **C** (176 rows): an RHS or extension page states the
action, its consequence and the season. **D** (42): the months are our mapping of vaguer
wording, the advice comes from a general page applied to this plant (the RHS repotting
guide for the herbs' winter rows), the plant is the `mentha` genus, or the row extends
houseplant spider-mite advice into November to February (RHS: mostly a pest from March
to October, though a heated greenhouse can see damage at any time of year; a
heated home is read as the same case; those winter rows name Amblyseius, which RHS says
survives winter better than Phytoseiulus). No A or B: no trial data was sought.

## Gaps

- **No row (returns None):** feed for lemon balm, garlic chives, thyme, coriander and
  dill; repot for basil, coriander, dill (annuals, sown afresh), parsley, rose and ZZ
  plant; prune for aloe. `tests/test_outcomes.py` pins this list.
- **Problems left out for lack of a plant-specific source:** onion white rot on chives
  (RHS gives prevention only), allium leaf miner on garlic chives, powdery mildew on mint,
  bay powdery mildew, maple aphids and Phytophthora root rot, basil whitefly and root rot,
  damping off, fern crown rot, fungus gnats on most houseplants, thrips except on
  fiddle-leaf fig, scale and spider mites on Christmas cactus, mealybugs on ZZ plant.
- **Root rot rows describe the watering change**, not a cure: sources say how to stop
  roots rotting (let compost dry, never stand the pot in water, shelter pots from winter
  rain), not how to save a plant whose roots have rotted, so `if_you_do` is worded as
  prevention ("helps prevent root rot").
- Outdoor timing is for lowland southern England, as in `seasonal-norms.md`.
- Garlic chives rows rest on chives pages (tier D); tarragon feed rests on a Utah State
  page (tier D).
- Months for pests outdoors follow the RHS pest page; a problem reported outside those
  months returns None rather than a row written for another season.

## Phase B1 actions (5 Oct)

Phase B1 (D43) split feed and repot out of "other" and added `change_soil`, `mulch`,
`humidity`, `rotate`, `check_pests` and `isolate`. 28 rows were added, all tier C, each
from an RHS page except two (ZZ plant humidity and peace lily pest checks: Clemson HGIC).
Five rows were checked against their pages by hand (thyme grit, acer mulch, fig
top-dressing, rosemary beetle, rose mulch after feeding).

| Action | Plants |
|---|---|
| mulch | acer, chives, male fern, bay, soft shield fern, rose (spring and after the midsummer feed), thyme (grit) |
| humidity | spider plant, snake plant (not advised), pothos, fiddle-leaf fig, monstera, moth orchid (summer), Christmas cactus, peace lily, ZZ plant (not needed) |
| rotate | snake plant, peace lily |
| change_soil | acer (root prune and fresh compost), fiddle-leaf fig (top-dress), bay, moth orchid (fresh bark) |
| check_pests | bay, monstera, rose (leaf-rolling sawfly), rosemary (rosemary beetle), peace lily |

**Gaps:** no mulch row for rosemary, sage, mint, lemon balm, tarragon or oregano (their RHS
pages do not say); rotate only where RHS says it; no `isolate` row (the one candidate was
about quarantining a new plant, not a sick one). Thyme mulch holds all year and rose
summer mulch is June to July, our reading of "then mulch" after the midsummer feed.
Sources and fetch notes: the private working repo's `archive/` copy of the B1 research report.
