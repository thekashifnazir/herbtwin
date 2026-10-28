"""Confidence built in code from factors (D26, D28, D33). The model is never asked for a
number: the advisor's high/low, agreement over 3 asks and the action's track record are
factors like any other. Weights and the fitted "N in 10" per level live in
data/confidence/weights.json (fitted by scripts/fit_confidence.py); the page shows two
levels in words instead (19 Oct answer-quality check).

Score = the chosen action's base (logit of its hit rate as primary) + each known factor's
weight. A missing factor adds nothing but is shown, so the strip says what is unknown.
"""

from __future__ import annotations

import calendar
import json
import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Literal

from herbtwin.plant_model import NO_LIGHT, ModelView, no_light_verdict
from herbtwin.schemas import (
    SOIL_FEEL_TEXT,
    CareAction,
    Chip,
    Effect,
    Factor,
    PhotoIssue,
    SoilFeel,
    TellMe,
    TexturePrior,
    coarse,
)
from herbtwin.seasonal import SeasonalNorm, normal_for

WEIGHTS_PATH = Path(__file__).resolve().parents[2] / "data" / "confidence" / "weights.json"
# "Choices compared" (the plant model's "Compare all choices"), not "2-week forecast": next
# to "Weather" the old name read as the same thing helping and not helping at once (17 Oct
# live re-walk); "Plant model" was dropped as jargon on 13 Oct
CHIPS = (
    "Season",
    "Photo",
    "Choices compared",
    "Agreement",
    "Lead advisor sure",
    "Weather",
    "Soil",
    "Light",
    "History",
)
# how many advisors agreed and whether they said they were sure are two things: as one
# "Agreement" chip, "Held back: agreement" sat beside "3 advisors agreed" when all 3 agreed
# but called it unsure (23 Oct, Kash on rev 00089: what does that mean?). The sureness is
# the lead advisor's own rating of its call (Panel.advisor, the chosen ask's), so it is its
# own chip, named for what it says
ADVISORS_SURE = "Lead advisor sure"
SAID_AS = {
    ADVISORS_SURE: {"raises": "The lead advisor was sure", "lowers": "The lead advisor wasn't sure"}
}
CHIP_OF = {
    "season": "Season",
    "season_evidence": "Season",
    "species": "Photo",
    "photo_quality": "Photo",
    "setting": "Photo",
    "plant_model": "Choices compared",
    "plant_model_margin": "Choices compared",
    "container": "Choices compared",
    "care_facts": "Choices compared",
    "advisor": ADVISORS_SURE,  # but a rule of ours leading is about agreement (chip_of)
    "agreement": "Agreement",
    "repair": "Agreement",
    "weather": "Weather",
    "forecast_distance": "Weather",
    "weather_explains": "Weather",
    "cold_nights": "Weather",
    "soil": "Soil",
    "soil_feel": "Soil",
    "soil_texture": "Soil",
    "light": "Light",
    "history": "History",
}
# evidence tiers (docs/reference/risk-models.md) in words a gardener reads on the page
_TIER_WORDS = {
    "A": "published studies",
    "B": "a model proven on a related crop",
    "C": "RHS or extension guidance",
    "D": "a gardeners' rule of thumb",
}
# two levels on the page, not three numbers (19 Oct answer-quality check, pre-registered on
# 624 held-out questions): "about 7 in 10" matched the gardener's answer 0.51 [0.45, 0.57],
# and the middle level (0.31) was no better than the bottom (0.32), so both read "not sure"
LEVEL_TEXT = {
    "not_sure": "Not sure: check first",
    "fairly_sure": "Not sure: do the quick check first, or take the low-risk step",
    "sure": "Our best read: go ahead, and keep an eye on it",
}
MODELLED = frozenset({"water", "dont_water", "shelter", "move_light", "leave_normal"})
RESTING = frozenset({"normal_dieback", "dormant", "leaf_fall"})
_SKIP_WORDS = {"leaf", "leaves", "stem", "stems", "plant", "plants", "with", "from", "that"}

Level = Literal["not_sure", "fairly_sure", "sure"]


@dataclass(frozen=True)
class FactorInputs:
    action: CareAction
    advisor: Literal["high", "low"]
    agree: int
    total: int
    repaired: bool
    species_conf: float | None
    match_how: str
    photo_quality: Literal["good", "poor"]
    quality_note: str
    norm: SeasonalNorm | None
    season_missing: Literal["no_norm", "outside_uk", "no_location", "indoors"] | None
    plant_key: str | None
    month: int
    symptoms: list[str]
    decline: int
    view: ModelView | None  # the plant model's view of the chosen action
    others_better: bool  # for leave it: does the plant model rate any action better?
    model_missing: Literal["indoors", "no_weather"] | None
    container: Literal["pot", "ground", "unknown"]
    setting: Literal["indoor", "outdoor", "unknown"]
    weather_ok: bool
    weather_missing: Literal["fetch_failed", "no_location", "indoors", "photo_too_old"] | None
    cold_nights_14: int
    explains: bool  # recent weather explains the symptom (answer.weather_explains)
    pack_verified: bool | None
    soil_surface: Literal["dry", "moist", "wet", "not_visible"]
    has_location: bool
    soil_feel: SoilFeel | None = None  # the person's finger test, after a refine
    history_days: int | None = None  # days since the plant's last visit (60 days at most)
    light_factor: tuple[Effect, str] | None = None  # from light.light_factor (C1)
    # the spot answer's inputs (spot spec section 8, D73); used only with spot_on
    spot_on: bool = False
    texture: TexturePrior | None = None  # for a plant in the ground
    light_known: bool = False  # a light class from visits or from a compass tap
    # a rule of ours chose the lead (pipeline.follow_the_twin, tender_first, in_proportion):
    # advisor is then "low" for the weight, but the words must not blame an unsure advisor.
    # Implies a low advisor: with it set, the advisor factor always lowers
    rule_led: bool = False


# a poor photo the read still named fairly confidently is not a rough read. 0.6 is the
# pre-registered blur probe's pick (data/eval/reports/2026-10-19-blur-probe.md, 456 reads):
# it flags 3.3% of sharp photos and 95% of heavily blurred ones; 0.8 flagged 6.0% of sharp
SURE_NAME = 0.6
# the read's own words for a shared frame: the prompt asks it to say so in quality_note.
# The count sits next to its noun (one word between at most), and "other" and "many" are
# left out: the prompt lets one plant have "other plants at the edges", and "multiple stems
# of plants" is one plant. "pots of" is one plant in several pots
SEVERAL = re.compile(
    r"\b(?:(?:several|multiple|mixed|various|different|two|three|four|five|a few)\s+"
    r"(?:\w+\s+)?|(?:row|group|collection|mix|trough|planter) of\s+(?:\w+\s+)?)"
    r"(?:plants|herbs|species|kinds|pots(?!\s+of))\b",
    re.IGNORECASE,
)
# the photo's own blur, not its background's (a sharp macro reads "blurred background")
_BACKGROUND = re.compile(
    r"\b(?:blurr?ed|blurry|soft|out[- ]of[- ]focus)\s+background\b"
    r"|\bbackground\s+(?:is\s+)?(?:out[- ]of[- ]focus|blurr?(?:ed|y)|blur|soft)\b"
    r"|\bbokeh\b|\bshallow depth of field\b",
    re.I,
)
# what is wrong with the photo, in the read's own words; a colour or a spot on the plant
# ("dark green leaves", "dark spots", "small leaves") is the plant, not the photo
_ISSUES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "blurry",
        re.compile(
            r"\bblur|\bout[- ]of[- ]focus|\bsoft[- ]focus|\bunfocus|\bnot in focus|\bfuzzy",
            re.I,
        ),
    ),
    (
        "dark",
        re.compile(
            r"\b(?:too |very )?dark\b(?!\s+(?:green|red|purple|brown|spots?|patch\w*|leaf|"
            r"leaves|markings?|veins?|stems?|edges?|soil|compost|background|backdrop|shade))"
            r"|\bdim(?:ly)?\b|\bunderexposed|\bpoorly lit|\blow light|\bin shadow",
            re.I,
        ),
    ),
    (
        "small",
        re.compile(
            r"\bsmall in (?:the )?frame|\b(?:plant|subject|herb)\s+(?:is\s+)?"
            r"(?:small|tiny|distant|far)\b|\bfar away|\btoo far|\bfrom a distance",
            re.I,
        ),
    ),
)


def photo_issue(
    quality: str, note: str, species_conf: float | None, sure_name: float = SURE_NAME
) -> PhotoIssue | None:
    """What makes this a rough read, from the read's own poor flag and note, or None. Only
    when the plant's name is unsure too: a poor flag on a confidently named plant is the
    read being careful. Several plants in one frame is said elsewhere, not as a retake."""
    if quality != "poor" or (species_conf is not None and species_conf >= sure_name):
        return None
    said = _BACKGROUND.sub(" ", note)
    for issue, pattern in _ISSUES:
        if pattern.search(said):
            return issue  # type: ignore[return-value]
    return None if SEVERAL.search(said) else "unclear"


@dataclass(frozen=True)
class Assessment:
    level: Level
    in_ten: int
    score: float
    factors: list[Factor]
    chips: list[Chip]
    tell_me: str | None
    tell_me_key: TellMe | None = None
    photo_issue: PhotoIssue | None = None


@dataclass
class _Acc:
    weights: dict
    rows: list[tuple[Factor, float]] = field(default_factory=list)

    def add(self, name: str, effect: Effect, detail: str) -> None:
        w = 0.0
        if effect in ("raises", "lowers"):
            w = self.weights["factors"].get(name, {}).get(effect, 0.0)
        self.rows.append((Factor(name=name, effect=effect, detail=detail), w))


@cache
def load_weights(path: Path = WEIGHTS_PATH) -> dict:
    return json.loads(path.read_text())


def first_dieback_month(plant_key: str, month: int) -> bool:
    """The month whose status first includes normal_dieback, or the previous month's
    next_change_month (D33)."""
    now = normal_for(plant_key, month)
    before = normal_for(plant_key, 12 if month == 1 else month - 1)
    if now is None or "normal_dieback" not in now.status:
        return False
    if before is None:
        return True
    return "normal_dieback" not in before.status or before.next_change_month == month


# the shown signs say "underground stems" for a beginner (16 Oct); a photo read may still
# say rhizome, so it is read as the plain words
_PLAIN = {"rhizomes": "underground stems", "rhizome": "underground stems"}


def _content_words(text: str) -> set[str]:
    words = " ".join(_PLAIN.get(w, w) for w in text.replace(",", " ").split()).split()
    return {w for w in words if len(w) >= 4 and w not in _SKIP_WORDS}


def matches_sign(sign: str, symptoms: list[str]) -> bool:
    """Does any symptom the photo reader named describe this norm sign? Whole-phrase
    containment either way, or two shared content words (one when the symptom has one)."""
    s = sign.casefold()
    sw = _content_words(s)
    for sym in symptoms:
        t = sym.casefold().strip()
        if not t:
            continue
        if t in s or s in t:
            return True
        tw = _content_words(t)
        if len(sw & tw) >= 2 or (len(tw) == 1 and tw <= sw):
            return True
    return False


# signs that only make sense inside: "brought indoors", "near a radiator", "kept in a warm
# room", "a cold windowsill", "touching cold window glass"
_INDOORS = re.compile(r"\b(?:indoors?|radiators?|warm room|windowsills?|window glass)\b", re.I)


def _season(acc: _Acc, i: FactorInputs) -> None:
    month = calendar.month_name[i.month]
    if i.norm is None:
        if i.season_missing == "no_norm" and i.action == "leave_normal":
            acc.add("season", "lowers", "no UK season norm for this plant: 'normal now' unchecked")
        else:
            reason = {
                "no_norm": "no season norm for this plant",
                "outside_uk": "outside the UK: UK season norms do not apply",
                "no_location": "location unknown",
                "indoors": "indoors: the UK outdoor season does not apply",
                None: "season unknown",
            }[i.season_missing]
            acc.add("season", "missing", reason)
        return
    # a sign about plants kept or brought indoors says nothing about one outside (18 Oct
    # judge walk: outdoor basil lowered by "grey fuzzy mould ... brought indoors")
    signs = [s for s in i.norm.problem_signs if not (i.setting == "outdoor" and _INDOORS.search(s))]
    hit = next((s for s in signs if matches_sign(s, i.symptoms)), None)
    if hit:
        acc.add("season", "lowers", f"the photo shows a problem sign for {month}: {hit}")
    elif i.action == "leave_normal" and RESTING & set(i.norm.status) and i.decline >= 1:
        status = ", ".join(s.replace("_", " ") for s in i.norm.status)
        acc.add("season", "raises", f"{i.norm.plant}: {status} is normal in {month}")
    else:
        acc.add("season", "neutral", f"season known for {month}")
    tier = i.norm.evidence_tier
    effect: Effect = "raises" if tier in ("A", "B") else "lowers" if tier == "D" else "neutral"
    said = _TIER_WORDS.get(tier, _TIER_WORDS["D"])  # crops.py types the tier as a plain str
    acc.add("season_evidence", effect, f"what is normal this month comes from {said}")
    if i.action == "leave_normal" and i.plant_key and i.weather_ok:
        if first_dieback_month(i.plant_key, i.month):
            n = i.cold_nights_14
            detail = f"{n} cold nights this fortnight" if n else COLD_NIGHTS_NOT_YET
            acc.add("cold_nights", "raises" if n else "lowers", detail)


def _photo(acc: _Acc, i: FactorInputs) -> None:
    if i.species_conf is None:
        acc.add("species", "missing", "plant not identified")
    elif i.species_conf >= 0.7 and i.match_how in ("exact", "binomial"):
        acc.add("species", "raises", f"plant identified ({i.species_conf:.0%})")
    elif i.species_conf < 0.4 or i.match_how == "genus":
        acc.add("species", "lowers", "plant identity unsure or genus only")
    else:
        acc.add("species", "neutral", f"plant identified ({i.species_conf:.0%})")
    if i.photo_quality == "poor":
        acc.add("photo_quality", "lowers", f"photo is poor: {i.quality_note or 'hard to read'}")
    else:
        acc.add("photo_quality", "neutral", "photo is clear")
    if i.setting == "unknown":
        acc.add("setting", "missing", "indoors or outdoors unknown")
    else:
        acc.add("setting", "raises", f"known to be {i.setting}s")  # not a bare "outdoor"


# never dropped for "N of 3 agree" (unlike "the advisor was sure"): the count alone does not
# say why a minority call leads
RULE_LED = "one of our rules chose this, not the advisors"


def _agreement(acc: _Acc, i: FactorInputs) -> None:
    if i.rule_led:
        acc.add("advisor", "lowers", RULE_LED)
    else:
        acc.add(
            "advisor",
            "raises" if i.advisor == "high" else "lowers",
            "the advisor was sure" if i.advisor == "high" else "the advisor was not sure",
        )
    text = f"{i.agree} of {i.total} agree"
    if i.agree == i.total == 3:
        acc.add("agreement", "raises", text)
    elif i.agree == 0 or (i.agree == 1 and i.total >= 2):
        # 0: a rule of ours led and no advisor chose it (pipeline.tender_first, in_proportion)
        acc.add("agreement", "lowers", text)
    else:
        acc.add("agreement", "neutral", text)
    if i.repaired:
        # plain words: the page shows this line (judge walk of #272: "malformed")
        acc.add("repair", "lowers", "one of the advisor's replies needed a second try")


def _plant_model(acc: _Acc, i: FactorInputs) -> None:
    if i.action not in MODELLED:
        return
    if i.view is None:
        why = (
            "indoors: no 2-week forecast" if i.model_missing == "indoors" else "no 2-week forecast"
        )
        acc.add("plant_model", "missing", why)
        return
    if i.action in ("leave_normal", "dont_water"):
        acc.add("plant_model", "lowers" if i.others_better else "raises", i.view.why)
    else:
        effect: Effect = {"better": "raises", "worse": "lowers", "same": "neutral"}[
            i.view.vs_leaving_it
        ]
        vs = {"better": "better than", "worse": "worse than", "same": "no different from"}
        # the twin can't model light: its "same" for moving it is no verdict on light
        said = (
            NO_LIGHT
            if no_light_verdict(i.view)
            else f"{vs[i.view.vs_leaving_it]} leaving it: {i.view.why}"
        )
        acc.add("plant_model", effect, said)
    tip = i.view.tip_day
    if tip is not None and tip <= 2:
        acc.add("plant_model_margin", "lowers", "harm could come within 2 days, so timing is tight")
    else:
        acc.add("plant_model_margin", "raises", "no harm due within 2 days")
    container: dict[str, tuple[Effect, str]] = {
        "pot": ("raises", "in a pot, as the model assumes"),
        "ground": ("lowers", "in the ground (the model assumes a pot)"),
        "unknown": ("missing", "pot or ground unknown"),
    }
    if i.setting != "indoor":  # indoors there is no ground: "the model assumes a pot" is moot
        acc.add("container", *container[i.container])
    if i.action in ("water", "shelter") and tip is not None:
        if tip <= 3:
            acc.add(
                "forecast_distance",
                "raises",
                f"the risk is {tip} day{'' if tip == 1 else 's'} away",
            )
        elif tip >= 8:
            acc.add("forecast_distance", "lowers", f"the risk is {tip} days away")


def _weather(acc: _Acc, i: FactorInputs) -> None:
    if not i.weather_ok:
        reason = {
            "fetch_failed": "weather fetch failed",
            "photo_too_old": "photo older than the 2-week weather record",
            "no_location": "no location",
            "indoors": "indoors",
            None: "no weather",
        }[i.weather_missing]
        acc.add("weather", "missing", reason)
    elif i.action in ("water", "shelter"):
        acc.add("weather", "raises", "forecast available")
    else:
        acc.add("weather", "neutral", "forecast available")
    if i.explains:
        acc.add("weather_explains", "raises", "recent weather explains what the photo shows")


def _care_and_soil(acc: _Acc, i: FactorInputs) -> None:
    if i.pack_verified is None:
        acc.add("care_facts", "missing", "no care facts")
    elif i.pack_verified:
        acc.add("care_facts", "raises", "care facts verified")
    else:
        acc.add("care_facts", "lowers", "generic care facts")
    s = i.soil_surface
    if s == "not_visible":
        acc.add("soil", "missing", "soil surface not visible")
    elif i.action not in ("water", "dont_water"):
        acc.add("soil", "neutral", f"soil surface looks {s}")
    else:
        fits = (i.action == "water" and s == "dry") or (i.action == "dont_water" and s != "dry")
        clash = (i.action == "water" and s == "wet") or (i.action == "dont_water" and s == "dry")
        effect: Effect = "raises" if fits else "lowers" if clash else "neutral"
        acc.add("soil", effect, f"soil surface looks {s}")
    feel = i.soil_feel
    if feel is None:
        acc.add("soil_feel", "missing", "how the soil feels 2 cm down")
    else:
        wet = feel in ("damp", "wet")
        if i.action == "water":
            feel_effect: Effect = "raises" if feel == "dry" else "lowers" if wet else "neutral"
        elif i.action == "dont_water":
            feel_effect = "raises" if wet else "lowers" if feel == "dry" else "neutral"
        else:
            feel_effect = "neutral"
        acc.add(
            "soil_feel", feel_effect, f"soil feels {SOIL_FEEL_TEXT[feel]} 2 cm down (you told us)"
        )
    if i.light_factor is None:
        acc.add("light", "missing", "light not known yet")
    else:
        acc.add("light", *i.light_factor)
    if i.history_days is None:
        acc.add("history", "missing", "no earlier photos yet")
    else:
        acc.add("history", "raises", f"earlier visit {i.history_days} days ago")


STRONG_MAP = 0.7  # a map prior this sure, on open ground, counts like a squeeze


def _soil_texture(acc: _Acc, i: FactorInputs) -> None:
    """D73: missing when unknown; neutral for pots; raises when the band supports a
    watering or drainage call for a plant in the ground; lowers when clay contradicts
    watering."""
    t = i.texture
    if i.setting == "indoor":  # no soil map under a room: a pot of bought compost, said or not
        return
    if i.container != "ground":
        if i.container == "pot":
            acc.add("soil_texture", "neutral", "in a pot: bought compost")
        return
    if t is None or t.source == "none":
        acc.add("soil_texture", "missing", "soil texture not known")
        return
    band = t.top
    sure = t.source == "squeeze" or t.probs.get(band, 0.0) >= STRONG_MAP
    said = "your squeeze test" if t.source == "squeeze" else "the soil maps"
    detail = f"{said}: {band} soil"
    if not sure:
        acc.add("soil_texture", "neutral", detail)
    elif i.action == "water":
        effect: Effect = (
            "lowers" if band == "clayey" else "raises" if band == "sandy" else "neutral"
        )
        acc.add("soil_texture", effect, detail)
    elif i.action == "dont_water":
        acc.add("soil_texture", "raises" if band == "clayey" else "neutral", detail)
    else:
        acc.add("soil_texture", "neutral", detail)


AGREE_COUNT = re.compile(r"\b\d+ of \d+ agree\b")
# why no cold nights lowers it (a measured weight): the die-back it is told to leave may not
# have begun. "No cold nights yet" alone read as good news under "Lowered it" (judge live
# walk of rev 00040)
COLD_NIGHTS_NOT_YET = "no cold nights yet, so the autumn die-back may not have begun"


# our own workings, never a fact about the plant: a reply that needed a second try still
# weighs (fitted), but "needed a second try" on the page read as a doubt (22 Oct site walk)
UNSAID = frozenset({"repair"})


def chip_of(f: Factor, split: bool = True) -> str:
    """The chip a factor counts under. `split=False`: the one "Agreement" chip as it was
    before the advisors' own sureness had its own, which "Mostly:" still reads (fold_reasons),
    so the line beside the level says what it said before."""
    if f.name == "advisor" and (f.detail == RULE_LED or not split):
        return "Agreement"
    return CHIP_OF[f.name]


def chip_name(key: str, effect: Effect) -> str:
    """The chip as the page says it: the advisors' sureness says which way it went."""
    return SAID_AS.get(key, {}).get(effect, key)


def _chips(rows: list[tuple[Factor, float]], split: bool = True) -> list[Chip]:
    """One row per chip, under its net effect (22 Oct site walk: "3 of 3 agree" under Helped
    and "needed a second try" under Lowered; Season under Lowered and under No effect). Its
    reasons are the ones that pushed it that way, and a reason that lowered it is never
    hidden: in a row that nets to Helped or No effect it ends the row as "…, but …" (review
    of the branch: "1 of 3 agree" vanished under "Agreement: the advisor was sure")."""
    chips = []
    # no plant model means no forecast: care facts alone must not read as "Helped: 2-week
    # forecast" on a page that just said the weather was unavailable (17 Oct walk)
    no_model = any(f.name == "plant_model" and f.effect == "missing" for f, _ in rows)
    for name in CHIPS if split else tuple(c for c in CHIPS if c != ADVISORS_SURE):
        mine = [(f, w) for f, w in rows if chip_of(f, split) == name]
        if name in SAID_AS and not mine:
            continue  # a rule of ours led: no advisor's sureness to say, not a missing one
        known = [(f, w) for f, w in mine if f.effect != "missing"]
        said = [(f, w) for f, w in mine if f.name not in UNSAID]
        total = sum(w for _, w in known)
        effect: Effect
        if not known or (name == "Choices compared" and no_model):
            effect = "missing"
        elif total > 0:
            effect = "raises"
        elif total < 0:
            effect = "lowers"
        else:
            effect = "neutral"
        # what did lower it: a "lowers" line with a negative weight (repair's is not)
        low = _once([f.detail for f, w in said if f.effect == "lowers" and w < 0])
        if effect == "missing":
            # only what is missing: "care facts verified" under Missing read as missing
            # (22 Oct site walk), and beside it under Helped as helped and missing at once
            # (#281 review)
            why = [f.detail for f, _ in said if f.effect == "missing"]
        elif effect == "lowers":
            # a reason with no weight never sits under "Lowered it": it did not lower it, and
            # "Lowered it · Weather: …; forecast available" read as good news there (judge
            # live walk of rev 00040)
            why = low
        else:
            # beside "Helped" a reason with no weight reads as part of what helped, as before
            up = _once([f.detail for f, _ in said if f.effect in ("raises", "neutral")])
            why = up[:-1] + [f"{up[-1]}, but {_but(low)}"] if up and low else up or low
        if name in SAID_AS and effect in SAID_AS[name]:
            why = []  # its name says it: "Advisors weren't sure", not "…: the advisor was not sure"
        chips.append(Chip(name=chip_name(name, effect), effect=effect, why=why, key=name))
    return chips


def _but(low: list[str]) -> str:
    """The lowering reasons after "but": a count says how few ("but only 1 of 3 agree")."""
    return " and ".join(f"only {w}" if AGREE_COUNT.fullmatch(w) else w for w in low)


def fold_reasons(factors: list[Factor], weights: dict | None = None) -> str:
    """Every reason the How sure fold says, as one text: what "Mostly:" may name (#review)."""
    w = (weights or load_weights())["factors"]
    rows = [(f, w.get(f.name, {}).get(f.effect, 0.0)) for f in factors]
    return " · ".join(x for c in _chips(rows, split=False) for x in c.why)


def _once(why: list[str]) -> list[str]:
    """Each reason once; and "3 of 3 agree" already says how sure the advisors were, so
    "the advisor was sure" beside it repeated it (19 Oct small-print re-check)."""
    if any(AGREE_COUNT.search(w) for w in why):
        why = [w for w in why if "the advisor was" not in w]
    return list(dict.fromkeys(why))


def _tell_me(i: FactorInputs, w: dict) -> tuple[TellMe, str] | None:
    """The missing input that would carry the most weight for this action."""
    f = w["factors"]
    options: list[tuple[float, TellMe, str]] = []
    if not i.has_location:
        weight = f["season"]["raises"] + f["weather"]["raises"] + f["plant_model"]["raises"]
        options.append(
            (
                weight,
                "location",
                "Tell us where the plant is and we'll check its weather, frost risk and whether "
                "this is normal for the season.",
            )
        )
    if i.soil_feel is None and i.action in ("water", "dont_water", "leave_normal"):
        options.append(
            (
                f["soil"]["raises"],
                "soil_feel",
                "Tell us how the soil feels 2 cm down and we'll say whether it needs water.",
            )
        )
    if i.setting == "unknown":
        options.append(
            (
                f["setting"]["raises"] + f["plant_model"]["raises"] / 2,
                "setting",
                "Tell us whether it is indoors or outside and we'll use the weather and a 2-week "
                "forecast for the plant.",
            )
        )
    if i.spot_on:
        options += _spot_tell_me(i, f)
    if not options:
        return None
    _, key, text = max(options)
    return key, text


def _spot_tell_me(i: FactorInputs, f: dict) -> list[tuple[float, TellMe, str]]:
    out: list[tuple[float, TellMe, str]] = []
    if i.action in ("move_light", "leave_normal") and i.setting == "outdoor" and not i.light_known:
        out.append(
            (
                f["light"]["raises"] + f["plant_model"]["raises"] / 2,
                "aspect",
                "Tell us which way it faces and we'll work out how much sun it gets.",
            )
        )
    no_squeeze = i.texture is None or i.texture.source != "squeeze"
    if i.container == "ground" and i.action in ("water", "dont_water") and no_squeeze:
        out.append(
            (
                f["soil_texture"]["raises"],
                "soil_texture",
                "Do the 1-minute squeeze test and we'll tell you how the soil drains.",
            )
        )
    return out


def assess(inp: FactorInputs, weights: dict | None = None) -> Assessment:
    w = weights or load_weights()
    acc = _Acc(w)
    _agreement(acc, inp)
    _photo(acc, inp)
    _season(acc, inp)
    _plant_model(acc, inp)
    _weather(acc, inp)
    _care_and_soil(acc, inp)
    if inp.spot_on:
        _soil_texture(acc, inp)
    tell = _tell_me(inp, w)
    base = w["base"].get(coarse(inp.action), w["base"]["default"])
    score = base + sum(wt for _, wt in acc.rows)
    level_row = next(r for r in w["levels"] if r["below"] is None or score < r["below"])
    issue = photo_issue(inp.photo_quality, inp.quality_note, inp.species_conf)
    if issue and level_row["level"] == "sure":
        # a rough read is never "our best read", whatever else lines up (judge walk of #269)
        level_row = next(r for r in w["levels"] if r["level"] == "fairly_sure")
    return Assessment(
        level=level_row["level"],
        in_ten=max(1, min(10, int(level_row["in_ten"]))),
        score=round(score, 4),
        factors=[f for f, _ in acc.rows],
        chips=_chips(acc.rows),
        tell_me=tell[1] if tell else None,
        tell_me_key=tell[0] if tell else None,
        photo_issue=issue,
    )
