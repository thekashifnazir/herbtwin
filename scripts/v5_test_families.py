"""The round-4 TEST sentences (v5) with the author's strict reading: the secondary gold.

160 sentences written by a fresh agent that never saw the checker; the author added the
direct reading after pre-registration part 2 froze the code. The primary gold is a new
blind labeller's. `G` is build_judge_v4.F with round-4 conditions; `N` is a near-miss: the
sentence's action is close to ours (`near`) but not the same advice, so the states carry
our action and the gold is no.

Condition keys beyond v4's: whitefly, leaf_spot, spider_mite, powdery (named problems),
soil_moist, trait (a quality of the plant: never confirmed), strong (a strength word:
never confirmed).
"""

from __future__ import annotations

import build_judge_v4 as v4
from build_judge_v4 import DW, LN, ML, NONE, PR, SH, TR, W

v4.CONDS.update({
    "whitefly": ("problem", "whitefly"), "leaf_spot": ("problem", "leaf spot"),
    "spider_mite": ("problem", "red spider mite"), "powdery": ("problem", "powdery mildew"),
    "soil_moist": ("soil", "moist"), "trait": (None, None), "strong": (None, None),
})  # fmt: skip
v4.FORM_COND.update({
    "whitefly": ("named_problem", "whitefly"), "leaf_spot": ("named_problem", "leaf spot"),
    "spider_mite": ("named_problem", "red spider mite"),
    "powdery": ("named_problem", "powdery mildew"), "soil_moist": ("soil_wet", "damp"),
    "trait": ("plant_trait", ""), "strong": None, "other": ("other", ""),
})  # fmt: skip
v4.SEASONS.update({
    "late spring": (5, 5, 5), "early spring": (3, 3, 3), "early summer": (6, 6, 6),
    "mid-summer": (7, 7, 7), "late summer": (8, 8, 8), "mid-autumn": (10, 10, 10),
    "March": (3, 3, 3), "April": (4, 4, 4), "May to September": (5, 6, 7, 8, 9),
})  # fmt: skip


def G(sentence, plant, says, kind="do", conds=(), season=None, **form):  # noqa: N802
    if "conditions" not in form:
        form["conditions"] = [v4.FORM_COND[c] for c in conds if v4.FORM_COND[c]] + (
            [("month_range", season)] if season else []
        )
    return v4.F(sentence, plant, says, kind, conds, season, **form)


def N(sentence, plant, near, action, kind="do", conds=(), season=None, **form):  # noqa: N802
    fam = G(sentence, plant, NONE, kind, conds, season, action=action, **form)
    fam["near"] = near
    return fam


GRP = {"applies_to": "plant_group"}
GEN = {"applies_to": "general"}
TEST = [
    G("Trim leggy thyme back to just above the leafy growth in late spring.", "thyme", PR, conds=("trait",), season="late spring"),
    G("If whitefly infest mint on a conservatory windowsill, spray the undersides of the leaves with soapy water.", "mint", TR, conds=("whitefly", "indoors")),
    G("Pick off and dispose of every rosemary beetle you can find.", "rosemary", TR, conds=("beetle",)),
    N("Harvest mint by cutting whole stems rather than picking individual leaves.", "mint", PR, "harvest"),
    G("Many people cut sage right back in autumn, only to lose it in a cold winter.", "sage", PR, kind="fact"),
    G("Keep mint in its own pot rather than among vegetables such as potatoes, where it will run riot.", "mint", NONE, action="none"),
    N("Pick rosemary sprigs as you need them throughout the year.", "rosemary", PR, "harvest"),
    G("Mint rust overwinters on the underground runners.", "mint", TR, kind="fact", action="none"),
    G("Perhaps remove the worst-affected coriander leaves if leaf spot appears.", "coriander", TR, kind="hedged", conds=("leaf_spot",)),
    G("Prune rosemary at the same time as lavender, just after flowering.", "rosemary", PR, conds=("other",)),
    G("Give the thyme a light clip all over with shears.", "thyme", PR),
    G("In late summer, pick off sage leaves showing powdery mildew and bin them.", "sage", TR, conds=("powdery",), season="late summer"),
    G("Thyme planted in the ground should only be watered during a long spell without rain.", "thyme", W, conds=("in_ground", "hot_dry")),
    G("In very dry weather, soak parsley rows thoroughly every two or three days.", "parsley", W, conds=("hot_dry", "strong", "in_ground")),
    G("How often should you water chives?", "chives", W, kind="question"),
    N("If heavy rain is expected, move pots of thyme under the eaves to keep them dry.", "thyme", SH, "bring_in", conds=("rain_ahead", "strong", "in_pot")),
    G("Sage prefers lean, stony ground to rich soil.", "sage", NONE, kind="liking"),
    G("Cut mint shoots down to soil level as soon as the orange spots of mint rust appear.", "mint", TR, conds=("rust",)),
    G("Chives die down to the ground each winter and reappear in spring.", "chives", LN, kind="fact"),
    G("Remove the mildewed basil leaves straight away.", "basil", TR, conds=("mildew",)),
    G("Wash the greenfly off the chives with a jet of water.", "chives", TR, conds=("aphids",), conditions=[("named_problem", "greenfly")]),
    G("Sow parsley thinly in drills and keep the soil moist while it germinates.", "parsley", NONE, action="none"),
    G("Shelter the rosemary with a double layer of horticultural fleece.", "rosemary", SH),
    G("At the first sign of aphids, rinse the shoot tips of chives with a strong spray of water.", "chives", TR, conds=("aphids",)),
    N("Shade coriander from the strongest midday sun to delay flowering.", "coriander", ML, "shade"),
    G("Cut out any thyme stems that have died back.", "thyme", PR, conds=("trait",)),
    G("Move the coriander to a lighter windowsill.", "coriander", ML),
    N("Cut back gradually on watering sage from late September.", "sage", DW, "water_less", conditions=[("month_range", "from late September")]),
    G("Coriander runs to seed quickly when the roots dry out.", "coriander", W, kind="fact", action="none"),
    N("Mulch around the base of chives with well-rotted compost.", "chives", W, "none"),
    G("Take off any sage leaves with brown spots.", "sage", TR, conds=("leaf_spot",), conditions=[("named_problem", "brown spots")]),
    G("Coriander likes a cool, slightly shaded spot in summer.", "coriander", ML, kind="liking", action="shade"),
    G("Older sage leaves often take on a silvery, felted look.", "sage", LN, kind="fact"),
    G("Basil sulks when temperatures fall below about 10C.", "basil", SH, kind="fact", action="none"),
    G("Through a prolonged drought, give established sage a deep drink once a fortnight.", "sage", W, conds=("hot_dry", "trait")),
    G("Nip out the top pair of leaves on each basil stem.", "basil", PR),
    G("Keep parsley seedlings on a bright windowsill so they do not stretch towards the light.", "parsley", ML, conds=("seedlings",)),
    G("Water coriander seedlings gently with a fine rose whenever the surface looks dry.", "coriander", W, conds=("seedlings", "soil_dry")),
    N("Deadhead chives after flowering so they don't self-seed everywhere.", "chives", PR, "deadhead", conditions=[("other", "after flowering")]),
    G("When the compost is still damp from the day before, skip watering the coriander.", "coriander", DW, conds=("soil_moist",)),
    G("If red spider mite mottles the leaves of thyme under glass, mist the plants and remove the worst stems.", "thyme", TR, conds=("spider_mite", "indoors")),
    N("Snip off faded thyme flowers to keep the plant neat.", "thyme", PR, "deadhead"),
    G("During a heatwave, water mint in containers first thing in the morning and again at dusk.", "mint", W, conds=("hot_dry", "in_pot")),
    G("Stand the basil where it gets full sun for most of the day.", "basil", ML),
    N("In summer, move basil into the greenhouse to boost its flavour and keep slugs at bay.", "basil", SH, "bring_in", season="summer"),
    N("Sow coriander direct where it is to grow, a short row every few weeks.", "coriander", W, "none"),
    G("You may find it helps to water mint a little more often in a sunny spot.", "mint", W, kind="hedged"),
    G("Plenty of growers sink mint in a bottomless bucket to stop it spreading.", "mint", NONE, kind="fact"),
    G("Parsley is a biennial and flowers in its second summer.", "parsley", NONE, kind="fact"),
    G("By mid-autumn, move pots of parsley into a cold greenhouse or porch.", "parsley", SH, conds=("in_pot",), season="mid-autumn"),
    G("Mediterranean herbs such as thyme rarely need watering once their roots are established.", "thyme", DW, kind="fact", conds=("trait",), group="mediterranean herbs", **GRP),
    N("Sow coriander alongside lettuce in a cool, part-shaded bed.", "coriander", W, "none"),
    G("Avoid watering sage on cold winter evenings.", "sage", W, kind="neg", conds=("cold_ahead",), season="winter"),
    N("Top-dress mint in pots with fresh compost and a handful of slow-release fertiliser.", "mint", W, "feed", conds=("in_pot",)),
    G("Remove fallen leaves from around the plants to reduce the spread of disease.", "mint", TR, conds=("other",), **GEN),
    G("Keep sage dry at the roots.", "sage", DW),
    G("Avoid sowing coriander in midsummer heat, when it bolts almost at once.", "coriander", NONE, kind="neg", action="none"),
    G("Before a hard frost, carry pots of sage into an unheated garage or shed.", "sage", SH, conds=("cold_ahead", "strong", "in_pot")),
    G("From May to September, water pot-grown basil whenever the compost feels dry.", "basil", W, conds=("soil_dry", "in_pot"), season="May to September"),
    G("Pinching out the tips can help basil branch out.", "basil", PR, kind="hedged"),
    G("Where whitefly builds up on indoor basil, hang yellow sticky traps beside the pots.", "basil", TR, conds=("whitefly", "indoors", "in_pot")),
    G("A clump of chives that is cut regularly produces finer, more tender leaves.", "chives", PR, kind="fact"),
    G("Watering mint in pots and containers", "mint", W, kind="question"),
    N("Repot parsley into a deeper container, as it has a long taproot.", "parsley", W, "repot"),
    N("If the forecast warns of heavy downpours, move potted chives under cover so the roots don't sit in water.", "chives", SH, "bring_in", conds=("rain_ahead", "strong", "in_pot")),
    G("Snip the chives down to the base.", "chives", PR),
    G("Young coriander plants need watering daily during hot, dry spells.", "coriander", W, kind="liking", conds=("trait", "hot_dry")),
    G("Should rosemary beetle turn up, tap the branches over an old tray and dispose of the beetles.", "rosemary", TR, conds=("beetle",)),
    G("Never spray rosemary with insecticide while it is in flower.", "rosemary", TR, kind="neg", conditions=[("other", "in flower")]),
    G("Some gardeners trim thyme after every flush of flowers.", "thyme", PR, kind="fact"),
    G("Throw a sheet of fleece over young coriander when a sharp frost is predicted.", "coriander", SH, conds=("cold_ahead", "strong", "trait")),
    G("Cut the mint right back to a few centimetres above the soil.", "mint", PR),
    G("Chives need a fairly rich, moist soil to do well.", "chives", W, kind="liking", action="none"),
    G("Let the thyme compost dry right out before you think about watering again.", "thyme", DW),
    G("Rosemary in pots could do with some fleece during a bitter spell.", "rosemary", SH, kind="hedged", conds=("in_pot", "cold_ahead", "strong")),
    G("It might be worth moving coriander somewhere brighter if the stems look thin.", "coriander", ML, kind="hedged", conds=("trait",)),
    N("Give rosemary only a little water at a time, and less often as autumn arrives.", "rosemary", DW, "water_less", season="autumn"),
    G("Avoid splashing basil leaves when you water.", "basil", W, kind="neg"),
    G("Find chives a sunnier position.", "chives", ML),
    G("Rosemary flowers in late winter and early spring, bringing early food for bees.", "rosemary", NONE, kind="fact"),
    G("Perhaps give sage a gentle trim after it flowers.", "sage", PR, kind="hedged", conds=("other",)),
    G("Mint tolerates dappled shade happily.", "mint", ML, kind="liking", action="none"),
    N("Check pots daily during hot weather, as compost can dry out within hours.", "chives", W, "none", conds=("hot_dry", "in_pot"), **GEN),
    G("Basil grown outdoors needs bringing into the house as soon as autumn evenings turn chilly.", "basil", SH, conds=("outdoors", "cold_ahead"), season="autumn"),
    G("Cut back straggly sage stems to a leafy bud.", "sage", PR, conds=("trait",)),
    G("Never prune thyme into the bare, woody base.", "thyme", PR, kind="neg"),
    G("Thyme cannot stand heavy, wet clay.", "thyme", DW, kind="liking", action="none"),
    G("Can parsley be grown indoors in winter?", "parsley", SH, kind="question", action="none"),
    G("Trim coriander stems back to encourage fresh leaves.", "coriander", PR),
    N("Raise pots on feet over winter so excess water can drain away.", "sage", DW, "none", season="winter", **GEN),
    G("Soak the mint thoroughly so the water reaches the bottom of the pot.", "mint", W, conds=("in_pot",)),
    G("In a dull, north-facing kitchen, move basil to the brightest window you have.", "basil", ML, conds=("indoors", "other")),
    G("Lightly trimmed thyme stays dense and low.", "thyme", PR, kind="fact"),
    G("When the soil is bone dry, water parsley slowly so it soaks in rather than runs off.", "parsley", W, conds=("soil_dry", "strong"), conditions=[("soil_dry", "bone dry")]),
    G("Frequent cutting keeps mint producing soft new shoots.", "mint", PR, kind="fact"),
    G("Don't bother tidying mint stems until spring, as they protect the crown.", "mint", PR, kind="neg"),
    N("Thin out basil seedlings, keeping only the strongest in each pot.", "basil", PR, "thin", conds=("seedlings", "in_pot")),
    G("Parsley requires a deep root run.", "parsley", NONE, kind="liking"),
    N("Thin coriander seedlings so each one stands about 10cm from its neighbour.", "coriander", PR, "thin", conds=("seedlings",)),
    N("Give container basil a balanced liquid feed every ten days in summer.", "basil", W, "feed", conds=("in_pot",), season="summer"),
    G("It's worth checking thyme for red spider mite in a hot, dry summer.", "thyme", TR, kind="hedged", action="none", conds=("spider_mite", "hot_dry")),
    G("In a wet summer, remove any coriander leaves that develop dark leaf spots.", "coriander", TR, conds=("leaf_spot", "other"), season="summer"),
    G("In severe cold, wrap container-grown rosemary in hessian or bubble wrap.", "rosemary", SH, conds=("cold_ahead", "strong", "in_pot")),
    G("Rosemary appreciates the shelter of a warm wall.", "rosemary", SH, kind="liking"),
    G("Move containers against a sheltered wall when frost is forecast.", "thyme", SH, conds=("cold_ahead", "in_pot"), **GEN),
    G("Mint craves moisture at the roots.", "mint", W, kind="liking"),
    G("Thyme revels in heat reflected from paving.", "thyme", ML, kind="liking"),
    G("Leafy herbs like parsley appreciate regular watering through the summer.", "parsley", W, kind="liking", season="summer", group="leafy herbs", **GRP),
    G("Rosemary in a heavy, waterlogged border should be left without water until the soil drains.", "rosemary", DW, conds=("soil_wet", "in_ground", "other")),
    G("Before a cold snap, gather pots of thyme together against a sunny wall and cover them with fleece.", "thyme", SH, conds=("cold_ahead", "in_pot")),
    G("Hold off watering the rosemary for now.", "rosemary", DW),
    G("Lots of people keep rosemary on a sunny doorstep all year round.", "rosemary", ML, kind="fact"),
    N("Rig up some netting to give parsley light shade during the hottest part of the day.", "parsley", ML, "shade"),
    G("In containers, check rosemary every few days in summer and water only when the compost is dry.", "rosemary", W, conds=("in_pot", "soil_dry"), season="summer"),
    G("Woody herbs like sage and rosemary are cut back in spring, not autumn.", "sage", PR, kind="fact", season="spring"),
    N("Move sage into a pot one size larger, using gritty, loam-based compost.", "sage", W, "repot", conds=("in_pot",)),
    N("Spread a gravel mulch around thyme to keep its leaves off damp soil.", "thyme", DW, "none"),
    G("Mint could be brought indoors for a winter supply of leaves.", "mint", SH, kind="hedged", conds=("other",)),
    G("Give the coriander a long, slow drink.", "coriander", W),
    G("In early spring, cut sage back to just above the lowest healthy buds.", "sage", PR, season="early spring"),
    G("Like lavender, sage should never be cut back hard into bare stems.", "sage", PR, kind="neg"),
    G("After a very hard winter, cut back any frost-blackened rosemary shoots in late spring.", "rosemary", PR, conds=("strong", "other"), season="late spring"),
    G("Don't leave diseased basil leaves lying on the compost surface.", "basil", TR, kind="neg"),
    G("You might want to cut parsley back if it starts to flower.", "parsley", PR, kind="hedged", conds=("other",)),
    G("Indoors, stand chives on the brightest sill in the house through winter.", "chives", ML, conds=("indoors",), season="winter"),
    G("Coriander hates having its roots disturbed by transplanting.", "coriander", NONE, kind="liking"),
    N("Don't strip more than half the leaves off a parsley plant at one time.", "parsley", PR, "harvest", kind="neg"),
    G("Chives planted beneath roses are said to help deter aphids.", "chives", TR, kind="fact", action="none"),
    G("Bring the basil plant into the house.", "basil", SH),
    G("Where the ground is soggy after a wet week, leave chives unwatered until it firms up.", "chives", DW, conds=("soil_wet", "in_ground")),
    G("Give basil a thorough watering at the base once the top of the compost has gone dry.", "basil", W, conds=("soil_dry",)),
    G("On established plants with woody stems, prune sage lightly in April rather than cutting into old wood.", "sage", PR, conds=("trait",), season="April"),
    G("Once flowering finishes in midsummer, cut chives to a few centimetres above the soil.", "chives", PR, conds=("other",), season="mid-summer"),
    G("It may help to hold off watering chives for a while if the leaf tips go yellow.", "chives", DW, kind="hedged", conds=("trait",)),
    G("Check parsley for greenfly in early summer and squash any colonies you find.", "parsley", TR, conds=("aphids",), season="early summer", conditions=[("named_problem", "greenfly"), ("month_range", "early summer")]),
    G("Pick off sage leaves marked with leaf spot as soon as you see them.", "sage", TR, conds=("leaf_spot",)),
    G("Is it OK to cut chives right down to the ground?", "chives", PR, kind="question"),
    G("Rosemary beetle larvae are greyish and feed on the young leaves.", "rosemary", TR, kind="fact", action="none"),
    G("Give parsley a good, deep watering.", "parsley", W),
    N("Reduce how often you water thyme once it has settled in.", "thyme", DW, "water_less", conds=("other",)),
    G("Curly parsley is slightly hardier than the flat-leaved type.", "parsley", NONE, kind="fact"),
    G("Cover the parsley with a cloche.", "parsley", SH),
    G("With rain on the way, hold back from watering the parsley bed.", "parsley", DW, conds=("rain_ahead", "in_ground")),
    G("Protecting rosemary through a cold winter", "rosemary", SH, kind="question"),
    G("In late summer, shear mint down by half to encourage a fresh flush of leaves.", "mint", PR, season="late summer"),
    G("Annual herbs such as coriander are best sown in succession through summer.", "coriander", NONE, kind="fact", group="annual herbs", **GRP),
    G("Thyme tends to open up in the middle as it ages.", "thyme", LN, kind="fact"),
    G("Dealing with leaf spot on coriander", "coriander", TR, kind="question"),
    G("No need to fleece chives; they shrug off the worst of the winter.", "chives", SH, kind="neg"),
    G("Basil leaves are at their most aromatic just before the plant flowers.", "basil", NONE, kind="fact"),
    G("In March, trim rosemary lightly to tidy the shape before new growth starts.", "rosemary", PR, season="March"),
    G("Leggy chives grown indoors should be moved closer to the window.", "chives", ML, conds=("indoors", "trait")),
    G("If you notice downy mildew under basil leaves, pull the plant up and put it in the bin.", "basil", TR, conds=("mildew",)),
    G("Strip off the rust-spotted mint leaves and bin them.", "mint", TR, conds=("rust",)),
    G("Don't move rosemary to a shady corner, even indoors.", "rosemary", ML, kind="neg", action="shade"),
    G("Basil should come indoors the moment a cold night is forecast.", "basil", SH, conds=("cold_ahead",)),
    G("Tender herbs struggle once autumn nights turn cold, so lift them into a frost-free place.", "basil", SH, conds=("cold_ahead",), season="autumn", group="tender herbs", **GRP),
    G("Sage tends to become woody and sparse after four or five years.", "sage", LN, kind="fact"),
    G("Spray parsley with a soft soap solution to clear the aphids.", "parsley", TR, conds=("aphids",)),
    G("Water in the cool of the morning so the foliage dries before nightfall.", "basil", W, conds=("other",), **GEN),
]  # fmt: skip
