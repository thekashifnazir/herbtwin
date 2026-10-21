"""Assemble the Answer the page and the JSON API show (spec section 7).

Time tags come from code: the primary is "today", other actions "this week", the watch
line "keep an eye on". The primary card's reason is the advisor's first sentence; the
"Don't" card appears only when the plant model rates a tempting action worse than
leaving it.
"""

from __future__ import annotations

import calendar
import logging
import re
from collections import Counter
from collections.abc import Mapping
from functools import cache
from typing import Literal, NamedTuple

from herbtwin.advice_context import WeatherFacts
from herbtwin.confidence import LEVEL_TEXT, RESTING, RULE_LED, Assessment, load_weights
from herbtwin.consequences import NO_DATA, consequence_for
from herbtwin.indoor_care import IndoorCare
from herbtwin.plant_model import ModelView, shelters_from_cold, worth_doing
from herbtwin.schemas import (
    ActionCard,
    AnalysisRecord,
    Answer,
    CareAction,
    CompareRow,
    IndoorNow,
    Observation,
    ProblemSeen,
    coarse,
)
from herbtwin.seasonal import SeasonalNorm, load_norms
from herbtwin.stages.advise import COUNTS, PANEL_TEMPERATURES, Panel

log = logging.getLogger(__name__)

PHOTO_QUESTION = "Here is a photo of my plant. What should I do for it now, if anything?"
HEADLINES: dict[str, str] = {
    "water": "Water it.",
    "dont_water": "Hold off watering.",
    "move_light": "Move it to better light.",
    "shelter": "Protect it from the weather.",
    "treat_or_remove": "Treat it.",
    "prune": "Cut it back.",
    "feed": "Feed it.",
    "repot": "Repot it.",
    "change_soil": "Refresh its soil.",
    "check_pests": "Check under the leaves for pests.",
    "isolate": "Keep it away from your other plants.",
    "mulch": "Mulch around it.",
    "humidity": "Raise the humidity around it.",
    "rotate": "Turn the pot.",
}
TEMPTING: tuple[CareAction, ...] = ("water", "shelter", "move_light")
FORECAST_BECAUSE = "tested on your plant's twin, it does better than leaving it."
DONT_BECAUSE = "worse than leaving it."  # the card's "Tested on your plant's twin:" line says why
# why each extra (THIS WEEK) action helps. The season's "next change" line is about the plant's
# year, so it goes only with cutting back; under any other action it read as nonsense
# ("Check for pests: outdoor plant finished", live 13 Oct). Even there it says what the plant
# does next, not why to cut, so it follows the reason (Toloka dry run, 16 Oct)
ALSO_BECAUSE: dict[str, str] = {
    "water": "water only if the soil is dry 2 cm down.",
    "dont_water": "let the top of the soil dry a little before the next watering.",
    "move_light": "the light it gets now is not right for it.",
    "shelter": "the weather could harm it.",
    "treat_or_remove": "remove the worst leaves so the damage does not spread.",
    "prune": "cutting off old, dead or leggy stems makes room for fresh growth.",
    "check_pests": "look under the leaves and along the stems: a photo cannot show everything.",
    "isolate": "keep it apart so a pest or disease cannot spread to other plants.",
    "feed": "a feed helps while it is growing; skip it while it is dormant.",
    "repot": "the roots may need more room.",
    "change_soil": "fresh compost would help it.",
    "mulch": "a mulch keeps the roots moist and protected.",
    "humidity": "dry air can stress it.",
    "rotate": "turning it keeps the growth even.",
}
# a sourced "how" that says there is no cure: treating it means pulling it out and binning it
# (basil downy mildew). "Treat it." over that line, beside "Also do: Protect it", read as a
# contradiction (18 Oct pre-deploy); the cards that look after the plant go, and those that
# keep the problem from the other plants stay
NO_CURE = re.compile(r"\bno (?:known )?cure\b", re.I)
NO_CURE_HEADLINE = "Remove it. There is no cure for this."
# its card's reason, in place of the advisor's ("Remove the affected leaves" reads as a part
# against the sourced whole-plant removal, and the voice says it aloud)
NO_CURE_BECAUSE = "this disease has no cure, and it can spread to other plants of its kind."
NO_CURE_SEEN = "{seen}, which has no cure and can spread to other plants of its kind."
SPARES_THE_OTHERS: frozenset[str] = frozenset({"treat_or_remove", "isolate", "check_pests"})
SEASONAL_JOBS = frozenset({"prune"})  # actions whose reason ends with the season's next change
# perennial herbs that rest through the UK winter: from September to February a cut "to
# encourage bushier growth" asks for growth the plant will not make. The gardener's review
# (19 Oct, s012 oregano) quoted it beside our own "dies back further and rests through
# winter"; only a light tidy suits now, and the main cut-back waits for spring
WINTER_REST_HERBS = frozenset(
    {
        "origanum vulgare",
        "thymus vulgaris",
        "mentha",
        "mentha spicata",
        "salvia officinalis",
        "salvia officinalis 'purpurascens'",
        "salvia rosmarinus",
        "allium schoenoprasum",
        "allium tuberosum",
        "artemisia dracunculus",
        "melissa officinalis",
    }
)
WINTER_REST_MONTHS = frozenset({9, 10, 11, 12, 1, 2})
TIDY_HEADLINE = "Give it a light tidy."
TIDY_BECAUSE = (
    "only a light tidy now: dead material and the longest straggly tips. The main cut-back "
    "waits for spring."
)
# a cut for growth: "trim the leggy, woody stems to encourage bushier growth", "prune it to
# keep it compact", "pinch out the tips for new shoots"
_CUT = r"(?:trim|prun|cut|pinch|shear|clip)\w*"
_GROWTH = (
    r"(?:bush\w*|compact\w*|dens\w*|branch\w*|(?:new|fresh|more|leaf|leafy) "
    r"(?:growth|shoots?)|regrowth)"
)
_FOR_GROWTH = rf"\b{_CUT}\b[^.;!?]*?\b{_GROWTH}\b"
# a cut held back in its own clause: "wait until spring to cut it back for bushier growth",
# "don't prune for new growth now", "avoid heavy pruning". Right for a resting herb: kept
# whole. A hold-off word in another clause ("Don't overwater, and trim the tips for bushy
# growth") holds nothing back (second Opus review)
_HOLDS_OFF = re.compile(
    rf"\b(?:don['\u2019]?t|do not|never|avoid|hold off|wait\w*)\b[^,;]*?\b{_CUT}\b|"
    rf"\b{_CUT}\b[^,;.]*?\b(?:until|till) (?:the )?spring\b",
    re.I,
)
# the cut as the last clause after "and" or a semicolon, or as a bracket of its own: only
# then can it come off and leave a whole sentence. Never after a bare comma ("If the stems
# are leggy, prune them..." left "If the stems are leggy."), and never with more after it
_CLOSING_CUT = re.compile(
    rf"(?:\s*;\s*(?:and\s+)?|,?\s+and\s+(?:then\s+)?){_FOR_GROWTH}[^.;!?(),]*"
    rf"(?P<end>[.!?]?)\s*$",
    re.I,
)
_BRACKET_CUT = re.compile(rf"\s*\((?:and\s+)?{_FOR_GROWTH}[^()]*\)", re.I)


def winter_rest(plant_key: str | None, month: int) -> bool:
    return plant_key in WINTER_REST_HERBS and month in WINTER_REST_MONTHS


def _no_cut_for_growth(sentence: str) -> str | None:
    """The sentence less a closing clause or bracket that cuts the plant for growth; None
    when the cut sits anywhere else (the whole sentence goes, never a fragment). A sentence
    that holds the cut back stays whole. For a resting herb only: in spring the cut is right."""
    if not re.search(_FOR_GROWTH, sentence, re.I) or _HOLDS_OFF.search(sentence):
        return sentence
    if (m := _CLOSING_CUT.search(sentence)) and m.start() > 0:
        return sentence[: m.start()].rstrip() + (m.group("end") or ".")
    if m := _BRACKET_CUT.search(sentence):
        kept = sentence[: m.start()] + sentence[m.end() :]
        return kept if not re.search(_FOR_GROWTH, kept, re.I) else None
    return None


# a tender herb (harmed by a chill above freezing: basil) outside from October to March:
# bringing it in comes first. The gardener (s052 basil) found "Cut it back." over "Protect
# it" a missed priority for a stressed outdoor basil in mid-October
TENDER_MONTHS = frozenset({10, 11, 12, 1, 2, 3})
TENDER_HEADLINE = "Bring it indoors to a bright windowsill."
TENDER_BECAUSE = (
    "it is a tender plant: cold nights harm it, and from October to March it is safer indoors."
)
# the gardener's second half of the same step (s052): "check the tray: empty it if there is
# any water in it". Its own line under the reason, never part of it: the voice check counts
# the reason's words as said, and "water" or "compost" there would let a made-up watering
# line through. For a pot or an unknown container ("If it stands" covers no tray); a bed
# has none
TRAY_CHECK = (
    "If it stands in a tray or saucer, tip out any water there: roots left sitting in water "
    "can rot."
)
TENDER_BED_BECAUSE = (  # planted out, it cannot come in (Opus review: "safer indoors" for a bed)
    "it is a tender plant: cold nights harm it, so cover it before they come."
)
# a seasonal job the advisors led with out of its season (pipeline.in_season): the reason is
# ours, never their feeding line under another headline
WAITING_JOB = {
    "feed": "feeding it",
    "repot": "repotting it",
    "change_soil": "refreshing its soil",
    "mulch": "mulching it",
}
# the season after a colon: the voice line's first clause stops at the first comma, and
# "(best done in Jun, Jul…" left a bracket open there (review)
WAIT_BECAUSE = "{job} waits for its season, {then}{when}."
# one insect and no damage (s014 mint): a look and a flick, never "keep it away from your
# other plants", which the gardener found too much
PROPORTION_HEADLINE = "Check under the leaves, and flick off any insects you find."
PROPORTION_BECAUSE = (
    "the photo shows no sign of a pest doing harm, so there is no need to move it: keep it "
    "apart only if you see damage or more of them."
)
# a bed plant cannot be moved apart (judge walk: border rosemary), with or without harm
PROPORTION_BED_BECAUSE = (
    "the photo shows no sign of a pest doing harm: look again in a few days, and treat it if "
    "you see damage or more of them."
)
BED_TREAT_BECAUSE = (
    "it is in the ground, where it stays: deal with the pest where it is, so it does not "
    "spread to other plants."
)
# the photo's words for harm a pest or disease did, or a pest in numbers ("holes chewed",
# "sticky honeydew", "a colony of aphids"); not the colour of the insect itself ("a black
# insect"). Not "a few" or "several" of them, and not one spot: still out of proportion
# (19 Oct answer-quality check: "two aphids" and "one brown spot" kept isolation)
DAMAGE = re.compile(
    # one spot is not ("one brown spot"), but a spot disease is ("black spot", "leaf spot").
    # Rot is left out: a wet-root rot does not spread from plant to plant
    r"\b(?:holes?|holed|chew\w*|eaten|bitten|nibbl\w*|spots|spotted|patches|lesions?|"
    r"(?:black|leaf)[\s-]spot|"
    r"sticky|honeydew|sooty|web\w*|mottl\w*|stippl\w*|speckl\w*|silver\w*|"
    r"mou?ld\w*|mildew|rust\w*|pustules?|galls?|damage\w*|infest\w*|colon(?:y|ies)|"
    r"clusters?|swarm\w*|many|lots|spread\w*|trails?|mines?|mined|notch\w*|tunnel\w*|"
    # a pest in numbers: "covered in aphids", "a mass of greenfly", "whitefly on the leaves"
    r"cover\w*|dozens?|hundreds|mass(?:es)?|cluster\w*|crowd\w*|heav\w*|numerous|thick\w*|"
    r"greenfly|blackfly|whitefly|whiteflies|powdery)\b",
    re.I,
)
# pests by name, in the plural: a pest in numbers unless the photo counts only a few
# ("aphids on the shoot tips" is; "two aphids" or "several aphids" is not: 19 Oct)
_PESTS = re.compile(
    r"\b(?:insects|aphids|mites|thrips|mealybugs|caterpillars|beetles|bugs|grubs|weevils|"
    r"scales?\s+insects|scale|slugs|snails)\b",  # not larvae: ladybird larvae are friends
    re.I,
)
# the count right before the pest, with at most one describing word ("a few small
# insects"), never a count of something else ("several leaves with aphids", "a few hundred")
_FEW = re.compile(
    r"\b(?:a\s+few|few|several|a\s+couple(?:\s+of)?|a\s+pair\s+of|one|single|two|three)\s+"
    r"(?:(?!(?:leaves|leaf|stems?|shoots?|hundreds?|thousands?|dozens?|of)\b)\w+\s+)?$",
    re.I,
)
# keeping it apart, in the advisors' own words: never said of a bed plant (#304 review)
_APART = re.compile(
    r"\b(?:apart|away from (?:your |the |its )?other plants|isolat\w*|quarantin\w*|"
    r"separate (?:it|them|the plant))\b",
    re.I,
)
# harm that is only a pest's when a pest is there too: "leaves yellowing from aphids", but
# not "lower leaves yellowing", which old leaves do on their own
_PEST_HARM = re.compile(
    r"\b(?:yellow\w*|brown\w*|blacken\w*|wilt\w*|curl\w*|distort\w*|stunt\w*|scorch\w*)\b",
    re.I,
)
_PEST = re.compile(
    # not a bare fly or larva: hoverflies and ladybird larvae are friends
    r"\b(?:insects?|beetles?|bugs?|aphids?|nymphs?|caterpillars?|"
    r"mites?|thrips|mealybugs?|weevils?|grubs?|scale)\b",
    re.I,
)
# "no damage", up to a turn ("no damage visible but lots of aphids" still has aphids)
_NO_DAMAGE = re.compile(
    r"\b(?:no|not|without|free of|nothing)\b(?:(?!\b(?:but|and|though|although|yet|except)\b)"
    r"[^,;.])*",
    re.I,
)
# a colour that names the pest, not harm: "a small brown insect", "black aphids". Bare
# colours only, with at most one word between and never a preposition: "yellowing from
# aphids" is harm (second Opus review)
_PEST_COLOUR = re.compile(
    r"\b(?:brown|black|yellow|silver|rust|green|white|red|orange)(?:ish)?\b"
    r"(?=\s+(?:(?!(?:from|with|by|on|under|beneath|below|of|in|near|and|or)\b)\w+\s+)?"
    r"(?:insect|beetle|bug|aphid|fly|flie|nymph|caterpillar|larva|larvae|mite|weevil|grub|"
    r"slug|snail)s?\b)",
    re.I,
)


def visible_damage(obs: Observation, problem: ProblemSeen | None) -> bool:
    """The photo shows harm a pest or disease did, a pest in numbers, clear decline, or a
    listed problem: the cases where keeping it apart is in proportion. Yellowing leaves or a
    first sign of decline alone are not (autumn dieback, old leaves: 19 Oct)."""
    if problem is not None or obs.decline >= 2:
        return True
    for cue in [*obs.symptoms, *obs.leaf_cues]:
        # one cue at a time: old leaves yellowing beside one insect is not harm it did
        said = _PEST_COLOUR.sub(" ", _NO_DAMAGE.sub(" ", cue))
        if DAMAGE.search(said) or (_PEST_HARM.search(said) and _PEST.search(said)):
            return True
        if any(not _FEW.search(said[: m.start()]) for m in _PESTS.finditer(said)):
            return True
    return False


# with the soil unknown, a "Don't water it" is a blanket rule the photo cannot support (s014
# mint: "mint likes moist soil and pots under cover can dry out"): the card says the check
DONT_IF_DRY = "Water only if the top of the compost is dry"


def dont_if_dry(container: str) -> str:
    """The soil check's heading: "soil" for a plant in the ground, "compost" in a pot."""
    return DONT_IF_DRY.replace("compost", "soil") if container == "ground" else DONT_IF_DRY


DONT_IF_DRY_BECAUSE = (
    "we can't see the soil, and the twin found watering now does worse than leaving it."
)
# a season sign about the outdoor weather, which a plant indoors never meets
OUTDOOR_SIGN = re.compile(
    r"\b(?:outdoors?|outside|cold nights?|frosts?|frosty|mild spell|wet (?:late )?summers?|"
    r"rain|rainy|autumn gales?|wind|windy|froze\w*|freez\w*|winter|weather|dry spell|"
    r"sowings?|sown|slime)\b",
    re.I,
)
# ...unless it is about a place indoors ("a cold night by the window or behind curtains")
INDOOR_PLACE = re.compile(
    r"\b(?:windows?|windowsills?|curtains?|radiators?|rooms?|indoors?)\b", re.I
)


_INDOOR_ONLY = re.compile(
    r"\bindoors?\b|\bwindowsills?\b", re.I
)  # "indoor basil…", "kept on a sill"


def _indoor_sign(sign: str) -> bool:
    return bool(INDOOR_PLACE.search(sign)) or not OUTDOOR_SIGN.search(sign)


# the photo's own words for very young plants: they are thinned, never cut back
# (not "sprouts": Brussels sprouts, sprouting broccoli and "new shoots sprouting" are grown up)
SEEDLINGS = re.compile(r"\b(?:seedlings?|germinat\w*|cotyledons?|microgreens?|seed leaves)\b", re.I)


def is_seedlings(obs: Observation) -> bool:
    return bool(SEEDLINGS.search(" ".join([obs.notes, obs.quality_note, *obs.leaf_cues])))


# the photo's own words for a leaf herb gone over to flower and seed (judge live walk of rev
# 00040: a coriander "simply bolted" and in full flower was told to watch for slug-grazed
# sowings and rotting young rosettes)
BOLTED = re.compile(
    r"\b(?:bolt(?:ed|ing|s)?|flower(?:s|ing|ed)?(?!\s+(?:beds?|borders?|pots?|boxes)\b)|"
    r"bloom(?:s|ing)?|(?:going|gone|run(?:s|ning)?) to seed|seed ?heads?|umbels?)\b",
    re.I,
)
# the photo saying it has not bolted: "no flowers yet", "no signs of bolting", "hasn't
# bolted", "isn't flowering", and every item of "no flowers or seed heads" (Opus review)
_STAGE = r"(?:flower|bloom|seed|bolt|umbel)\w*(?:\s+heads?)?"
_NOT_YET = re.compile(
    rf"\b(?:no|not|never|without|free of|\w+n['’]t)\s+(?:\w+\s+){{0,3}}?{_STAGE}"
    rf"(?:\s*(?:,|or|nor|and)\s+(?:\w+\s+)?{_STAGE})*|"
    # only a risk or a future: "likely to bolt soon", "before it bolts", "at risk of
    # bolting", "it will flower next month" (integrator's review of #288). "Beginning to
    # bolt" and "going to seed" are happening now
    rf"\b(?:before|likely|risk|prone|liable|tends?|may|might|could|will|would|about to)"
    rf"\s+(?:\w+\s+){{0,3}}?{_STAGE}|"
    # a stage named and then denied: "bolting has not started", "flowering not yet"
    rf"\b{_STAGE}\s+(?:(?:has|have|had|is|was)\s+)?(?:not|n['’]t|yet to)\b",
    re.I,
)
# what a bolted leaf herb does next: the seasons' own signs are for young plants
BOLTED_SIGNS = (
    "Seed heads forming: pick the last good leaves now, or leave them to save seed",
    "Leaves turning sparse and bitter as it puts its energy into seed",
)


@cache
def _bolters() -> frozenset[str]:
    """The leaf herbs our season norms mark at risk of bolting (coriander, dill, parsley):
    for the rest, flowers are no change of stage worth a watch line."""
    return frozenset(n.plant for n in load_norms() if "bolting_risk" in n.status)


def is_bolted(obs: Observation, plant_key: str | None) -> bool:
    if plant_key is None or plant_key not in _bolters():
        return False
    said = " ".join([obs.notes, obs.quality_note, *obs.leaf_cues, *obs.symptoms])
    return bool(BOLTED.search(_NOT_YET.sub(" ", said)))


def _first_sentence(text: str) -> str:
    m = re.match(r"(.+?[.!?])(\s|$)", text.strip())
    return m.group(1) if m else text.strip()


def _plain(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.lower().replace("'", "")).split())


_HEAT = r"(?:temperatures?|the weather|weather|days?|nights?)\s+"  # "days get warmer" is heat
_WARMING = _HEAT + r"(?:rises?|warms?(?: up)?|gets? warmer|heats? up)"
_COOLING = _HEAT + r"(?:falls?|drops?|cools?(?: down)?|gets? colder)"
_LONGER = r"days?\s+(?:get longer|gets? longer|lengthens?|draws? out)"
_SHORTER = r"days?\s+(?:get shorter|gets? shorter|shortens?|draws? in)"
_TURN = "|".join((_WARMING, _COOLING, _LONGER, _SHORTER))
# "as temperatures rise" said in October (18 Oct, coriander in London, rev 00032): a clause
# about the season turning the wrong way for the month, said as what is happening now.
# Warmth is wrong from September to January, cooling from March to July; day length turns
# at the solstices, so lengthening is wrong from July to November, shortening from January
# to May. "when" and "once" set a condition for later ("feed it when the weather warms
# up"): advice, so they stay. The prompt is unchanged
_WRONG_TURN: dict[int, tuple[str, ...]] = {
    m: tuple(
        turn
        for turn, months in (
            (_WARMING, (9, 10, 11, 12, 1)),
            (_COOLING, (3, 4, 5, 6, 7)),
            (_LONGER, (7, 8, 9, 10, 11)),
            (_SHORTER, (1, 2, 3, 4, 5)),
        )
        if m in months
    )
    for m in range(1, 13)
}


def _in_season(sentence: str, month: int) -> str | None:
    """The sentence less a clause that turns the season the wrong way for the month; None
    when the sentence opens with one (nothing sensible is left)."""
    wrong = _WRONG_TURN[month]
    if not wrong:
        return sentence
    # the clause, with any second turn joined to it ("... rise and days lengthen")
    clause = (
        rf"(?:as|while)\s+(?:the\s+)?(?:{'|'.join(wrong)})\b"
        # "as temperatures rise and fall" is no turn of the season: keep it whole
        r"(?!\s+and\s+(?:falls?|drops?|rises?|cools?|warms?)\b)"
        rf"(?:\s+and\s+(?:the\s+)?(?:{_TURN})\b)?"
    )
    if re.match(rf"\s*{clause}", sentence, re.I):
        return None
    return re.sub(rf"(?:,\s*|\s+){clause}(?:\s*,(?=\s))?", "", sentence, flags=re.I)


# a reason line that is no reason: the mildew sample's "Treat it." came with "Ask omitted"
# (19 Oct small-print walk), a placeholder the advisor wrote in its answer field. The panel
# keeps any answer of 2 words, so the card checks again: no lone word, and a short line
# naming a placeholder is dropped
REASON_WORDS = 2  # "Bolting is normal." is a reason; a lone word is not
# the whole line is a placeholder, perhaps naming the field it stands for: "Ask omitted",
# "N/A", "None.", never a real reason that happens to start "None of the leaves..."
_PLACEHOLDER = re.compile(
    r"^(?:(?:ask|answer|reason|question|text|field)\s+)?"
    r"(?:omitted|n/?a|none|null|tbd|placeholder|not applicable|no (?:ask|question))"
    r"(?:\s+(?:here|given|needed|provided))?$",
    re.I,
)
_SENTENCES = re.compile(r"(.+?[.!?])(?:\s+|$)|(.+)$")  # as `_reason` reads them


def why_not_a_reason(sentence: str) -> str | None:
    """ "too short", "question" or "placeholder" when the line is no reason; None when it is
    one."""
    if len(re.findall(r"[A-Za-z]+", sentence)) < REASON_WORDS:
        return "too short"
    # a question asks the person and gives no reason (19 Oct judge walk, indoor basil: "Is
    # the plant currently receiving direct sunlight...?" sat under the headline)
    if sentence.rstrip().rstrip("\"')]}\u201d\u2019").endswith("?"):  # ...sun?" and ...light?)
        return "question"
    bare = re.sub(r"[^\w/ ]+", " ", sentence).strip()
    return "placeholder" if _PLACEHOLDER.match(" ".join(bare.split())) else None


def usable_reason(sentence: str) -> bool:
    return why_not_a_reason(sentence) is None


def _sentences(answer: str) -> list[str]:
    return [(m.group(1) or m.group(2) or "").strip() for m in _SENTENCES.finditer(answer.strip())]


_SEEN_TAIL = re.compile(r"\.?\s*(Seen (?:it|either)\? Send a new photo\.)$")


def watch_list(watch: str) -> tuple[list[str], str]:
    """Keep an eye on as a list (19 Oct pre-walk: the bullets ran together on a phone): the
    signs, and the line after them. A watch with no bullets is one line and no list."""
    if not watch.startswith("•"):
        return [], watch
    m = _SEEN_TAIL.search(watch)
    body, after = (watch[: m.start()], m.group(1)) if m else (watch, "")
    return [s.strip() for s in body.split("•") if s.strip()], after


# See it by part (21 Oct, gardener test: they wanted the advice by part of the setup): the
# plan's own lines sorted by the part they are about. A fourth row, Where it sits, holds
# light, shelter, turning and keeping it apart: in October the lead is often "Bring it
# indoors", which is not about the pot (a bed has none) and would otherwise drop out of the
# fold. Leave it, Check first and Something else are about no part
PARTS = ("Pot", "Soil", "Leaves and stems", "Where it sits")
PART_OF: dict[str, str] = {
    "repot": "Pot",
    "water": "Soil",
    "dont_water": "Soil",
    "feed": "Soil",
    "mulch": "Soil",
    "change_soil": "Soil",
    "prune": "Leaves and stems",
    "check_pests": "Leaves and stems",
    "treat_or_remove": "Leaves and stems",
    "isolate": "Where it sits",  # "Keep it apart": where it stands (Opus review)
    "humidity": "Leaves and stems",
    "move_light": "Where it sits",
    "shelter": "Where it sits",
    "rotate": "Where it sits",
}
# a watch sign by its words, the first match winning (every sign we can show is run through
# it in tests/test_answer_by_part.py). A pot left out, unwrapped or standing in water is the
# pot's; light and a cold window are where it sits; a sign with wet compost in it is about
# the watering even when the leaves show it; "at soil level" is a place on the stem
_SIGN_PARTS = (
    (
        "Pot",
        re.compile(
            r"\b(?:trays?|saucers?|drainage holes?|pot-?bound|root-?bound|"
            r"pot (?:standing|left|unwrapped|not wrapped)|standing in (?:rain or )?water)\b",
            re.I,
        ),
    ),
    (
        "Where it sits",
        re.compile(
            r"\b(?:windowsills?|sunny sill|direct (?:summer |midday )?sun|window glass|"
            r"(?:dim|dark) (?:spot|corner))\b",
            re.I,
        ),
    ),
    (
        "Soil",
        re.compile(r"\b(?:compost|soil(?! level)|waterlogged|sodden|soggy|roots?)\b", re.I),
    ),
    (
        "Leaves and stems",
        re.compile(
            r"\b(?:lea(?:f|ves|fy)|leaflets?|stems?|shoots?|fronds?|tips?|buds?|branch\w*|"
            r"twigs?|bark|segments?|crowns?|crosiers?|flower\w*|soil level|fuzz\w*|mould|"
            r"mildew|pests?|aphids?|greenfly|beetles?|larvae|slime|pustules?|spots?|holes)\b",
            re.I,
        ),
    ),
)


class PartItem(NamedTuple):
    text: str  # the plan's own words, as shown above the fold
    kind: Literal["do", "dont", "check", "watch"]  # its colour: green, clay, amber, amber


def part_of_sign(sign: str) -> str | None:
    """The part a Keep an eye on sign is about, or None when its words name none."""
    return next((part for part, words in _SIGN_PARTS if words.search(sign)), None)


def by_part(
    answer: Answer, label: Mapping[str, str], container: str = "unknown"
) -> list[tuple[str, list[PartItem]]]:
    """The plan's advice by part: each row's items in the plan's order, in the plan's
    words (`label` is the page's own card labels; `container` the photo's, which says soil
    or compost as the Check first card does). Empty rows are left out, and so is the whole
    fold when fewer than two rows have anything: one row only repeats the plan."""
    rows: dict[str, list[PartItem]] = {p: [] for p in PARTS}

    def add(part: str | None, text: str, kind: str) -> None:
        if part and text and text not in [i.text for i in rows[part]]:
            rows[part].append(PartItem(text, kind))

    # the main card says its headline, the first sentence of it; never "Remove it" with no
    # cure, which under Leaves and stems read as "remove the leaves" (Opus review)
    if answer.do and answer.headline != NO_CURE_HEADLINE:
        add(PART_OF.get(answer.do[0].action), answer.headline.split(". ")[0].rstrip("."), "do")
    for c in answer.do[1:]:
        tidy = c.action == "prune" and answer.winter_rest  # the template's own swap
        add(PART_OF.get(c.action), "Give it a light tidy" if tidy else label[c.action], "do")
    if answer.tray_check:
        add("Pot", TRAY_CHECK.split(":")[0], "do")  # a plain line on the card, no prefix
    if answer.dont is not None:
        if answer.dont_if_dry:
            add("Soil", dont_if_dry(container), "check")
        else:
            add(PART_OF.get(answer.dont.action), label[answer.dont.action], "dont")
    for sign in watch_list(answer.watch or "")[0]:
        add(part_of_sign(sign), sign, "watch")
    shown = [(p, items) for p, items in rows.items() if items]
    return shown if len(shown) >= 2 else []


def _lead_lower(sentence: str) -> str:
    """The sentence to follow a lead-in: its first word lower-cased unless it is a name, an
    acronym or "I" ("RHS advises…", "October…" stay)."""
    first = sentence.split(" ", 1)[0].strip(",.;:")
    one = len(first) == 1 and first != "I"  # "A light trim…": nothing after the capital to test
    keep = not one and (first == "I" or not first[1:].islower() or first in calendar.month_name)
    return sentence if keep else f"{sentence[:1].lower()}{sentence[1:]}"


def is_question(text: str) -> bool:
    """The person's words end in a question mark, before any closing quote, bracket or "!"."""
    return text.rstrip(" \"'”’!.)").endswith("?")


# the factor details in a gardener's words, for "Mostly: …" (C review): the fold keeps its own
# terser lines. A detail not here is said as it is
_PLAIN_DOUBT: dict[str, str] = {
    "species": "we're not sure which plant this is",
    "photo_quality": "the photo is hard to read",
    "repair": "one of the advisors' replies needed a second try",
    "care_facts": "we only have general care facts for it",
    "container": "it grows in the ground, and our model assumes a pot",
    "light": "the light it gets may not suit this job",
}
_AGREE = re.compile(r"^(\d+) of (\d+) agree$")


def _plain_doubt(name: str, detail: str) -> str:
    if name in _PLAIN_DOUBT:
        return _PLAIN_DOUBT[name]
    if name == "advisor":
        return (
            "a safety rule of ours overrode the advisors' choice"
            if detail == RULE_LED
            else "the advisors weren't confident"
        )
    if m := _AGREE.match(detail):
        return f"only {m[1]} of {m[2]} advisors agreed"
    if detail.startswith("no UK season norm"):
        return "we have no season notes for this plant"
    if detail.startswith("the photo shows a problem sign for ") and ": " in detail:
        # a whole season sign ran to 50 words on the page (preview of C): the sign alone
        month, sign = detail.removeprefix("the photo shows a problem sign for ").split(": ", 1)
        return f"the photo shows a sign of trouble for {month}: {short_sign(sign).lower()}"
    # one line beside the level: a detail stops at its first add-on
    return re.split(r";\s| \(", detail, maxsplit=1)[0].rstrip(" .")


# when the main action's own record weighs more than any single factor: "Mostly" must be true
# (#321 review: leave_normal's base is -0.94 against a -0.06 factor). No "in our tests":
# the line under the badge says that just before it (21 Oct)
BASE_DOUBT = "advice of this kind is right less often"


def top_doubt(answer: Answer) -> str | None:
    """The one thing that lowered our sureness most, in plain words, for the line beside "How
    sure we are" (design wave 1, C): the reason was two screens down, folded. Only a factor
    that did lower it (a negative weight), and never one the fold leaves out: beside "N of 3
    agree", "the advisor was not sure" is dropped there, so it is passed over here too."""
    table = load_weights()
    weights = table["factors"]
    # the fold hides "the advisor was not sure" only beside an agreement line that lowered it
    # too (confidence._once joins same-effect lines): 2 of 3 is neutral, so it stays there
    counted = any(f.name == "agreement" and f.effect == "lowers" for f in answer.factors)
    lows = [
        (w, i, f)
        for i, f in enumerate(answer.factors)
        if f.effect == "lowers"
        and f.detail
        and (w := weights.get(f.name, {}).get("lowers", 0.0)) < 0
        and not (counted and f.name == "advisor" and f.detail.startswith("the advisor was"))
    ]
    do = getattr(answer, "do", None) or []
    # scored as confidence.assess scores it: feed is "other", isolate is treat_or_remove
    base = table["base"].get(coarse(do[0].action), table["base"]["default"]) if do else 0.0
    weakest = min((x[0] for x in lows), default=0.0)
    if base < 0 and base < weakest:
        return BASE_DOUBT
    if not lows:
        return None
    f = min(lows, key=lambda x: (x[0], x[1]))[2]
    return _plain_doubt(f.name, f.detail)


def reply_to(answer: Answer, question: str | None, month: int) -> str:
    """The advisor's answer to the person's own question: its sentences other than its
    reason (told_note asks for the reply after it), from the first ask that gave one. Each
    goes through the reason's own checks (the season's turn, no placeholder or bare
    question) and is never a reason already on the page or an echo of their words. When no
    ask answered it, a pointer to the headline; empty only when there is no headline."""
    said = _plain(question or "")
    if not said:
        return ""
    shown = {_plain(c.because) for c in answer.do}
    rest = answer.winter_rest or answer.no_cut_growth  # seedlings too: never "pinch out" here
    for run in answer.runs:
        reason = _plain(_reason(run.answer, question, month, quiet=True, rest=rest))
        parts = []
        for part in _sentences(run.answer):
            sentence = _said_now(part, month, rest) if part else None
            if not sentence or why_not_a_reason(sentence) is not None:
                continue
            if answer.in_ground and _APART.search(sentence):  # a bed plant stays put (#304)
                continue
            plain = _plain(sentence)
            if plain != reason and plain not in shown and plain not in said:
                parts.append(sentence)
        if parts:
            return " ".join(parts[:2])
    # no ask answered it: point at the answer rather than leave the question hanging (judge
    # walk of #269, finding 6: "You asked" with nothing under it)
    head = answer.headline.strip()
    if not head or not is_question(question or ""):  # a statement needs no pointer
        return ""
    return f"Our answer: {head}{'' if head[-1] in '.!?' else '.'} See the top."


def _has_placeholder(answer: str) -> bool:
    if not re.search(r"[A-Za-z]", answer):  # empty, or punctuation only
        return True
    return any(not usable_reason(x) for x in _sentences(answer) if x)


def _said_now(sentence: str, month: int, rest: bool) -> str | None:
    """The sentence as it holds this month: no clause turning the season the wrong way, and
    for a resting herb no cut for growth; None when nothing sensible is left."""
    now = _in_season(sentence, month)
    return _no_cut_for_growth(now) if now and rest else now


def _reason(
    answer: str,
    told_question: str | None,
    month: int,
    quiet: bool = False,
    rest: bool = False,
) -> str:
    """The advisor's first sentence, unless it only repeats what the person told us (it
    did, live) or names the wrong season: then the next one, or none. Their words are never
    shown as our reason."""
    said = _plain(told_question or "")
    for part in _sentences(answer):
        sentence = _said_now(part, month, rest)
        if not sentence:
            continue
        if (why := why_not_a_reason(sentence)) is not None:
            # the kind and length only: the advisor's text can echo the person's own note
            if not quiet:  # reply_to looks again on every page view: log once, at the answer
                log.warning("advisor reason dropped: %s, %d chars", why, len(sentence))
            continue
        plain = _plain(sentence)
        # an echo is most of their note, not a short phrase that happens to be inside it
        if not (said and plain in said and 2 * len(plain) >= len(said)):
            return sentence
    return ""


# what each advisor said, under "Who advised" (21 Oct, Kash on rev 00049: "what does each
# mean?"): one model asked three times, so each ask's own call, as the page names it. The
# call only, never their words: their raw text would need every filter the page's reasons
# have, and an Opus review of a quoted version still found chemicals, hard cuts and other
# calls' commands getting through (integrator, for FINAL). Never a new role: #351
RULES_CHOSE = "Our rules then chose the plan at the top, so follow that."
MOST_SAID = "The plan at the top goes with what most of them said."
ALL_DIFFERED = "Each said something different, so we're less sure of the plan at the top."
_TOGETHER = {2: "Both", 3: "All three", 4: "All four"}
TIDY_LABEL = "Give it a light tidy"  # a resting herb's cut, as the template swaps it
THIN_LABEL = "Thin them out"  # seedlings are thinned, never cut back (the page drops the cut)
REMOVE_LABEL = "Remove it"  # under no cure, as the headline says


class AdvisorLine(NamedTuple):
    who: str  # "Advisor 1", or "All three" when every one chose the same
    action: str  # the page's own label for the call


class AdvisorsSaid(NamedTuple):
    lines: list[AdvisorLine]
    note: str  # whose plan the page is: ours by rule, the most said, or a split; may be ""


def advisor_lines(rec: AnalysisRecord, label: Mapping[str, str]) -> AdvisorsSaid:
    """Each stored ask's call, in the page's words (`label` is its card labels), with the
    page's own swaps: a light tidy for a resting herb, thinning for seedlings, "Remove it"
    under no cure, and treating for a bed plant that cannot go apart (in_proportion). The
    note counts the calls as shown, never their coarse classes (feed, rotate and water are
    all "other"). A failed ask is missing from `runs`: the lines are numbered as they came
    back and the note says how many failed."""
    a = rec.answer
    if a is None or not a.runs:
        return AdvisorsSaid([], "")
    no_cure = a.headline == NO_CURE_HEADLINE

    def call(primary: str) -> str:
        if primary == "prune" and a.winter_rest:
            return TIDY_LABEL
        if primary == "prune" and a.no_cut_growth:
            return THIN_LABEL
        if primary == "isolate" and a.in_ground:
            primary = "treat_or_remove"
        if primary == "treat_or_remove" and no_cure:
            return REMOVE_LABEL
        return label.get(primary, label.get("other", ""))

    calls = [call(r.primary) for r in a.runs]
    n = len(calls)
    same = n > 1 and len(set(calls)) == 1
    if same:
        lines = [AdvisorLine(_TOGETHER.get(n, f"All {n}"), calls[0])]
    else:
        lines = [AdvisorLine(f"Advisor {i}", c) for i, c in enumerate(calls, 1)]
    rule_led = no_cure or any(f.name == "advisor" and f.detail == RULE_LED for f in a.factors)
    top = max(Counter(calls).values())
    note = (
        RULES_CHOSE
        if rule_led
        else ""
        if same or n == 1
        else MOST_SAID
        if top >= 2
        else ALL_DIFFERED
    )
    asked = len(PANEL_TEMPERATURES)
    if n < asked:
        failed = asked - n
        lost = f"{COUNTS.get(failed, str(failed)).capitalize()} ask{'s' if failed > 1 else ''}"
        note = " ".join(
            x for x in (f"{lost} failed, so {COUNTS.get(n, str(n))} answered.", note) if x
        )
    return AdvisorsSaid(lines, note)


# a comma that starts an add-on, not another sign: "..., outdoors as well as under cover",
# "..., later turning brown", "..., not the neat rows", "..., worse when roots are dry"
_ADD_ON = re.compile(
    r",\s+(?:outdoors|indoors|later|on|not|worse|often|usually|especially|even|as)\b"
)


def short_sign(sign: str) -> str:
    """A season sign as a bullet: the sign itself, without its add-ons. It stops at a
    semicolon or at a comma that starts an add-on ("grey-purple fuzz on the leaf underside,
    outdoors as well as under cover" stops at "underside"), and never at a comma between
    signs or adjectives ("loose in the compost, C-shaped white grubs", "a young, still-leafy
    plant"). Bracketed notes go too. 19 Oct small print: the first basil bullet ran to about
    30 words."""
    sign = sign.split(" (")[0].split(";")[0].strip()
    m = _ADD_ON.search(sign)
    return sign[: m.start()].strip() if m else sign


def _main_reason(
    panel: Panel,
    views: dict[CareAction, ModelView],
    told_question: str | None,
    month: int,
    rest: bool = False,
    tidy: bool = False,
) -> str:
    """The main card's reason: the chosen advisor's, else another ask's that chose the same,
    else what the twin found, else our own line for the action; never a placeholder. `rest`
    trims cuts for growth (a resting herb, or seedlings); `tidy` is the resting herb alone,
    whose cut-back card becomes a light tidy (never seedlings: review of the pinch fix)."""
    runs = [panel.chosen] + [
        r for r in panel.runs if r is not panel.chosen and r.advice.primary == panel.primary
    ]
    first = _reason(panel.chosen.advice.answer, told_question, month, rest=rest)
    # the rest rule took its only line (a cut for growth): look further, as for a placeholder
    cut = rest and not first and bool(_reason(panel.chosen.advice.answer, told_question, month))
    if first or not (_has_placeholder(panel.chosen.advice.answer) or cut):
        return first  # a reason, or none on purpose (it only echoed the person's note)
    for run in runs[1:]:
        if said := _reason(run.advice.answer, told_question, month, rest=rest):
            return said
    view = views.get(panel.primary)
    if view is not None and view.why:
        return f"tested on your plant's twin: {view.why.rstrip('.')}."
    if tidy and panel.primary == "prune":
        return TIDY_BECAUSE
    return ALSO_BECAUSE.get(panel.primary, "")


LEAVE_BUT_PROTECT = "Leave it, but protect it before the cold night on {day}."
# the photo read saw a plant that has outgrown its pot (Observation.pot_fit, 21 Oct): say what
# was seen, not only that the roots "may" need room
CROWDED_BECAUSE = "the roots look crowded for the pot."
# "darkening", not "blackened": the cold night can be a chill as well as a frost
FROST_SIGN = "Limp or darkening shoot tips after the cold night on {day}."


# where to look for more of a problem that does not spread leaf to leaf; the rest spread
_PROBLEM_WATCH = {
    "root rot": "more wilting, or soft dark stems at the base",
    "verticillium wilt": "more shoots wilting, often one side first",
    "fungus gnats": "more small flies over the compost",
    "leaf scorch": "more brown, crisp leaf edges",
    "carrot fly": "more reddish leaves on stunted plants",
    "vine weevil": "wilting with loose compost at the roots",
    "slugs and snails": "fresh holes and slime trails",
    "coral spot": "more pink spots on dead stems",
    "cuckoo spit": "more froth on the stems",
}


def _watch_problem(name: str, no_cure: bool) -> str:
    """The named problem as the first thing to watch: where more of it would show."""
    look = _PROBLEM_WATCH.get(name.lower())
    if look:
        return f"{name}: {look}"
    return (
        f"{name} on {'the plants beside it' if no_cure else 'new leaves or the plants beside it'}"
    )


def _leave_but_protect(primary: CareAction, views: dict[CareAction, ModelView]) -> str | None:
    """The advisors said leave it, but the twin marks a cold night that shelter avoids: say
    both in one headline, not "Leave it" above "cold risk Saturday if left out" (19 Oct
    site walk, peas; Kash chose this over the twin overruling all 3 advisors). A split
    panel with a shelter ask has already been led by shelter (pipeline.follow_the_twin), so
    the two rules never stack."""
    view = views.get("shelter")
    if primary != "leave_normal" or not shelters_from_cold(view) or view is None:
        return None
    return LEAVE_BUT_PROTECT.format(day=view.cold_on) if view.cold_on else None


# the indoor table's jobs for a plant that is doing well: not beside a hold, a treatment
# or a check
TENDING = ("feed", "repot")
_THRIVING = ("leave_normal", "water", "move_light", "prune", "rotate", "humidity", "feed", "repot")


def _thriving(primary: CareAction, actions: list[CareAction], problem: ProblemSeen | None) -> bool:
    return primary in _THRIVING and "dont_water" not in actions and problem is None


def _headline(primary: CareAction, norm: SeasonalNorm | None, month: int, answer: str) -> str:
    if primary == "leave_normal":
        if norm is not None and RESTING & set(norm.status):
            return f"Leave it. This is normal for {calendar.month_name[month]}."
        return "Leave it for now and keep an eye on it."
    return HEADLINES.get(primary, _first_sentence(answer))


def _level_text(assessment: Assessment) -> str:
    """The middle level's "Not sure" names the check it means: the question the page asks, or none
    (18 Oct judge walk: "do the quick check first" named no check)."""
    if assessment.level != "fairly_sure":
        return LEVEL_TEXT[assessment.level]
    word = LEVEL_TEXT["fairly_sure"].split(":")[0]
    if assessment.tell_me is None:
        return f"{word}: look closely before you act, then watch how it responds"
    if assessment.tell_me_key == "soil_feel":
        return f"{word}: feel the soil 2 cm down first, and tell us below"
    return f"{word}: answer the question below first"


def _quoted(c: ActionCard, problem: ProblemSeen) -> ActionCard:
    """A problem card with no row of ours: the trusted page's own sentence on dealing with
    it, shown as a quote with its site, in place of "no reliable data"."""
    how = problem.how
    if how is None or c.if_you_do_from != "none":
        return c
    return c.model_copy(
        update={
            "if_you_do": how.quote,
            "if_you_do_from": "web_search",
            "if_you_do_url": how.url,
            "found_with": how.found_with,
            "less_sure": True,  # one page's words, not a row we checked
        }
    )


def build_answer(
    *,
    panel: Panel,
    assessment: Assessment,
    norm: SeasonalNorm | None,
    plant_key: str | None,
    month: int,
    views: dict[CareAction, ModelView],
    told_question: str | None = None,
    problem: ProblemSeen | None = None,
    setting: str = "unknown",
    seedlings: bool = False,
    bolted: bool = False,
    soil_known: bool = True,
    tender: bool = False,
    container: str = "unknown",
    damage: bool = True,
    indoor_care: IndoorCare | None = None,
    roots_crowded: bool = False,
) -> Answer:
    adv = panel.chosen.advice
    # the season norms are the UK outdoor year: indoors, none of their outdoor lines apply
    # ("outdoor plant finished", "before any cold night", "normal for October" on a
    # windowsill basil; 19 Oct site walk)
    indoors = setting == "indoor"
    resting = winter_rest(plant_key, month)

    def card(
        action: CareAction, when, because: str, do: bool = True, answer: str | None = None
    ) -> ActionCard:
        c = consequence_for(
            action,
            plant_key=plant_key,
            month=month,
            answer=adv.answer if answer is None else answer,
            views=views,
        )
        text, source, less_sure = c.text, c.source, c.less_sure
        if action == "prune" and resting and re.search(rf"\b{_GROWTH}\b", text, re.I):
            # a sourced line for the growing season ("keeps mint bushy"): not while it rests
            text, source, less_sure = NO_DATA, "none", False
        v = views.get(action)
        if do and v is not None and v.vs_leaving_it == "worse":
            # the advisor overruled the plant model (confidence already drops for it): say
            # so, rather than a line that argues against the card's own action
            text = f"worse than leaving it ({v.why}); check first"
        return ActionCard(
            action=action,
            when=when,
            because=because,
            if_you_do=text,
            if_you_do_from=source,
            less_sure=less_sure,
        )

    # a rule of ours led, not an advisor (pipeline.tender_first, in_proportion): the
    # advisor's words were for its own call, so the reason is ours
    led = coarse(adv.primary) != coarse(panel.primary)
    tender_lead = tender and panel.primary == "shelter" and month in TENDER_MONTHS and not indoors
    # an isolate call that in_proportion turned into a look, led by it or by an ask that chose
    # the look (Opus review: one check_pests ask kept the plain headline)
    looked = (
        panel.primary == "check_pests"
        and not damage
        and any(r.advice.primary == "isolate" for r in panel.runs)
    )
    # a seasonal job out of season led, and no ask chose what leads now (pipeline.in_season)
    waited = None
    # the exact action, not coarse(): feed, rotate and humidity all coarse to "other", and a
    # rotate lead kept the advisors' feeding line (review)
    if adv.primary != panel.primary and panel.agree == 0 and adv.primary in WAITING_JOB:
        c = consequence_for(adv.primary, plant_key=plant_key, month=month, answer="", views={})
        waited = c if c.off_season else None
    # seedlings are never cut or pinched for growth (judge walk of rev 00043: a pot of
    # seed-leaf basil told to "pinch out the stem tips"): the same trim as a resting herb's
    no_cut = resting or seedlings
    if tender_lead and (led or container != "ground"):
        # our headline needs our reason, whoever chose shelter: "Bring it indoors to a bright
        # windowsill." over the advisors' "bring it indoors overnight" or "a sunny balcony"
        # argued with itself (judge walk of rev 00043)
        reason = TENDER_BED_BECAUSE if container == "ground" else TENDER_BECAUSE
    elif led and looked:
        reason = PROPORTION_BED_BECAUSE if container == "ground" else PROPORTION_BECAUSE
    elif adv.primary == "isolate" and panel.primary == "treat_or_remove":
        # every advisor said keep it apart, and a bed plant cannot be: in_proportion led with
        # treating it, so the reason is ours (coarse() calls the two the same: Opus review)
        reason = BED_TREAT_BECAUSE
    elif waited is not None:
        reason = WAIT_BECAUSE.format(
            job=WAITING_JOB[adv.primary],
            when=f": {waited.text}" if waited.text.startswith("best done in") else "",
            # never "nothing else needs doing": a problem or cold-night card can follow
            then="so leave it be for now"
            if panel.primary == "leave_normal"
            else "so this comes first",
        )
    else:
        reason = _main_reason(panel, views, told_question, month, no_cut, tidy=resting)
    if roots_crowded and reason == ALSO_BECAUSE["repot"]:  # only the stock line: say what was seen
        reason = CROWDED_BECAUSE
    if container == "ground" and _APART.search(reason or ""):
        # a treat ask's own "and keep it away from your other plants" (#304 review)
        kept = " ".join(s for s in _sentences(reason) if s and not _APART.search(s))
        reason = kept or (
            BED_TREAT_BECAUSE
            if panel.primary == "treat_or_remove"
            else ALSO_BECAUSE.get(panel.primary, "")
        )
    said = {
        _reason(r.advice.answer, told_question, month, quiet=True, rest=no_cut) for r in panel.runs
    }
    if assessment.photo_issue and reason and reason in said:
        # a rough read: "the plant looks healthy" from a blurred photo is a guess, said as
        # one. Only the advisor's own line: the twin's and ours already say where they're from
        reason = f"From what this photo shows, {_lead_lower(reason)}"
    do = [card(panel.primary, "today", reason)]
    if reason in (TENDER_BECAUSE, TENDER_BED_BECAUSE) and not shelters_from_cold(
        views.get("shelter")
    ):
        # brought in for its state, not a forecast night: no twin line saying "no cold nights"
        # under "cold nights harm it", whoever chose shelter (review of the reason fix)
        do[0] = do[0].model_copy(
            update={"if_you_do": NO_DATA, "if_you_do_from": "none", "less_sure": False}
        )
    for action in adv.actions:
        if action in (panel.primary, "ask_first") or len(do) == 3:
            continue
        if action == "prune" and seedlings:  # seedlings are thinned, never cut back
            continue
        if action == "isolate" and not damage:  # one insect, no harm: out of proportion
            continue
        if action == "isolate" and container == "ground":  # a bed plant cannot be moved apart
            continue
        # a seasonal job outside the plant's own months: "THIS WEEK · Feed it" over "best
        # done in Jun, Jul, Aug or Sep" told an October basil to feed now (19 Oct)
        if consequence_for(
            action, plant_key=plant_key, month=month, answer=adv.answer, views=views
        ).off_season:
            continue
        because = ALSO_BECAUSE.get(action, "the advisor suggested this too.")
        if action == "repot" and roots_crowded:
            because = CROWDED_BECAUSE
        if action == "prune" and resting:
            because = TIDY_BECAUSE
        if norm is not None and action in SEASONAL_JOBS and not indoors:
            because = f"{because} What comes next: {norm.next_change.rstrip('.')}."
        do.append(card(action, "this_week", because))
    if problem is not None:
        # the photo check named a listed problem: make sure there is a card to treat it,
        # with that problem's own outcome row rather than whatever the advisor wrote
        seen = f"the photo {'looks like' if problem.sure else 'could show'} {problem.name}."
        at = next((i for i, c in enumerate(do) if c.action == "treat_or_remove"), None)
        if at is not None:  # keep its place and time; reason and outlook from the problem
            do[at] = _quoted(
                card("treat_or_remove", do[at].when, seen, answer=problem.name), problem
            )
        else:
            new = _quoted(card("treat_or_remove", "this_week", seen, answer=problem.name), problem)
            if len(do) == 3:
                do[-1] = new
            else:
                do.append(new)
    care = indoor_care if indoors else None
    if (
        care is not None
        and care.also_do is not None
        and care.because is not None
        and care.if_you_do is not None
        and len(do) < 3
        and care.also_do not in {c.action for c in do}
        and not (care.also_do in TENDING and not _thriving(panel.primary, adv.actions, problem))
        # #301's filter, as for the advisor's own cards: an April basil was told "Feed it"
        # beside "best done in Jun, Jul, Aug or Sep" (#340 review)
        and not consequence_for(
            care.also_do, plant_key=plant_key, month=month, answer=adv.answer, views=views
        ).off_season
    ):
        # the month's one indoor job, from our indoor table: what to expect is the sources'
        # general line, not a test on this plant (21 Oct, a gardener: indoor "doesn't have
        # much info"). Never a second card for the same job, and never a feed or a repot
        # under a plant being held dry, treated or checked (#review: "Hold off watering"
        # then "Feed it")
        do.append(
            ActionCard(
                action=care.also_do,
                when="this_week",
                because=care.because,
                if_you_do=care.if_you_do,
                if_you_do_from="norm_rule",
                less_sure=True,
            )
        )
    # a choice the plant model rates better than leaving it is in the advice, at least as a
    # THIS WEEK card (18 Oct judge walk: "Treat it." beside "Protect it: better, cold risk
    # Sunday"). It never pushes out the main action or the photo check's problem
    # Watering beside "Leave it" or "Hold off watering" would argue with the main card: the
    # advisor's call stands there, and confidence already drops for it. When both slots after
    # the main card are taken (the problem and another forecast card), a further one is left
    # to Compare all choices
    kept = {panel.primary} | ({"treat_or_remove"} if problem is not None else set())
    hold = panel.primary in ("leave_normal", "dont_water") or "dont_water" in adv.actions
    for action, v in views.items():
        have = {c.action for c in do}
        if (
            not worth_doing(v)  # a small edge with no risky day ahead stays in Compare
            or action in have
            or action in ("leave_normal", "dont_water")
        ):
            continue
        if action == "water" and hold:
            continue
        new = card(action, "this_week", FORECAST_BECAUSE)  # its twin line says why
        kept.add(action)
        if len(do) < 3:
            do.append(new)
        elif at := next((i for i in range(2, 0, -1) if do[i].action not in kept), None):
            do[at] = new
    # only when "Treat it." is the main card: a photo check under another main action is
    # hedged on the page ("the photo alone can be wrong") and leaves the advisor's call standing
    main = do[0]
    no_cure = (
        main.action == "treat_or_remove"
        and main.if_you_do_from == "outcome_table"
        and NO_CURE.search(main.if_you_do) is not None
    )
    if no_cure:
        # the photo check's own reason names the problem: kept, with why it must go
        seen = problem is not None and main.because.startswith("the photo ")
        main.because = (
            NO_CURE_SEEN.format(seen=main.because.rstrip(".")) if seen else NO_CURE_BECAUSE
        )
        # "no known cure" is the sources' plain finding, and the headline rests on it: a
        # "(less sure)" beside it, under "Likely right", argued with the page (19 Oct)
        main.less_sure = False
        do = [main] + [c for c in do[1:] if c.action in SPARES_THE_OTHERS]
    dont = None
    for action in TEMPTING:
        v = views.get(action)
        if v is not None and v.vs_leaving_it == "worse" and action not in {c.action for c in do}:
            unsure = action == "water" and not soil_known
            dont = card(action, "today", DONT_IF_DRY_BECAUSE if unsure else DONT_BECAUSE, do=False)
            break
    listed = list(norm.problem_signs) if norm is not None else []
    if indoors:
        listed = [x for x in listed if _indoor_sign(short_sign(x))]
    elif setting == "outdoor":
        # a sign about a plant brought in does not happen outside (judge walk of #272: an
        # outdoor mildew basil was told to watch for mould "on a plant brought indoors")
        listed = [x for x in listed if not _INDOOR_ONLY.search(short_sign(x))]
    if bolted:  # the seasons' signs are for young plants; it has gone over to seed
        listed = list(BOLTED_SIGNS)
    named = problem.name.strip() if problem is not None else ""
    if named:
        # the photo named a problem: watch for that one first (judge walk of c485f29: a
        # rosemary beetle was told to watch for root rot), never its own signs again (17 Oct
        # walk, sample 6); then one other worth knowing: a cold night, else the month's next
        core = " ".join(named.lower().split()[-2:])
        rest = [s for s in listed if core not in s.lower()]
        cold = views.get("shelter")
        frost = cold is not None and shelters_from_cold(cold) and cold.cold_on
        second = (
            FROST_SIGN.format(day=cold.cold_on).rstrip(".")
            if frost
            else short_sign(rest[0]).rstrip(".")
            if rest
            else ""
        )
        bullets = [_watch_problem(named, no_cure)] + ([second] if second else [])
        said = " ".join(f"• {x[:1].upper()}{x[1:]}" for x in bullets)
        watch = f"{said}. {'Seen either?' if second else 'Seen it?'} Send a new photo."
    elif listed:
        # one clause per sign: the signs carry their own "or"s and semicolons
        # as bullets under "Keep an eye on" (19 Oct small print: about 55 words in a block)
        signs = [short_sign(s) for s in listed[:2]]
        bullets = " ".join(f"• {x[:1].upper()}{x[1:].rstrip('.')}" for x in signs)
        seen = "Seen either?" if len(signs) == 2 else "Seen it?"
        watch = f"{bullets}. {seen} Send a new photo."
    elif (cold := views.get("shelter")) is not None and shelters_from_cold(cold) and cold.cold_on:
        # no season signs for this plant, but the twin marks a cold night: frost damage is the
        # one sign worth watching (19 Oct judge walk, the pea bed had only the line below)
        watch = f"• {FROST_SIGN.format(day=cold.cold_on)} Seen it? Send a new photo."
    else:
        watch = "Send a new photo if it changes."
    if container == "ground":  # a bed has soil, not compost (judge walk: border rosemary)
        watch = re.sub(r"\b([Cc])ompost\b", lambda m: "Soil" if m[1] == "C" else "soil", watch)
    compare = [
        CompareRow(
            action=a,
            vs_leaving_it="same" if a == "leave_normal" else v.vs_leaving_it,
            # the vs column already says "baseline" (judge live walk of rev 00040)
            why=v.why,
        )
        for a, v in views.items()
        if a != "dont_water"
    ]
    if no_cure:  # "if you protect it" under "remove it" argues with the headline (#230 review)
        compare = []
    ours = (
        TENDER_HEADLINE
        if tender_lead and container != "ground"  # a bed of basil cannot come in
        else PROPORTION_HEADLINE
        if looked
        else TIDY_HEADLINE
        if resting and panel.primary == "prune"
        else None
    )
    return Answer(
        headline=NO_CURE_HEADLINE
        if no_cure
        else ours
        or _leave_but_protect(panel.primary, views)
        # a rough read can't say "normal for October": the plain leave-it line (judge walk)
        or _headline(
            panel.primary,
            None if indoors or assessment.photo_issue else norm,
            month,
            adv.answer,
        ),
        do=do,
        dont=dont,
        watch=watch,
        # whoever led (our rule or the advisors themselves): the same headline, the same check
        tray_check=not no_cure and ours == TENDER_HEADLINE,
        in_ground=container == "ground",
        tell_me=assessment.tell_me,
        tell_me_key=assessment.tell_me_key,
        photo_issue=assessment.photo_issue,
        level=assessment.level,
        level_text=_level_text(assessment),
        in_ten=assessment.in_ten,
        factors=assessment.factors,
        chips=assessment.chips,
        compare=compare,
        runs=[r.advice for r in panel.runs],
        assumptions=[],
        dont_if_dry=dont is not None and dont.because == DONT_IF_DRY_BECAUSE,
        winter_rest=resting,
        no_cut_growth=no_cut,
        indoor=IndoorNow(month=month, normal=care.normal, tips=care.tips, sources=care.sources)
        if care is not None
        else None,
    )


def weather_explains(obs: Observation, weather: WeatherFacts | None, plant_key: str | None) -> bool:
    """Wilting after 10+ dry warm days; basil blackened after a night below about 10 C."""
    if weather is None:
        return False
    if obs.water_stress >= 2 and weather.dry_days_14 >= 10 and weather.mean_tmax_14 >= 20:
        return True
    blackened = any("black" in s.casefold() for s in obs.symptoms) or obs.decline >= 2
    cold = weather.min_t_7 is not None and weather.min_t_7 < 10
    return plant_key == "ocimum basilicum" and blackened and cold
