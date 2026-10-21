"""Does the chat's web search help? 30 factual herb questions through the real follow-up
chat, with Tavily search on and with search off (19 Oct 2026).

PRE-REGISTERED: the metrics, the rubric and the decision rule below were fixed in this
header, and committed, before any paid call.

Questions: 30 that a gardener types under an answer (8 herbs: basil, parsley, coriander,
rosemary, thyme, mint, sage, chives). Each has one key fact already in the repo's sourced
data (data/outcomes/outcomes_uk.json, data/outcomes/problem_signs_uk.json,
data/seasonal/norms_uk.json, data/crop_calendar/calendar.json), named in `source`, and a
fixed keyword rubric for it: `must` (every pattern found) and `wrong` (none found).

Arms: `chat.reply`, the live path, with the chat's configured model (HERBTWIN_FAST_MODEL,
else the advise model) at temperature 0. The same minimal answer record per herb in both
arms: the photo read as that herb, healthy, outdoors in a pot; a neutral answer ("Leave
it for now."); a mild synthetic October fortnight with no frost; no history, no chat
before. Only `search` differs: "on" is Tavily alone (no Exa or TinyFish behind it), on the
app's trusted sites with its plant filter; "off" is no search tool and the app's
search-off prompt line. run_scenario stays offered in both, as live. One reply per
question and arm (60 replies).

Scoring, on the reply less the app's own "Less sure: ..." line (added when nothing
grounds a reply; counted apart as M5):
- M1 correct: every `must` pattern and no `wrong` pattern matches the reply, citations
  removed. Deterministic, no model judge.
- M2 cites: the reply names at least one source (a URL, or a bracketed web address).
- M3 on_plant: of replies that cite, every cited source is one of the search hits the
  chat was given this turn AND that hit's title, address or snippet names the herb.
  A source not among the hits (from memory, invented) is not on-plant.
- M4 unsure: the reply says it is not sure (chat.UNSURE) or declines (the app's
  could-not-answer or not-available text).
- M5 less_sure: the app added its "Less sure" line (no grounding behind the reply).
Each arm's rate with a 95% bootstrap interval over questions (2000 draws, seed 0), and
the paired difference on minus off, resampling questions.

M1 is the decision metric. Decision rule: "search makes the chat more correct" is claimed
only if M1's paired 95% interval lies above 0; "less correct" only if it lies below 0;
otherwise no measurable change. Whatever the result, it is reported.
Budget: stop before the recorded model spend passes the run's budget ($3 aimed, $5 cap).

POST-HOC (added 19 Oct, after the run; not pre-registered): `correct_v2`, a rubric v2
(see RUBRIC_V2 below), is reported beside M1 and clearly labelled. It never replaces M1
or the decision above.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from herbtwin.chat import LESS_SURE, NO_ANSWER, UNAVAILABLE, UNSURE
from herbtwin.evals import metrics as m
from herbtwin.schemas import (
    AnalysisRecord,
    Answer,
    DailyWeather,
    Environment,
    Observation,
    SpeciesCandidate,
)
from herbtwin.stages.research import normalise_species, seed_pack

ARMS = ("off", "on")
METRICS = ("correct", "cites", "on_plant", "unsure", "less_sure")
POST_HOC = ("correct_v2",)  # rubric v2, written after the run: never the decision
ON = date(2026, 10, 19)


@dataclass(frozen=True)
class Herb:
    latin: str
    common: str
    names: tuple[str, ...]  # how a source names it: common, Latin, genus


HERBS = {
    "basil": Herb("Ocimum basilicum", "basil", ("basil", "ocimum")),
    "parsley": Herb("Petroselinum crispum", "parsley", ("parsley", "petroselinum")),
    "coriander": Herb("Coriandrum sativum", "coriander", ("coriander", "cilantro", "coriandrum")),
    "rosemary": Herb("Salvia rosmarinus", "rosemary", ("rosemary", "rosmarinus")),
    "thyme": Herb("Thymus vulgaris", "thyme", ("thyme", "thymus")),
    "mint": Herb("Mentha spicata", "mint", ("mint", "mentha")),
    "sage": Herb("Salvia officinalis", "sage", ("sage", "salvia officinalis")),
    "chives": Herb("Allium schoenoprasum", "chives", ("chive", "allium schoenoprasum")),
}


@dataclass(frozen=True)
class Question:
    id: str
    herb: str  # a HERBS key
    text: str
    fact: str  # the key fact, in plain words
    source: str  # where in the repo the fact is
    must: tuple[str, ...]  # every pattern must match (case-insensitive)
    wrong: tuple[str, ...] = ()  # none may match


# shared patterns
_CUT_BACK = (
    r"5\s*cm|five centimet|2\s*in(?:ch)?|two inches|ground level|"
    r"(?:to|near|at|above|down to) (?:the )?(?:base|ground)|"
    r"cut (?:it |them |the (?:whole |entire )?(?:plant|clump) |the stems |everything )?"
    r"(?:right |hard |all the way )?(?:back|down)"
)
_HARDY = (
    r"\bhardy\b|survives? (?:most |a |the )?(?:uk |british )?winters?|overwinter|"
    r"(?:cope|copes|tolerate|tolerates|handle|handles|withstand|withstands) (?:with )?"
    r"(?:\w+ )?(?:frost|cold|winter)"
)
_NOT_HARDY = r"\bnot (?:\w+ )?hardy\b|\b(?:frost[- ])?tender\b|isn.?t (?:\w+ )?hardy"
CAL = "data/crop_calendar/calendar.json"
OUT = "data/outcomes/outcomes_uk.json"
SIGNS = "data/outcomes/problem_signs_uk.json"
NORMS = "data/seasonal/norms_uk.json"

QUESTIONS: tuple[Question, ...] = (
    Question(
        "basil_hardy", "basil",
        "Is basil hardy enough to stay outside over a UK winter?",
        "No: basil is frost tender and does not overwinter outdoors",
        f"{CAL} basil: frost_tender true, overwinters_outdoors n",
        (r"\btender\b|\bnot (?:\w+ )?hardy\b|isn.?t (?:\w+ )?hardy|"
         r"(?:won.?t|will not|can.?t|cannot|doesn.?t|does not|unlikely to|not) (?:\w+ )?survive|"
         r"(?:frost|cold) (?:will |would )?kills?|killed by (?:frost|cold)",),
    ),
    Question(
        "basil_plant_out", "basil",
        "When can I plant basil outside?",
        "June, once nights stay above 10 C",
        f"{CAL} basil: plant_out [6, 7]; {NORMS} basil Jan next_change",
        (r"\bjune\b|early summer",),
    ),
    Question(
        "basil_eat_flowering", "basil",
        "Can I still eat the basil leaves once it starts flowering?",
        "Yes; leaves on flowering shoots are smaller and stronger tasting, and pinching "
        "out flower stems keeps leaf quality",
        f"{NORMS} basil Jul normal_signs; {OUT} basil prune",
        (r"\byes\b|\bedible\b|safe to eat|can (?:still )?(?:eat|use|pick|harvest)|"
         r"still (?:eat|use|good|fine)",),
    ),
    Question(
        "basil_downy_mildew", "basil",
        "What disease gives basil yellow patches on top of the leaves and grey-purple fuzz "
        "underneath?",
        "Basil downy mildew",
        f"{SIGNS} basil downy mildew",
        (r"downy mildew",),
    ),
    Question(
        "basil_dm_cure", "basil",
        "Is there a cure for basil downy mildew?",
        "No known cure: use the healthy leaves, then pull out, bag and bin infected plants",
        f"{OUT} basil treat_or_remove basil downy mildew",
        (r"\bno (?:known |real |effective )?(?:cure|treatment|fix)|"
         r"(?:can.?t|cannot) be (?:cured|treated)|incurable|not curable|isn.?t curable|"
         r"\bno\b[^.]*\bcure|pull (?:it |them |the plants? )?(?:up|out)|\bbin\b|"
         r"remove (?:and destroy |the (?:whole|infected|affected) plants?)|dispose",),
    ),
    Question(
        "basil_pot", "basil",
        "How big a pot does basil need?",
        "At least 20 cm wide and deep",
        f"{CAL} basil container note",
        (r"\b20\s*(?:cm|centimet)|\b8\s*(?:in|inch)",),
    ),
    Question(
        "parsley_life", "parsley",
        "Will my parsley come back next year, or is it an annual?",
        "Biennial: it overwinters, flowers in its second year, then dies",
        f"{CAL} parsley life_cycle biennial; {NORMS} parsley Jan next_change",
        (r"biennial|second year|two years|(?:next|following) (?:year|summer|spring)[^.]*"
         r"(?:flower|seed|bolt)",),
    ),
    Question(
        "parsley_sow_out", "parsley",
        "When can I sow parsley seed outdoors?",
        "April to August",
        f"{CAL} parsley sow_outdoors [4, 5, 6, 7, 8]",
        (r"\bapril\b|mid[- ]spring", r"august|late summer|mid[- ]?summer|into (?:the )?summer"),
    ),
    Question(
        "parsley_carrot_fly", "parsley",
        "What pest tunnels into parsley roots and leaves creamy maggots there?",
        "Carrot fly",
        f"{NORMS} parsley Jul problem_signs; {OUT} parsley carrot fly",
        (r"carrot (?:root )?fly",),
    ),
    Question(
        "parsley_leaf_miner", "parsley",
        "What makes pale blotches on parsley leaves that dry brown and papery?",
        "Celery leaf miner (celery leaf mining fly)",
        f"{SIGNS} celery leaf mining fly; {NORMS} parsley Jul problem_signs",
        (r"leaf[- ]?min(?:er|ing)",),
    ),
    Question(
        "coriander_bolt", "coriander",
        "Why has my young coriander gone to flower so quickly?",
        "It bolted: dry compost or hot full sun makes young plants flower early",
        f"{NORMS} coriander Jul problem_signs; {CAL} coriander soil note",
        (r"\bbolt", r"\bdry|drought|heat|\bhot\b|\bsun|warm|stress|water"),
    ),
    Question(
        "coriander_after_flower", "coriander",
        "Will coriander keep making new leaves after it flowers?",
        "No: leaf production stops once flowering starts, and the plant dies after seeding",
        f"{NORMS} coriander Jul normal_signs and next_change",
        (r"\bstops?\b|\bno (?:more|new)\b|\bfewer\b|\bdies?\b|\bdying\b|declin|finish|"
         r"(?:won.?t|will not|doesn.?t|does not)\b",),
    ),
    Question(
        "coriander_pick_height", "coriander",
        "How tall should coriander be before I start picking the leaves?",
        "10 to 15 cm",
        f"{OUT} coriander prune",
        (r"\b1[05]\s*(?:cm|centimet)|\b1[05]\s*(?:-|–|to)\s*1[05]\s*cm|\b[46]\s*(?:in|inch)",),
    ),
    Question(
        "rosemary_hardy", "rosemary",
        "Is rosemary hardy outside in the UK?",
        "Yes, hardy through most of the UK (RHS H4); it is wet roots in winter that harm it",
        f"{CAL} rosemary hardiness_rhs H4, overwinters_outdoors y",
        (_HARDY,),
        (_NOT_HARDY,),
    ),
    Question(
        "rosemary_prune", "rosemary",
        "When should I prune my rosemary?",
        "A light trim each year after the spring flowers fade",
        f"{OUT} rosemary prune (months 5, 6)",
        (r"after (?:it |the |its )?(?:spring )?flower|after flowering|flowers? (?:have )?fade|"
         r"(?:once|when) (?:it |the )?(?:has )?(?:finished )?flowering|late spring|early summer|"
         r"\bmay\b|\bjune\b",),
    ),
    Question(
        "rosemary_beetle", "rosemary",
        "What are the small metallic green and purple striped beetles on my rosemary?",
        "Rosemary beetle",
        f"{SIGNS} rosemary beetle",
        (r"rosemary (?:leaf )?beetle|chrysolina americana",),
    ),
    Question(
        "rosemary_foam", "rosemary",
        "There's white frothy foam on my rosemary stems. Should I spray it?",
        "Cuckoo spit from spittlebugs: no action needed",
        f"{OUT} rosemary treat_or_remove cuckoo spit",
        (r"cuckoo spit|spittle|froghopper",
         r"no (?:need|action)|(?:don.?t|do not|no need to|needn.?t) (?:need to )?"
         r"(?:spray|treat|remove|worry)|harmless|leave (?:it|them)|not (?:needed|necessary)|"
         r"isn.?t (?:needed|necessary)|unnecessary|\bnot\b[^.]*\bspray"),
    ),
    Question(
        "rosemary_pot", "rosemary",
        "How big a pot does rosemary need?",
        "At least 30 cm wide and deep, with plenty of drainage holes",
        f"{CAL} rosemary container note",
        (r"\b30\s*(?:cm|centimet)|\b12\s*(?:in|inch)",),
    ),
    Question(
        "thyme_trim", "thyme",
        "When is the best time to trim my thyme?",
        "Mid to late spring, or soon after flowering",
        f"{OUT} thyme prune (months 4, 5 and 8, 9)",
        (r"spring|after (?:it |the |its )?(?:\w+ )?flower|after flowering|\bapril\b|\bmay\b",),
    ),
    Question(
        "thyme_mulch", "thyme",
        "What can I put around my thyme to keep its stems off damp soil?",
        "Grit or gravel",
        f"{OUT} thyme mulch",
        (r"\bgrit|gravel",),
    ),
    Question(
        "thyme_repot_october", "thyme",
        "Is October a good time to repot my thyme?",
        "Best avoided: growth has slowed and fresh compost sits wet; spring is best",
        f"{OUT} thyme repot (months 9 to 2)",
        (r"spring",
         r"\bwait|avoid|\bnot (?:\w+ )?(?:best|ideal|good|recommended)|better|best|"
         r"(?:hold|put) off|isn.?t (?:\w+ )?(?:best|ideal|good)"),
    ),
    Question(
        "mint_spread", "mint",
        "How do I stop mint spreading all over the bed?",
        "Grow it in a pot, or a sunken bottomless container",
        f"{CAL} mint container note",
        (r"\bpot\b|\bpots\b|container|sunk|\bbur(?:y|ied)\b|barrier",),
    ),
    Question(
        "mint_rust", "mint",
        "What causes orange powdery pustules on my mint leaves?",
        "Mint rust",
        f"{SIGNS} mint rust",
        (r"\brust\b",),
    ),
    Question(
        "mint_after_flower", "mint",
        "What should I do with my mint after it has flowered?",
        "Cut the whole plant down to about 5 cm for a fresh crop of leaves",
        f"{OUT} mint prune (months 5 to 10); {NORMS} mint Jul next_change",
        (_CUT_BACK,),
    ),
    Question(
        "mint_beetle", "mint",
        "What are the small shiny blue beetles on my mint?",
        "Blue mint beetle",
        f"{SIGNS} blue mint beetle",
        (r"mint (?:leaf )?beetle|chrysolina coerulans",),
    ),
    Question(
        "sage_speckles", "sage",
        "My sage leaves have pale speckles all over. Are they still safe to eat?",
        "Sage leafhoppers; harmless, and the leaves remain safe to eat",
        f"{OUT} sage treat_or_remove sage and ligurian leafhoppers",
        (r"leafhopper|leaf hopper",
         r"\bsafe\b|\bedible\b|fine to eat|can (?:still )?(?:eat|use)|harmless|\byes\b"),
    ),
    Question(
        "sage_prune", "sage",
        "When should I give my sage a prune?",
        "A light prune in mid to late spring",
        f"{OUT} sage prune (months 4, 5)",
        (r"spring|\bapril\b|\bmay\b",),
    ),
    Question(
        "chives_after_flower", "chives",
        "What should I do with my chives after they flower?",
        "Cut the whole clump to about 5 cm for a flush of fresh leaves",
        f"{OUT} chives prune",
        (_CUT_BACK,),
    ),
    Question(
        "chives_divide", "chives",
        "How often should I divide my chives?",
        "Every three or four years, in spring or autumn",
        f"{OUT} chives repot",
        (r"(?:three|3)(?:\s*(?:-|–|to|or)\s*(?:four|4))?\s*years|(?:2|two)\s*(?:-|–|to|or)\s*"
         r"(?:3|three|4|four)\s*years|few years",),
    ),
    Question(
        "chives_white_dots", "chives",
        "What makes lines of small white dots along my chive leaves?",
        "Allium leaf miner",
        f"{SIGNS} allium leaf miner",
        (r"leaf[- ]?miner|phytomyza",),
    ),
)  # fmt: skip


# ---- rubric v2: POST-HOC, written 19 Oct after the run and the hand check ----
# Not pre-registered: the reported decision stays on the rubric above. v2 normalises the
# Unicode hyphens Nano writes ("leaf‑miner", U+2011) and tightens the patterns a review
# found loose: a bare "won't", "best" or "hardy" passed; "may" matched the verb; "no
# treatment mentioned" passed as "no cure"; "cut the flower stems" passed for cutting the
# clump. Questions not listed here keep their v1 patterns. Because v2 was written after
# reading the replies, its agreement with the hand check is not independent evidence.

_PREP_MAY = r"\b(?:in|from|late|early|mid|until|by|or|and|to)[- ]may\b"
_CUT_BACK_V2 = (
    r"5\s*cm|five centimet|2\s*in(?:ch)?|two inches|(?:ground|soil) level|"
    r"(?:just )?above (?:the )?soil|(?:to|near|at|down to) (?:the )?(?:base|ground)|"
    r"cut (?:it |them |the (?:whole |entire )?(?:plant|clump|mint) |the stems |everything )?"
    r"(?:right |hard |all the way )?(?:back|down)"
)
_CUT_CLUMP = (
    r"5\s*cm|five centimet|2\s*in(?:ch)?|two inches|(?:ground|soil) level|whole (?:clump|plant)|"
    r"cut (?:it |them |the (?:whole |entire )?(?:clump|plant|chives|leaves|foliage) )"
    r"(?:right |hard |all the way )?(?:back|down)"
)
_YES = r"^\s*yes\b"
_NO = r"^\s*no\b"
_V1 = {q.id: q for q in QUESTIONS}

# question id -> (must, wrong)
RUBRIC_V2: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "basil_hardy": (
        _V1["basil_hardy"].must,
        (_YES, r"\bis (?:fully |quite |very )?hardy enough"),
    ),
    "basil_eat_flowering": (
        (r"\byes\b|can (?:still )?(?:eat|use|pick|harvest)|"
         r"still (?:eat|use|good|fine|edible|safe)|"
         r"leaves (?:are|remain|stay) (?:\w+ )?(?:edible|safe|fine|good)",),
        (_NO, r"\bnot (?:\w+ ){0,2}(?:edible|safe)|"
              r"(?:shouldn.?t|should not|can.?t|cannot|don.?t|do not|avoid) (?:\w+ ){0,2}eat"),
    ),
    "basil_dm_cure": (
        (r"\bno (?:known |simple |real |effective |actual )?cure|(?:can.?t|cannot) be cured|"
         r"incurable|(?:not|isn.?t) curable|(?:pull|dig|lift) (?:\w+ ){0,3}(?:up|out)|\bbin\b|"
         r"remov\w* (?:\w+ ){0,2}(?:infected|affected|diseased|whole) plants?|destroy",),
        (),
    ),
    "parsley_life": (
        _V1["parsley_life"].must,
        (r"\bis (?:just |only )?an annual\b",),
    ),
    "coriander_bolt": (
        (r"\bbolt", r"\bdry|drought|heat|\bhot\b|\bsun|warm|stress|temperature"),
        (),
    ),
    "coriander_after_flower": (
        (r"stops? (?:\w+ ){0,3}(?:leaves|leaf|producing|making|growing)|"
         r"(?:no|fewer) (?:more |new )?leaves|leaf (?:production|growth) (?:stops|ends|slows)|"
         r"(?:won.?t|will not|doesn.?t|does not) (?:keep )?(?:\w+ ){0,2}(?:new |more |fresh )?"
         r"leaves|(?:the plant|it) (?:then |will |eventually )?dies?\b|runs? to seed|"
         r"sets? seed and dies",),
        (_YES,),
    ),
    "rosemary_hardy": (
        (r"\b(?:is|are|it.s|generally|fully|very|reasonably|quite|fairly|perfectly|usually|"
         r"mostly) (?:\w+ )?hardy\b|\bhardy (?:outdoors|outside|through|in (?:most|the|much))|"
         r"survives? (?:most |a |the )?(?:uk |british )?winters?|"
         r"overwinters? (?:outdoors|outside|well)",),
        (_NO, r"\bnot (?:\w+ ){0,2}hardy|isn.?t (?:\w+ ){0,2}hardy|half[- ]hardy|"
              r"\b(?:frost[- ])?tender\b"),
    ),
    "rosemary_prune": (
        (r"after (?:it |the |its )?(?:has )?(?:finish\w* )?(?:spring )?flower|"
         r"flowers? (?:have )?fade|late spring|early summer|\bjune\b|" + _PREP_MAY,),
        (r"(?:usually|best|ideally|typically),? (?:in )?(?:late summer|(?:early )?autumn)",),
    ),
    "rosemary_foam": (
        (r"cuckoo spit|spittle|froghopper",
         r"no (?:need|action)|(?:don.?t|do not|no need to|needn.?t) (?:need to )?"
         r"(?:spray|treat|remove|worry)|harmless|leave (?:it|them)|not (?:needed|necessary)|"
         r"isn.?t (?:needed|necessary)|unnecessary"),
        (),
    ),
    "thyme_trim": (
        (r"spring|after (?:it |the |its )?(?:\w+ )?flower|after flowering|\bapril\b|" + _PREP_MAY,),
        (),
    ),
    "thyme_repot_october": (
        (r"spring",
         r"\bwait|avoid|\bnot (?:\w+ ){0,2}(?:best|ideal|good|recommended|right)|"
         r"(?:hold|put) off|isn.?t (?:\w+ ){0,2}(?:best|ideal|good|right)|better (?:to|in|left)|"
         r"best (?:avoided|left|to wait)|\bno\b,"),
        (_YES, r"october is (?:a )?(?:good|fine|great|ideal)"),
    ),
    "mint_after_flower": ((_CUT_BACK_V2,), ()),
    "sage_speckles": (
        (r"leafhopper|leaf[- ]hopper",
         r"\bsafe\b|\bedible\b|fine to eat|can (?:still )?(?:eat|use)|harmless|" + _YES),
        (r"\bnot (?:\w+ ){0,2}(?:safe|edible)|"
         r"(?:avoid|don.?t|do not|shouldn.?t|should not) (?:\w+ ){0,2}eat",),
    ),
    "sage_prune": ((r"spring|\bapril\b|" + _PREP_MAY,), ()),
    "chives_after_flower": ((_CUT_CLUMP,), ()),
}  # fmt: skip


# ---- the answer record each herb's questions are asked under ----


def record_for(herb: Herb) -> AnalysisRecord:
    """A minimal answer record: the photo read as this herb, healthy, outdoors in a pot,
    a neutral answer and a mild October fortnight with no frost (synthetic, no place).
    The care pack is the herb's seed pack, so run_scenario works as live (no network)."""
    obs = Observation(
        species=[SpeciesCandidate(name=herb.latin, common_name=herb.common, confidence=0.9)],
        is_plant=True,
        water_stress=0,
        decline=0,
        heat_light_stress=0,
        fine_leave_it=True,
        symptoms=[],
        leaf_cues=[],
        soil_surface="not_visible",
        setting="outdoor",
        container="pot",
    )
    days = [
        DailyWeather(
            date=ON + timedelta(days=i),
            t_min=8.0,
            t_max=14.0,
            rain_mm=1.0,
            et0_mm=1.2,
            radiation_mj=6.0,
            daylight_h=10.5,
            wet_hours=0,
            is_forecast=i > 0,
        )
        for i in range(-14, 8)
    ]
    answer = Answer(
        headline="Leave it for now.",
        do=[],
        dont=None,
        watch="Leaves that yellow or wilt.",
        tell_me=None,
        level="fairly_sure",
        level_text="Fairly sure",
        in_ten=7,
        factors=[],
        chips=[],
        compare=[],
        runs=[],
        assumptions=[],
    )
    return AnalysisRecord(
        record_id=f"chat-search-{herb.common}",
        taken_at=datetime(ON.year, ON.month, ON.day, 11, tzinfo=UTC),
        observation=obs,
        environment=Environment(lat=0.0, lon=0.0, days=days, source="synthetic mild October"),
        pack=seed_pack(normalise_species(herb.latin)),
        state=None,
        answer=answer,
        told=None,
    )


# ---- the rubric ----

_URL = re.compile(r"https?://[^\s\]\)>,;\"']+", re.I)
# a bracketed address without a scheme: "[rhs.org.uk/herbs/basil]"
_BARE = re.compile(r"\[\s*((?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/[^\]\s]*)?)\s*\]", re.I)
_CITES = re.compile(r"\[[^\]]*\]|https?://\S+")


def own_text(text: str) -> str:
    """The model's reply less the app's own "Less sure" line."""
    return text.replace(LESS_SURE, "").strip()


def prose(text: str) -> str:
    """The reply's own words: citations and addresses removed."""
    return " ".join(_CITES.sub(" ", own_text(text)).split())


def norm_url(url: str) -> str:
    u = re.sub(r"^https?://", "", url.strip().lower())
    u = re.sub(r"^www\.", "", u)
    return u.rstrip("/.,;:)")


def cited(text: str) -> list[str]:
    """Every source the reply names, normalised, in order, once each."""
    out: list[str] = []
    for u in [*_URL.findall(text), *_BARE.findall(text)]:
        n = norm_url(u)
        if n and n not in out:
            out.append(n)
    return out


def _matches(must: Sequence[str], wrong: Sequence[str], words: str) -> bool:
    return all(re.search(p, words, re.I) for p in must) and not any(
        re.search(p, words, re.I) for p in wrong
    )


def correct(q: Question, text: str) -> bool:
    """M1, the pre-registered rubric."""
    return _matches(q.must, q.wrong, prose(text))


_HYPHENS = str.maketrans({"‐": "-", "‑": "-"})


def correct_v2(q: Question, text: str) -> bool:
    """Rubric v2 (post-hoc): Unicode hyphens made plain, and the tighter patterns."""
    must, wrong = RUBRIC_V2.get(q.id, (q.must, q.wrong))
    return _matches(must, wrong, prose(text).translate(_HYPHENS))


def _names(herb: Herb, text: str) -> bool:
    low = text.lower()
    return any(re.search(rf"\b{re.escape(n)}", low) for n in herb.names)


def on_plant(sources: Sequence[str], hits: Sequence[dict], herb: Herb) -> bool | None:
    """None when nothing is cited. True only when every cited source is one of this
    turn's hits (an address match, or the hit's address starting with the cited one) and
    that hit names the herb."""
    if not sources:
        return None
    for s in sources:
        hit = next(
            (h for h in hits if norm_url(h["url"]) == s or norm_url(h["url"]).startswith(s)),
            None,
        )
        if hit is None or not _names(herb, f"{hit['title']} {hit['url']} {hit['snippet']}"):
            return False
    return True


def unsure(text: str) -> bool:
    own = own_text(text)
    return bool(UNSURE.search(own)) or own.startswith((NO_ANSWER, UNAVAILABLE))


def hits_of(tools: Sequence[dict]) -> list[dict]:
    return [
        h for t in tools if t.get("name") == "search_web" for h in t["result"].get("results", [])
    ]


def score(q: Question, text: str, tools: Sequence[dict]) -> dict:
    sources = cited(text)
    return {
        "correct": correct(q, text),
        "cites": bool(sources),
        "on_plant": on_plant(sources, hits_of(tools), HERBS[q.herb]),
        "unsure": unsure(text),
        "less_sure": LESS_SURE in text,
        "correct_v2": correct_v2(q, text),  # post-hoc, not the decision metric
    }


# ---- the summary ----


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else math.nan


def _interval(values: list[float], n: int, seed: int) -> dict:
    ci = m.cluster_bootstrap(values, _mean, None, n=n, seed=seed)
    return {"value": _mean(values), "lo": ci.lo, "hi": ci.hi, "n": len(values)}


def summarise(rows: Sequence[dict], *, n: int = 2000, seed: int = 0) -> dict:
    """Each arm's rates and the paired on-minus-off differences, resampling questions."""
    ok = [r for r in rows if r.get("status") == "ok"]
    # by question id, so the bootstrap draws do not depend on the order rows finished in
    ok = sorted(ok, key=lambda r: r["id"])
    by_arm = {a: {r["id"]: r for r in ok if r["arm"] == a} for a in ARMS}
    out: dict = {"n_rows": len(rows), "n_ok": len(ok), "arms": {}, "diff": {}}
    for arm, rs in by_arm.items():
        out["arms"][arm] = {}
        for name in METRICS + POST_HOC:
            vals = [float(v) for r in rs.values() if (v := r["score"].get(name)) is not None]
            if vals:
                out["arms"][arm][name] = _interval(vals, n, seed)
    both = sorted(set(by_arm["on"]) & set(by_arm["off"]))
    out["paired_questions"] = len(both)
    for name in METRICS + POST_HOC:
        pairs = [
            (by_arm["on"][i]["score"].get(name), by_arm["off"][i]["score"].get(name)) for i in both
        ]
        diffs = [float(a) - float(b) for a, b in pairs if a is not None and b is not None]
        if diffs:
            out["diff"][name] = _interval(diffs, n, seed)
    on, off = by_arm["on"], by_arm["off"]
    out["flips"] = {
        "on_only": sorted(
            i for i in both if on[i]["score"]["correct"] > off[i]["score"]["correct"]
        ),
        "off_only": sorted(
            i for i in both if on[i]["score"]["correct"] < off[i]["score"]["correct"]
        ),
    }
    return out


def hand_agreement(rows: Sequence[dict], hand: dict[str, dict]) -> dict:
    """How often each rubric agrees with the hand verdicts ("<id>|<arm>": {"correct": ...})."""
    by = {f"{r['id']}|{r['arm']}": r for r in rows if r.get("status") == "ok"}
    keys = [k for k in hand if k in by]
    out: dict = {"n": len(keys)}
    for name in ("correct", "correct_v2"):
        out[name] = sum(by[k]["score"].get(name) == hand[k]["correct"] for k in keys)
    return out


def decision(diff: dict | None) -> str:
    if not diff or math.isnan(diff["lo"]):
        return "no result"
    if diff["lo"] > 0:
        return "search makes the chat more correct"
    if diff["hi"] < 0:
        return "search makes the chat less correct"
    return "no measurable change in correctness"
