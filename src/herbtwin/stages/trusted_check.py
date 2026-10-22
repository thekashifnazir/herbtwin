"""Does a trusted page's sentence back our advice? The model reads, code decides (19 Oct,
the pattern where a model fills a form and code decides: never let one model verdict gate
a high-stakes output).

Stage 1 (stages/trusted_extract.py) turns ONE page sentence into a fixed form, never
seeing our advice. Stage 2, here, is plain code: it agrees only when the form is an
instruction, to do (not avoid) our very action, for this plant, unhedged, and every
condition the sentence puts on it holds against what we already know about the plant
(the soil, the forecast, the month, indoors or out, the named problem, seedlings). Any
condition we cannot check, or a form we cannot read, is "unsure", and unsure shows nothing.

Round 4 writes in a blind labeller's stricter reading: a strength or a quality of the
plant the state can't confirm (heavy rain, hard frost, leggy, young) is unsure, read from
the sentence itself as well as the form; so are beds for a potted plant and pots for one
in the ground; "water less" is not "hold off"; deadheading and thinning are not cutting
back; "late autumn" is November. Round 5: "bone dry", "parched", "soggy" and
"waterlogged" are strengths too, and pulling up the whole plant is its own action.
After the round-5 test (disclosed post-test changes, each able only to remove agrees):
pinching out is not cutting back; each action must be said in the sentence's own words
(checking for a pest is not treating it); removing whole plants is not removing the
affected parts.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

FormAction = Literal[
    "water", "withhold_water", "water_less", "protect_cold", "bring_in", "move_light", "shade",
    "prune", "deadhead", "thin", "harvest", "treat_or_remove", "remove_plant", "feed", "repot",
    "none",
]  # fmt: skip
ConditionKind = Literal[
    "soil_dry", "soil_wet", "cold_or_frost_forecast", "hot_dry_weather", "rain_forecast",
    "month_range", "indoor", "outdoor", "container", "named_problem", "plant_stage",
    "plant_trait", "other",
]  # fmt: skip


class Condition(BaseModel):
    kind: ConditionKind
    value: str = Field("", max_length=60)


class Form(BaseModel):
    """What one sentence says, as Stage 1 reads it."""

    action: FormAction
    polarity: Literal["do", "dont"]
    applies_to: Literal["this_plant", "plant_group", "general", "other_plant"]
    group: str = Field("", max_length=40)  # the group named, for plant_group
    conditions: list[Condition] = Field(default_factory=list, max_length=6)
    hedged: bool
    is_instruction: bool


@dataclass(frozen=True)
class PlantState:
    """What we know about the plant when the answer is decided (pipeline.decide)."""

    plant: str  # its common name, lower case
    month: int
    action: str  # our coarse action
    setting: Literal["indoor", "outdoor", "unknown"] = "unknown"
    container: Literal["pot", "ground", "unknown"] = "unknown"
    soil: Literal["dry", "moist", "wet"] | None = None  # the finger test, else the photo
    cold_ahead: bool | None = None  # a frost or cold night in the forecast; None: no forecast
    hot_dry: bool | None = None  # a hot or dry spell; None: no forecast
    rain_ahead: bool | None = None  # rain in the next days; None: no forecast
    problem: str | None = None  # the photo check's named problem
    seedlings: bool = False


# our coarse action, and the form actions that are the same advice ("water less" is not
# "hold off", deadheading or thinning is not cutting back: round 4, from the blind labeller)
SAME_ADVICE: dict[str, frozenset[str]] = {
    "water": frozenset({"water"}),
    "dont_water": frozenset({"withhold_water"}),
    "shelter": frozenset({"protect_cold", "bring_in"}),
    "move_light": frozenset({"move_light"}),
    "prune": frozenset({"prune"}),
    "treat_or_remove": frozenset({"treat_or_remove"}),
    # pulling up the whole plant is not removing the affected parts; it backs only a
    # no-cure "remove the plant" (round 5; the app gives no such advice yet)
    "remove_plant": frozenset({"remove_plant"}),
}
# the groups a page may name, and their herbs; a group not listed is unsure
GROUPS: dict[str, frozenset[str]] = {
    "tender herbs": frozenset({"basil"}),  # coriander is a hardy annual
    "mediterranean herbs": frozenset({"rosemary", "thyme", "sage"}),
    "leafy herbs": frozenset({"basil", "coriander", "parsley", "mint", "chives"}),
}
_SEASONS = {
    "spring": (3, 4, 5), "summer": (6, 7, 8), "autumn": (9, 10, 11), "fall": (9, 10, 11),
    "winter": (12, 1, 2),
}  # fmt: skip
_MONTHS = {calendar.month_name[m].lower(): m for m in range(1, 13)}
_MONTHS |= {calendar.month_abbr[m].lower(): m for m in range(1, 13)}
_MONTHS["sept"] = 9
_PART = {"early": 0, "mid": 1, "late": 2}
_MAY_AFTER = frozenset(
    {"early", "mid", "late", "in", "from", "to", "until", "till", "by", "and", "of"}
)
# a strength the state can't confirm: we know frost is forecast, not that it is hard
_STRENGTH = re.compile(
    r"\b(?:heavy|hard|severe|harsh|sharp|bitter|very|extreme|torrential|bone[- ]dry|parched"
    r"|soggy|waterlogged)\b",
    re.I,
)
# a quality of the plant the state can't confirm, anywhere in the sentence
_TRAIT = re.compile(
    r"\b(?:leggy|young|established|mature|woody|old|newly|pale|straggly|overgrown)\b", re.I
)
_GROUND_WORDS = re.compile(r"\b(?:beds?|borders?|open ground|in the ground)\b", re.I)
_POT_WORDS = re.compile(r"\b(?:pots?|containers?|tubs?|planters?|window ?boxes?)\b", re.I)
# pinching out is not cutting back (post-test, 19 Oct: round 5's 4 false agrees were all
# pinch-out lines the blind labeller did not count as "cut it back")
_PINCH = re.compile(r"\bpinch(?:es|ed|ing)?\b", re.I)
# each action in the sentence's own words (post-test, 19 Oct, from live pages: "check
# rosemary for rosemary beetle" was read as treating it, "ventilate the greenhouse" as
# protecting from cold). Allow-lists, so a verb not listed only loses an agree
_TREATS = (
    r"remov\w*|destroy\w*|pick(?:s|ed|ing)? off|pick (?:\w+ )*?off|cut(?:s|ting)?|squash\w*|"
    r"rinse\w*|wash\w*|spray\w*|strip\w*|take (?:\w+ )*?off|dig(?:s|ging)?|pull\w*|bin(?:s|ned)?|"
    r"dispos\w*|treat\w*|wipe\w*|rub\w*|hose\w*|shake\w*|collect\w*|clear\w*|burn\w*|"
    r"prune\w*|trim\w*|mist\w*|hang\w*|tap"
)
_SAYS: dict[str, re.Pattern] = {
    action: re.compile(rf"\b(?:{words})\b", re.I)
    for action, words in {
        "water": r"water\w*|soak\w*|drench\w*|irrigat\w*|moist|drink",
        "withhold_water": (
            r"hold\w* (?:off|back)|stop\w*|withh\w*|(?:don't|do not|never) water|no (?:more )?water|"
            r"unwatered|without (?:a |any )?water\w*|go without|for later|another day|drain\w*|"
            r"let\b[^.;]*\bdry|keep\b[^.;]*\bdry|wait\w*|avoid\w*|leave\b[^.;]*\bdry|skip\w*"
        ),
        "protect_cold": (
            r"fleece\w*|cover\w*|protect\w*|shelter\w*|wrap\w*|cloche\w*|insulat\w*|"
            r"mulch\w*|cold frames?"
        ),
        "bring_in": (
            r"bring\w*|brought|com(?:e|es|ing) (?:in|inside|indoors)|mov\w*|take\w*|lift\w*|"
            r"put\w*|place\w*|stand\w*|"
            r"overwinter\w*|transfer\w*"
        ),
        "move_light": r"mov\w*|put\w*|place\w*|stand\w*|shift\w*|relocat\w*|transfer\w*|give",
        # the verbs, never the nouns: "save the trimmings" is no cut (round 7's false agree)
        "prune": (
            r"cut(?!tings\b)\w*|prun(?!ings\b)\w*|trim(?!mings\b)\w*|clip(?!pings\b)\w*|"
            r"shorten\w*|shear\w*|snip\w*|chop\w*"
        ),
        "treat_or_remove": _TREATS,
        "remove_plant": _TREATS,
    }.items()
}
# the whole plant removed is not its affected parts (round 5's rule, which the model
# misses on live pages: "dig up and destroy mint plants affected by rust")
_WHOLE_PLANT = re.compile(
    r"\b(?:remov|destroy|dig|pull|lift|bin|burn|dispos)\w*\b[^.;]{0,25}\bplants?\b", re.I
)


def _plain(sentence: str) -> str:
    return sentence.replace("’", "'")


_BACKING = frozenset().union(*SAME_ADVICE.values())  # every form action that can agree
# a cut of the whole plant, or down to the ground or base, is a hard cut, not a trim
# (round 7's false agree: "cut the whole plant down to just above the base")
_HARD_CUT = re.compile(
    r"\b(?:whole plant|(?:down )?to (?:just )?(?:above )?the (?:ground|base)|to ground level)\b",
    re.I,
)


def could_agree(sentence: str, action: str | None = None) -> bool:
    """The sentence names one of our actions (this action's, when given) in its own words.
    decide never agrees with one that does not, whatever its form, so only these are
    worth a read (21 Oct)."""
    actions = SAME_ADVICE.get(action, frozenset()) if action else _BACKING
    return any(_SAYS[a].search(_plain(sentence)) for a in actions)


def months_in(value: str) -> set[int] | None:
    """The months a month_range names ("spring", "October", "March to May"); None when
    it can't be read."""
    said = re.findall(r"[A-Za-z]+", value)
    words = [w.lower() for w in said]
    # "may" is the month only as "May" or after a timing word ("late may", "in may"):
    # "may indicate" is the verb (search probe, 19 Oct)
    for i, w in enumerate(words):
        if w == "may" and said[i] != "May" and (not i or words[i - 1] not in _MAY_AFTER):
            words[i] = ""
    named = [w for w in words if w in _SEASONS or w in _MONTHS]
    if not named:
        return None
    if len(named) == 2 and named[0] in _MONTHS and named[1] in _MONTHS and "to" in words:
        a, b = _MONTHS[named[0]], _MONTHS[named[1]]
        return {(a + i - 1) % 12 + 1 for i in range((b - a) % 12 + 1)}
    out: set[int] = set()
    for i, w in enumerate(words):
        part = _PART.get(words[i - 1]) if i else None
        if w in _SEASONS:
            # "late autumn" is November, not October
            out |= {_SEASONS[w][part]} if part is not None else set(_SEASONS[w])
        elif w in _MONTHS:
            out.add(_MONTHS[w])
    return out


def holds(c: Condition, s: PlantState) -> bool | None:
    """True or False when the state can tell; None when it can't (an unknown, or a kind
    we cannot check)."""
    v = c.value.strip().lower()
    if _STRENGTH.search(v) and c.kind not in ("month_range", "named_problem"):
        return None
    match c.kind:
        case "soil_dry":
            return None if s.soil is None else s.soil == "dry"
        case "soil_wet":
            return None if s.soil is None else s.soil == "wet"
        case "cold_or_frost_forecast":
            return s.cold_ahead
        case "hot_dry_weather":
            return s.hot_dry
        case "rain_forecast":
            return s.rain_ahead
        case "container":
            if s.container == "unknown" or not v:
                return None
            return v.startswith(("pot", "container", "tub")) == (s.container == "pot")
        case "month_range":
            ms = months_in(c.value.strip())  # its own case: "May" is the month, "may" may not be
            return None if ms is None else s.month in ms
        case "indoor":
            return None if s.setting == "unknown" else s.setting == "indoor"
        case "outdoor":
            return None if s.setting == "unknown" else s.setting == "outdoor"
        case "named_problem":
            if not v or s.problem is None:
                return None if not v else False
            p = s.problem.lower()
            return v in p or p in v
        case "plant_stage":
            return s.seedlings if "seedling" in v else None
    return None  # "plant_trait", "other": a condition we cannot check


def unconfirmed(sentence: str, s: PlantState) -> bool:
    """What the sentence itself names that the state can't confirm, whatever the form
    says: a strength (heavy rain, hard frost), a quality of the plant (leggy, young), or
    beds when the plant is in a pot (and pots when it is in the ground)."""
    if _STRENGTH.search(sentence) or _TRAIT.search(sentence):
        return True
    if _GROUND_WORDS.search(sentence) and s.container != "ground":
        return True
    return bool(_POT_WORDS.search(sentence)) and s.container != "pot"


def decide(form: Form | None, s: PlantState, sentence: str = "") -> Literal["agree", "unsure"]:
    if form is None or s.action not in SAME_ADVICE:
        return "unsure"
    if sentence and unconfirmed(sentence, s):
        return "unsure"
    if s.action == "prune" and (_PINCH.search(sentence) or _HARD_CUT.search(sentence)):
        return "unsure"
    if sentence and form.action in _SAYS and not _SAYS[form.action].search(_plain(sentence)):
        return "unsure"
    if sentence and form.action == "treat_or_remove" and _WHOLE_PLANT.search(sentence):
        return "unsure"
    if not form.is_instruction or form.polarity != "do" or form.hedged:
        return "unsure"
    if form.action not in SAME_ADVICE[s.action]:
        return "unsure"
    if form.applies_to == "other_plant":
        return "unsure"
    if form.applies_to == "plant_group":
        members = GROUPS.get(form.group.strip().lower())
        if members is None or s.plant not in members:
            return "unsure"
    if any(holds(c, s) is not True for c in form.conditions):
        return "unsure"
    if form.action in ("treat_or_remove", "remove_plant") and not any(
        c.kind == "named_problem" for c in form.conditions
    ):
        return "unsure"  # it must name the problem we found, or it backs nothing
    return "agree"
