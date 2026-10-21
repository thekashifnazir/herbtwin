"""Builds data/eval/sets/trusted_judge_v4.jsonl: the set for the extract-then-decide check
(19 Oct; Kash chose to tell the judge the plant's state, and the design where a model
fills a form and code decides: the model reads, code decides).

Every sentence is new (none is in v1 or v2), DEV, TEST and RED-TEAM sentences are disjoint,
and the script refuses a reused one. Each sentence carries TWO annotations by the author
(the nvidia session; Kash is never asked for a care judgment):

1. the DIRECT reading: what the sentence tells the gardener to do (one of our coarse
   actions, or "none"), its kind, the conditions it puts on that, and the season it names.
   The primary gold comes from this, item by item: does the sentence, read literally,
   support doing OUR action NOW for THIS plant in THIS state? It is true only for an
   instruction, of our action, for this plant, in a season that includes the month, whose
   every condition holds in the state; a condition the state cannot tell does not hold.
2. the Stage-1 FORM fields (stages/trusted_check.Form): the secondary gold for field
   accuracy, and what the code's Stage-2 rules run on.

The two are written separately, so where the code's rules on the labelled form disagree
with the direct reading, that is a rule (or a vocabulary) gap, and the script reports it.

    uv run python scripts/build_judge_v4.py
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from herbtwin.stages.trusted_check import Form, PlantState, decide

ROOT = Path(__file__).parents[1]
OUT = ROOT / "data/eval/sets/trusted_judge_v4.jsonl"
W, DW, ML, SH, TR, PR, LN, NONE = (
    "water", "dont_water", "move_light", "shelter", "treat_or_remove", "prune", "leave_normal",
    "none",
)  # fmt: skip
OTHER = {W: DW, DW: W, ML: SH, SH: TR, TR: SH, PR: W, LN: TR, NONE: W}
SEASONS = {"spring": (3, 4, 5), "summer": (6, 7, 8), "autumn": (9, 10, 11), "winter": (12, 1, 2)}
# direct conditions: the state field each reads and the value that makes it hold
CONDS = {
    "soil_dry": ("soil", "dry"), "soil_wet": ("soil", "wet"),
    "cold_ahead": ("cold_ahead", True), "mild_ahead": ("cold_ahead", False),
    "rain_ahead": ("rain_ahead", True), "hot_dry": ("hot_dry", True),
    "seedlings": ("seedlings", True), "indoors": ("setting", "indoor"),
    "outdoors": ("setting", "outdoor"), "in_pot": ("container", "pot"),
    "in_ground": ("container", "ground"), "mildew": ("problem", "downy mildew"),
    "rust": ("problem", "mint rust"), "aphids": ("problem", "aphids"),
    "beetle": ("problem", "rosemary beetle"), "other": (None, None),
}  # fmt: skip
# the direct condition as a Stage-1 condition, for the default form
FORM_COND = {
    "soil_dry": ("soil_dry", ""), "soil_wet": ("soil_wet", ""),
    "cold_ahead": ("cold_or_frost_forecast", ""), "mild_ahead": ("other", "after the cold"),
    "rain_ahead": ("rain_forecast", ""), "hot_dry": ("hot_dry_weather", ""),
    "seedlings": ("plant_stage", "seedlings"), "indoors": ("indoor", ""),
    "outdoors": ("outdoor", ""), "in_pot": ("container", "pot"),
    "in_ground": ("container", "ground"), "mildew": ("named_problem", "downy mildew"),
    "rust": ("named_problem", "mint rust"), "aphids": ("named_problem", "aphids"),
    "beetle": ("named_problem", "rosemary beetle"), "other": ("other", "unstated"),
}  # fmt: skip
FORM_ACTION = {W: "water", DW: "withhold_water", ML: "move_light", PR: "prune",
               TR: "treat_or_remove", LN: "none", NONE: "none"}  # fmt: skip
_BRING = re.compile(r"\b(?:bring|indoors|inside|porch|under cover|greenhouse|house wall)\b", re.I)


def F(sentence, plant, says, kind="do", conds=(), season=None, **form):  # noqa: N802
    """One sentence: its direct reading, and its Stage-1 form (defaults from the direct
    reading; keyword overrides where the form differs)."""
    action = form.pop("action", None) or (
        ("bring_in" if _BRING.search(sentence) else "protect_cold")
        if says == SH
        else FORM_ACTION[says]
    )
    fconds = form.pop("conditions", None)
    if fconds is None:
        fconds = [FORM_COND[c] for c in conds] + ([("month_range", season)] if season else [])
    fields = {
        "action": action,
        "polarity": form.pop("polarity", "dont" if kind == "neg" else "do"),
        "applies_to": form.pop("applies_to", "other_plant" if kind == "other_plant" else "this_plant"),
        "group": form.pop("group", ""),
        "conditions": [{"kind": k, "value": v} for k, v in fconds],
        "hedged": form.pop("hedged", kind == "hedged"),
        "is_instruction": form.pop("is_instruction", kind in ("do", "hedged")),
    }  # fmt: skip
    assert not form, form
    return {"sentence": sentence, "plant": plant, "says": says, "kind": kind,
            "conds": list(conds), "season": season, "form": Form.model_validate(fields)}  # fmt: skip


def base_state(plant, month, action, **kw) -> dict:
    s = {"plant": plant, "month": month, "action": action, "setting": "outdoor",
         "container": "pot", "soil": None, "cold_ahead": None, "hot_dry": None,
         "rain_ahead": None, "problem": None, "seedlings": False}  # fmt: skip
    s.update(kw)
    return s


def direct_gold(fam: dict, st: dict) -> bool:
    """The author's direct reading, applied to one state."""
    if fam["kind"] != "do" or fam["says"] != st["action"] or fam["plant"] != st["plant"]:
        return False
    if fam["season"] and st["month"] not in SEASONS[fam["season"]]:
        return False
    for c in fam["conds"]:
        field, value = CONDS[c]
        if field is None or st.get(field) != value:
            return False
    return True


def opposite(field, value):
    if isinstance(value, bool):
        return not value
    return {"soil": "wet" if value == "dry" else "dry",
            "setting": "outdoor" if value == "indoor" else "indoor",
            "container": "ground" if value == "pot" else "pot",
            "problem": "aphids" if value != "aphids" else "downy mildew"}[field]  # fmt: skip


def states(fam: dict) -> list[dict]:
    plant, says, season = fam["plant"], fam["says"], fam["season"]
    month = SEASONS[season][1] if season else 10
    ours = says if says != NONE else W
    real = [c for c in fam["conds"] if CONDS[c][0] is not None]
    if fam["kind"] == "do" and real:
        holding = {CONDS[c][0]: CONDS[c][1] for c in real}
        out = [base_state(plant, month, ours, **holding)]  # every condition holds
        f0, v0 = CONDS[real[0]]
        out.append(base_state(plant, month, ours, **{**holding, f0: opposite(f0, v0)}))
        if f0 not in ("setting", "container", "seedlings"):
            rest = {k: v for k, v in holding.items() if k != f0}
            out.append(base_state(plant, month, ours, **rest))  # the state cannot tell
        return out
    if fam["kind"] == "do":
        out = [base_state(plant, month, ours), base_state(plant, month, OTHER[ours])]
        if season:
            out.append(base_state(plant, 1 if season != "winter" else 7, ours))
        return out
    return [base_state(plant, 10, ours), base_state(plant, 6, ours, setting="indoor"),
            base_state(plant, 1, ours, container="ground")]  # fmt: skip


TEST = [
    # conditional instructions: the state decides
    F(
        "Give the pot a thorough soak whenever the compost feels dry to the touch.",
        "basil",
        W,
        conds=("soil_dry",),
    ),
    F("Water parsley deeply if the soil has dried out.", "parsley", W, conds=("soil_dry",)),
    F(
        "When the top few centimetres are dry, water mint generously.",
        "mint",
        W,
        conds=("soil_dry",),
    ),
    F(
        "If the compost is dry, water coriander straight away to stop it bolting.",
        "coriander",
        W,
        conds=("soil_dry",),
    ),
    F("Water chives well in prolonged dry weather.", "chives", W, conds=("hot_dry",)),
    F(
        "During long dry spells, give rosemary an occasional deep watering.",
        "rosemary",
        W,
        conds=("hot_dry",),
    ),
    F("Water parsley every evening during a heatwave.", "parsley", W, conds=("hot_dry",)),
    F("In hot weather, water pots of basil twice a day.", "basil", W, conds=("hot_dry",)),
    F(
        "If the compost is soggy, stop watering until it has dried out.",
        "basil",
        DW,
        conds=("soil_wet",),
    ),
    F(
        "Hold off watering rosemary while the soil is still wet.",
        "rosemary",
        DW,
        conds=("soil_wet",),
    ),
    F(
        "When heavy rain is forecast, there is no need to water beds.",
        "mint",
        DW,
        conds=("rain_ahead",),
    ),
    F("Skip watering pots of thyme if rain is due.", "thyme", DW, conds=("rain_ahead",)),
    F("If rain is forecast, leave watering for another day.", "basil", DW, conds=("rain_ahead",)),
    F(
        "If a frost is forecast, drape fleece over basil overnight.",
        "basil",
        SH,
        conds=("cold_ahead",),
    ),
    F(
        "Bring pots of coriander into a porch when a cold night is on the way.",
        "coriander",
        SH,
        conds=("cold_ahead",),
    ),
    F(
        "Cover young parsley with a cloche when frost threatens.",
        "parsley",
        SH,
        conds=("cold_ahead",),
    ),
    F(
        "Move pots of sage against a house wall before a hard frost.",
        "sage",
        SH,
        conds=("cold_ahead",),
    ),
    F(
        "Lift basil pots indoors if night temperatures will fall below 8C.",
        "basil",
        SH,
        conds=("cold_ahead",),
    ),
    F(
        "Never leave basil out on a frosty night.",
        "basil",
        SH,
        conds=("cold_ahead",),
        action="bring_in",
        polarity="do",
    ),
    F("Once the cold spell has passed, take the fleece off.", "basil", NONE, conds=("mild_ahead",)),
    F(
        "If downy mildew appears on basil, remove the affected plants straight away.",
        "basil",
        TR,
        conds=("mildew",),
    ),
    F(
        "Where downy mildew strikes, pull up and bin the worst plants.",
        "basil",
        TR,
        conds=("mildew",),
    ),
    F(
        "If the leaves are mottled with downy mildew, bin the plant.",
        "basil",
        TR,
        conds=("mildew",),
    ),
    F(
        "If rust shows on mint, cut the stems to the ground and bin them.",
        "mint",
        TR,
        conds=("rust",),
    ),
    F(
        "Mint with rust pustules should have its affected shoots removed.",
        "mint",
        TR,
        conds=("rust",),
    ),
    F(
        "If aphids cluster on the tips, wipe them off with a damp cloth.",
        "basil",
        TR,
        conds=("aphids",),
    ),
    F(
        "Where aphids are a problem, squash small colonies by hand.",
        "parsley",
        TR,
        conds=("aphids",),
    ),
    F("When aphids appear, hose them off with a jet of water.", "chives", TR, conds=("aphids",)),
    F(
        "If you find rosemary beetle, shake the plant over a sheet and destroy the beetles.",
        "rosemary",
        TR,
        conds=("beetle",),
    ),
    F(
        "Pick off rosemary beetle larvae by hand whenever you see them.",
        "rosemary",
        TR,
        conds=("beetle",),
    ),
    F(
        "Thin coriander seedlings to 5cm apart once they can be handled.",
        "coriander",
        PR,
        conds=("seedlings",),
    ),
    F("When seedlings appear, keep the compost just moist.", "basil", W, conds=("seedlings",)),
    F(
        "Water seedlings from below if the compost has dried.",
        "parsley",
        W,
        conds=("seedlings", "soil_dry"),
    ),
    F("Indoors, move basil to the brightest windowsill you have.", "basil", ML, conds=("indoors",)),
    F(
        "Grown indoors, parsley needs moving close to a bright window.",
        "parsley",
        ML,
        conds=("indoors",),
    ),
    F("Indoors, water basil less in winter.", "basil", DW, conds=("indoors",), season="winter"),
    F(
        "If the plant is outdoors, bring it in before frost.",
        "basil",
        SH,
        conds=("outdoors", "cold_ahead"),
    ),
    F(
        "Basil kept outdoors should come inside once nights fall below 10C.",
        "basil",
        SH,
        conds=("outdoors", "cold_ahead"),
    ),
    F(
        "In pots, water rosemary only when the compost is nearly dry.",
        "rosemary",
        W,
        conds=("in_pot", "soil_dry"),
    ),
    F(
        "Container-grown mint needs watering every day in hot weather.",
        "mint",
        W,
        conds=("in_pot", "hot_dry"),
    ),
    F(
        "Move potted basil into the greenhouse when frost is forecast.",
        "basil",
        SH,
        conds=("in_pot", "cold_ahead"),
    ),
    F("Water pots of parsley daily in summer.", "parsley", W, conds=("in_pot",), season="summer"),
    # the words fit a condition we track, but not our advice
    F(
        "When a wet spell is forecast, move pots of thyme under cover.",
        "thyme",
        NONE,
        conds=("rain_ahead",),
        action="bring_in",
    ),
    F(
        "If frost has blackened the tips, cut them back in spring.",
        "basil",
        PR,
        conds=("other",),
        season="spring",
    ),
    F("Shade parsley in a heatwave.", "parsley", NONE, conds=("hot_dry",), action="shade"),
    F("Keep coriander out of hot afternoon sun.", "coriander", NONE, action="shade"),
    F("Feed basil every fortnight in summer.", "basil", NONE, season="summer", action="feed"),
    F(
        "Repot rosemary into gritty compost in spring.",
        "rosemary",
        NONE,
        season="spring",
        action="repot",
    ),
    F("Harvest basil leaves regularly from the top.", "basil", NONE, action="harvest"),
    # plain instructions
    F("Water basil generously and often.", "basil", W),
    F("Keep parsley well watered throughout its life.", "parsley", W),
    F("Give mint a good drink every few days.", "mint", W),
    F("Water rosemary only sparingly.", "rosemary", DW),
    F("Keep thyme on the dry side at all times.", "thyme", DW),
    F("Let sage dry out well between waterings.", "sage", DW),
    F("Move the basil pot to your sunniest window.", "basil", ML),
    F("Shift coriander into a spot with more light.", "coriander", ML),
    F("Put parsley where it gets morning sun.", "parsley", ML),
    F("Protect basil from cold with a layer of fleece.", "basil", SH),
    F("Shelter pots of sage from icy winds.", "sage", SH),
    F("Remove any shoots killed by disease and bin them.", "mint", TR),
    F("Destroy rosemary beetles and their larvae.", "rosemary", TR),
    F("Cut out stems spotted with rust.", "mint", TR),
    F("Pinch out the tips of basil to keep it bushy.", "basil", PR),
    F("Shorten leggy mint stems by half.", "mint", PR),
    F("Trim chives back to fresh growth.", "chives", PR),
    F("Clip thyme lightly to keep it compact.", "thyme", PR),
    F(
        "Some yellowing of older parsley leaves is quite normal.",
        "parsley",
        LN,
        is_instruction=False,
    ),
    F(
        "Mint dying back in late autumn is entirely natural.",
        "mint",
        LN,
        season="autumn",
        is_instruction=False,
    ),
    F("Leave chives alone; they will regrow in spring.", "chives", LN),
    # plant groups
    F(
        "Bring tender herbs indoors before the first frost.",
        "basil",
        SH,
        conds=("cold_ahead",),
        applies_to="plant_group",
        group="tender herbs",
    ),
    F(
        "Fleece tender herbs whenever frost is forecast.",
        "coriander",
        SH,
        conds=("cold_ahead",),
        applies_to="plant_group",
        group="tender herbs",
    ),
    F(
        "Keep Mediterranean herbs dry through the winter.",
        "rosemary",
        DW,
        season="winter",
        applies_to="plant_group",
        group="mediterranean herbs",
    ),
    F(
        "Water leafy herbs freely in summer.",
        "parsley",
        W,
        season="summer",
        applies_to="plant_group",
        group="leafy herbs",
    ),
    F(
        "Trim leafy herbs often to keep them productive.",
        "chives",
        PR,
        applies_to="plant_group",
        group="leafy herbs",
    ),
    F(
        "Mediterranean herbs need little water.",
        "rosemary",
        DW,
        kind="liking",
        applies_to="plant_group",
        group="mediterranean herbs",
    ),
    # hedged
    F(
        "You might water basil a little more in a warm spell.",
        "basil",
        W,
        kind="hedged",
        conds=("hot_dry",),
    ),
    F(
        "It can help to fleece young basil on cold nights.",
        "basil",
        SH,
        kind="hedged",
        conds=("cold_ahead",),
    ),
    F(
        "Some herbs may benefit from a light trim now.",
        "thyme",
        PR,
        kind="hedged",
        applies_to="general",
    ),
    F(
        "Perhaps move parsley somewhere brighter if it looks pale.",
        "parsley",
        ML,
        kind="hedged",
        conds=("other",),
    ),
    F("You could remove a few of the worst leaves.", "basil", TR, kind="hedged"),
    F(
        "It's often worth watering mint in a dry week.",
        "mint",
        W,
        kind="hedged",
        conds=("hot_dry",),
    ),
    # other seasons
    F(
        "Sow coriander outdoors in April.",
        "coriander",
        NONE,
        season="spring",
        action="none",
        conditions=[("month_range", "April")],
    ),
    F("Cut sage back by a third in spring.", "sage", PR, season="spring"),
    F("Give mint a summer trim to keep leaves fresh.", "mint", PR, season="summer"),
    F("Water basil every morning in summer.", "basil", W, season="summer"),
    F("In winter keep rosemary almost dry.", "rosemary", DW, season="winter"),
    F("Fleece thyme in the depths of winter.", "thyme", SH, season="winter"),
    F("Deadhead chives through the summer.", "chives", PR, season="summer"),
    F("Move basil outdoors in early summer.", "basil", NONE, season="summer", action="none"),
    # negations
    F(
        "Never water basil late at night.",
        "basil",
        W,
        kind="neg",
        conditions=[("other", "late at night")],
    ),
    F("Do not cut rosemary back into old wood.", "rosemary", PR, kind="neg"),
    F("There is no need to fleece established sage.", "sage", SH, kind="neg"),
    F("Avoid moving basil into cold, draughty rooms.", "basil", ML, kind="neg", action="none"),
    F(
        "Don't remove the flowers if you want coriander seed.",
        "coriander",
        PR,
        kind="neg",
        conditions=[("other", "for seed")],
    ),
    F(
        "You needn't water mint planted in damp ground.",
        "mint",
        W,
        kind="neg",
        conditions=[("soil_wet", "")],
    ),
    F(
        "Don't let parsley go short of water in summer.",
        "parsley",
        W,
        season="summer",
        polarity="do",
    ),
    F(
        "Avoid trimming thyme in late autumn.",
        "thyme",
        PR,
        kind="neg",
        conditions=[("month_range", "autumn")],
    ),
    F("Don't destroy the hoverfly larvae among the aphids.", "parsley", TR, kind="neg"),
    F(
        "There's no reason to bring rosemary indoors in the south.",
        "rosemary",
        SH,
        kind="neg",
        conditions=[("other", "in the south")],
    ),
    F(
        "Never water sage from overhead in winter.",
        "sage",
        W,
        kind="neg",
        conditions=[("month_range", "winter")],
    ),
    F(
        "In the ground, rosemary rarely needs watering.",
        "rosemary",
        W,
        kind="neg",
        conditions=[("container", "ground")],
        is_instruction=False,
    ),
    # likings and needs
    F("Basil loves heat and bright light.", "basil", ML, kind="liking"),
    F("Parsley appreciates a moisture-retentive soil.", "parsley", W, kind="liking"),
    F("Rosemary relishes a hot, dry spot.", "rosemary", DW, kind="liking"),
    F("Mint thrives in damp ground.", "mint", W, kind="liking"),
    F("Thyme is at its best in full sun.", "thyme", ML, kind="liking"),
    F("Coriander prefers cool, bright conditions.", "coriander", ML, kind="liking"),
    F("Sage needs very free-draining soil.", "sage", DW, kind="liking"),
    F("Chives are tolerant of light shade.", "chives", ML, kind="liking"),
    F("Basil dislikes cold, wet compost.", "basil", DW, kind="liking"),
    F("Mint prefers partial shade.", "mint", ML, kind="liking"),
    F("Thyme needs little water once established.", "thyme", DW, kind="liking"),
    # facts and what others do
    F(
        "Plants in containers need watering more often than those in the ground.",
        "mint",
        W,
        kind="fact",
        applies_to="general",
    ),
    F("Many cooks keep a pot of basil on the kitchen windowsill.", "basil", ML, kind="fact"),
    F("Some growers fleece rosemary every November.", "rosemary", SH, kind="fact"),
    F(
        "Plenty of gardeners water herbs every evening.",
        "basil",
        W,
        kind="fact",
        applies_to="general",
    ),
    F("Commercial growers cut chives several times a year.", "chives", PR, kind="fact"),
    F("Downy mildew can wipe out basil in a week.", "basil", TR, kind="fact"),
    F("Rust on mint is spread by spores in the soil.", "mint", TR, kind="fact"),
    F("Overwatering is a common way to lose rosemary.", "rosemary", DW, kind="fact"),
    F("Frost turns basil leaves black.", "basil", SH, kind="fact"),
    F("Pinching out encourages side shoots.", "basil", PR, kind="fact", applies_to="general"),
    F("Coriander bolts quickly in hot weather.", "coriander", LN, kind="fact"),
    F("Sage is evergreen in most winters.", "sage", LN, kind="fact"),
    F("Rosemary beetle feeds mainly in autumn and spring.", "rosemary", TR, kind="fact"),
    F("Gardeners often grow basil on a sunny patio.", "basil", ML, kind="fact"),
    # questions and headings
    F("Should you water basil from below?", "basil", W, kind="question"),
    F("Does rosemary need protecting in winter?", "rosemary", SH, kind="question"),
    F("When should I cut back mint?", "mint", PR, kind="question"),
    F("Watering basil in pots", "basil", W, kind="question"),
    F("How do I get rid of aphids on parsley?", "parsley", TR, kind="question"),
    F("Can basil survive outdoors in October?", "basil", SH, kind="question"),
    # other plants
    F("Water courgettes daily once they start fruiting.", "basil", W, kind="other_plant"),
    F("Pinch out the side shoots of cordon tomatoes.", "basil", PR, kind="other_plant"),
    F("Fleece early potatoes against late frost.", "basil", SH, kind="other_plant"),
    F("Remove blighted potato foliage and bin it.", "basil", TR, kind="other_plant"),
    F("Move citrus trees indoors for the winter.", "rosemary", SH, kind="other_plant"),
    F("Bring pelargoniums indoors in autumn.", "basil", SH, kind="other_plant"),
    F("Prune roses hard in March.", "rosemary", PR, kind="other_plant"),
]

DEV = [
    F("Water basil thoroughly when the compost surface is dry.", "basil", W, conds=("soil_dry",)),
    F("If parsley wilts on a dry day, give it a long drink.", "parsley", W, conds=("soil_dry",)),
    F("In dry spells, water mint at the base every few days.", "mint", W, conds=("hot_dry",)),
    F(
        "Water container herbs morning and evening in very hot weather.",
        "basil",
        W,
        conds=("in_pot", "hot_dry"),
        applies_to="general",
    ),
    F("Let wet compost drain before watering rosemary again.", "rosemary", DW, conds=("soil_wet",)),
    F("Don't water if heavy rain is forecast.", "thyme", DW, conds=("rain_ahead",), polarity="do"),
    F("Fleece basil on nights when frost is forecast.", "basil", SH, conds=("cold_ahead",)),
    F(
        "Bring parsley pots under cover if a cold night is coming.",
        "parsley",
        SH,
        conds=("cold_ahead",),
    ),
    F("Uncover plants again once frosts have passed.", "basil", NONE, conds=("mild_ahead",)),
    F("Bin basil plants that show downy mildew.", "basil", TR, conds=("mildew",)),
    F("Cut rusty mint stems to the ground.", "mint", TR, conds=("rust",)),
    F("Rub off aphids where they gather on shoot tips.", "basil", TR, conds=("aphids",)),
    F("Collect and destroy rosemary beetles when you see them.", "rosemary", TR, conds=("beetle",)),
    F("Thin parsley seedlings to 15cm apart.", "parsley", PR, conds=("seedlings",)),
    F(
        "On a windowsill indoors, turn the pot every few days so all sides get light.",
        "basil",
        NONE,
        conds=("indoors",),
        action="none",
    ),
    F("Water mint in pots more often than in the ground.", "mint", W, conds=("in_pot",)),
    F(
        "Move tender herbs under cover before frost.",
        "coriander",
        SH,
        conds=("cold_ahead",),
        applies_to="plant_group",
        group="tender herbs",
    ),
    F(
        "It may be worth fleecing sage in a hard winter.",
        "sage",
        SH,
        kind="hedged",
        conds=("cold_ahead",),
    ),
    F("Water parsley regularly.", "parsley", W),
    F("Keep rosemary on the dry side.", "rosemary", DW),
    F("Give basil the sunniest spot you can.", "basil", ML),
    F("Protect sage pots from freezing winds.", "sage", SH),
    F("Remove diseased leaves promptly.", "basil", TR),
    F("Pinch out basil flower buds.", "basil", PR),
    F("Dieback of mint in autumn is normal.", "mint", LN, season="autumn", is_instruction=False),
    F("Sow parsley in spring.", "parsley", NONE, season="spring", action="none"),
    F("Trim thyme in summer after flowering.", "thyme", PR, season="summer", conds=("other",)),
    F("In winter, water sage hardly at all.", "sage", DW, season="winter"),
    F(
        "Never prune sage hard in autumn.",
        "sage",
        PR,
        kind="neg",
        conditions=[("month_range", "autumn")],
    ),
    F(
        "Don't water coriander at midday.",
        "coriander",
        W,
        kind="neg",
        conditions=[("other", "midday")],
    ),
    F(
        "There's no need to cover thyme in a mild winter.",
        "thyme",
        SH,
        kind="neg",
        conditions=[("other", "mild winter")],
    ),
    F("Basil craves warmth.", "basil", ML, kind="liking"),
    F("Rosemary prefers lean, dry soil.", "rosemary", DW, kind="liking"),
    F("Many people grow mint in a bucket to stop it spreading.", "mint", PR, kind="fact"),
    F("Some gardeners water parsley daily.", "parsley", W, kind="fact"),
    F("Is basil an annual?", "basil", LN, kind="question"),
    F("Water tomatoes at the base, not over the leaves.", "basil", W, kind="other_plant"),
]

# the six sentences the last test run got wrong (seen: kept apart from TEST)
REDTEAM = [
    F("Water well when the soil feels dry.", "basil", W, conds=("soil_dry",), applies_to="general"),
    F(
        "Cover with fleece whenever a cold night is forecast.",
        "basil",
        SH,
        conds=("cold_ahead",),
        applies_to="general",
    ),
    F(
        "Bring pots under cover in cold, wet weather.",
        "basil",
        SH,
        conds=("cold_ahead", "rain_ahead"),
        applies_to="general",
    ),
    F(
        "Bring pots of basil indoors onto a sunny windowsill as nights cool.",
        "basil",
        SH,
        conds=("cold_ahead",),
    ),
    F(
        "Use a cloche to protect seedlings from cold nights.",
        "basil",
        SH,
        conds=("seedlings", "cold_ahead"),
        applies_to="general",
    ),
    F(
        "Remove any yellowing leaves.",
        "basil",
        NONE,
        action="treat_or_remove",
        applies_to="general",
    ),
]


def form_gold(fam: dict, st: dict) -> bool:
    s = PlantState(**{k: v for k, v in st.items()})
    return decide(fam["form"], s) == "agree"


def main() -> None:
    old = set()
    for name in ("trusted_judge_v1.jsonl", "trusted_judge_v2.jsonl"):
        for line in (ROOT / "data/eval/sets" / name).read_text().splitlines():
            if line.strip():
                old.add(json.loads(line)["sentence"])
    sets = {"test": TEST, "dev": DEV, "redteam": REDTEAM}
    names = {k: [f["sentence"] for f in v] for k, v in sets.items()}
    for k, v in names.items():
        if len(set(v)) != len(v):
            raise SystemExit(f"{k}: a sentence twice")
    if set(names["test"]) & (old | set(names["dev"]) | set(names["redteam"])):
        raise SystemExit("a TEST sentence is reused")
    if set(names["dev"]) & old:
        raise SystemExit("a DEV sentence is reused from v1/v2")
    rows, mismatched = [], []
    for split, fams in sets.items():
        for fam in fams:
            for st in states(fam):
                g, fg = direct_gold(fam, st), form_gold(fam, st)
                row = {"id": len(rows) + 1, "split": split, "sentence": fam["sentence"],
                       "kind": fam["kind"], "state": st, "gold": g, "form_gold": fg,
                       "form": fam["form"].model_dump()}  # fmt: skip
                rows.append(row)
                if g != fg:
                    mismatched.append(row)
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    for split in sets:
        rs = [r for r in rows if r["split"] == split]
        neg = sum(not r["gold"] for r in rs)
        print(f"{split}: {len(rs)} items ({len({r['sentence'] for r in rs})} sentences), "
              f"{neg} negatives, {len(rs) - neg} positives")  # fmt: skip
    print(f"direct vs rule-on-labelled-form disagreements: {len(mismatched)}")
    for r in mismatched:
        print(f"  [{r['split']}] direct={r['gold']} rule={r['form_gold']} "
              f"{r['state']['action']}: {r['sentence']}")  # fmt: skip
    print(Counter((r["split"], r["kind"], r["gold"]) for r in rows))


if __name__ == "__main__":
    main()
