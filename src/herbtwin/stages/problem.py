"""Photo + known plant -> a named pest or disease, or None. The second, targeted look.

Runs only when the first read suspected a problem (pipeline.read_photo): probes on 13 Oct
showed the first read's free-text guess rarely false-alarms but often names the wrong
disease, while this check, which knows the plant and picks from its listed problems with
what each looks like, names it right far more often. A failed check never stops the answer.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ValidationError

from herbtwin.adapters.base import AdapterError, ModelAdapter, extract_json
from herbtwin.confidence import matches_sign
from herbtwin.outcomes import problems_for
from herbtwin.schemas import Observation, ProblemSeen
from herbtwin.seasonal import normal_for

log = logging.getLogger(__name__)

SIGNS_PATH = Path(__file__).resolve().parents[3] / "data" / "outcomes" / "problem_signs_uk.json"
SYSTEM = (
    "You check one plant photo for known pests and diseases. Name a problem only when the "
    "photo plainly shows its signs; yellowing, wilting, old damage or a blur are not enough. "
    "In seen, describe what this photo shows in your own words; do not copy the list. "
    "Reply with JSON only, matching the schema."
)
PROBLEM_MAX_TOKENS = 1024
SEEN_MAX = 300


class _Reply(BaseModel):
    problem: str
    seen: str = ""


@lru_cache(maxsize=1)
def signs() -> dict[str, dict]:
    """Each named problem's {photo, signs, source}. photo=false ones are never offered."""
    return json.loads(SIGNS_PATH.read_text())["problems"]


def checkable(plant_key: str) -> list[str]:
    """The plant's listed problems that show in a photo, in problems_for order."""
    table = signs()
    return [p for p in problems_for(plant_key) if table.get(p, {}).get("photo") is True]


# words that say nothing about WHICH problem: two names sharing only these do not agree
_GENERIC = frozenset(
    "a an and the of on in with possible likely early mild severe some damage disease "
    "diseases fungal fungus infection infestation leaf leaves plant plants spot spots "
    "insect insects pest pests bug bugs feeding mildew mould mold basil mint sage rose "
    "leek rosemary thyme parsley coriander".split()
)


def _stem(word: str) -> str:
    """Plain endings off, so "miner" meets "mining" and "aphids" meets "aphid"."""
    if word.endswith("ing") and len(word) > 5:
        return word[:-3]
    if word.endswith("er") and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def _words(text: str) -> set[str]:
    """The telling words of a problem name or guess."""
    plain = re.sub(r"[^a-z ]", " ", text.lower()).split()
    return {_stem(w) for w in plain if w not in _GENERIC and len(w) >= 3}


# the listed problems that are diseases; every other listed problem is a pest
DISEASES = frozenset(
    {
        "basil downy mildew",
        "black spot",
        "coral spot",
        "grey mould",
        "leek rust",
        "mint rust",
        "powdery mildew",
        "rose rust",
        "rust",
    }
)
_DISEASE_WORDS = re.compile(
    r"\b(fung\w*|mildew|mould|mold|rust\w*|spot\w*|blight|rot|rotting|disease\w*|"
    r"blotch\w*|lesion\w*|pustule\w*|powder\w*|fuzz\w*)\b"
)
_PEST_WORDS = re.compile(
    r"\b(insect\w*|bug\w*|beetle\w*|aphid\w*|mite\w*|fly|flies|caterpillar\w*|slug\w*|"
    r"snail\w*|weevil\w*|scale|mealy\w*|larva\w*|pest\w*|hole\w*|eaten|chew\w*|"
    r"thrip\w*|\w*hopper\w*|moth\w*|miner\w*|mining|web\w*|gnat\w*)\b"
)


def _kind_of_guess(likely: str) -> str | None:
    text = likely.lower()
    disease, pest = bool(_DISEASE_WORDS.search(text)), bool(_PEST_WORDS.search(text))
    return "both" if disease and pest else "disease" if disease else "pest" if pest else None


def suspicion(obs: Observation) -> str | None:
    """The read's own words when they name a disease or pest sign (fuzz, pustules, insects,
    holes...), else None: the second look runs only then. The read prompt is unchanged: any
    extra request in it cost Gemma about 5 of 193 species reads (13 Oct A/B)."""
    text = "; ".join([*obs.symptoms, *obs.leaf_cues]).strip()
    return text if text and _kind_of_guess(text) is not None else None


_SLUG = re.compile(r"\b(slug|snail)s?\b")
# a denial ("no slugs visible", "not a snail", "no sign of slugs") is not a sighting
_NO_SLUG = re.compile(
    r"\b(no (visible |signs? of )?|not an? )(slug|snail)s?( (or|and) (an? )?(slug|snail)s?)?\b"
)


def slugs_seen(obs: Observation) -> bool:
    """A slug or snail with no plant in the photo: the read says so in its own words (18 Oct
    probe: 20 of 24 slug photos read as no plant, 11 of those named the slug or snail). The
    read prompt is unchanged, so no new field is asked for."""
    if obs.is_plant:
        return False
    text = "; ".join([*obs.symptoms, *obs.leaf_cues, obs.notes, obs.quality_note]).lower()
    return bool(_SLUG.search(_NO_SLUG.sub("", text)))


def second_look_reason(obs: Observation, plant_key: str | None, month: int) -> str | None:
    """Why to take the second look, as the words to check against: the read's own disease
    or pest words, else the plant's problem sign for the month that the read's symptoms
    describe (17 Oct: "grey dusty patches on leaf underside" names no disease, but it is
    basil downy mildew's October sign). None: no second look."""
    if (said := suspicion(obs)) is not None:
        return said
    norm = normal_for(plant_key, month) if plant_key else None
    if norm is None or not obs.symptoms:
        return None
    for sign in norm.problem_signs:
        # only a pest or disease sign: a cultural one (cold injury, too little light) is not
        # something the second look can name, and it would only add a call
        if _kind_of_guess(sign) is not None and matches_sign(sign, obs.symptoms):
            return _named(sign)
    return None


def _named(sign: str) -> str:
    """The problem a sign names, from its brackets ("…(basil downy mildew, common in
    autumn)" -> "basil downy mildew"), so the agreement checks the name, not every word of
    a long sign; the sign itself when no bracket names a pest or disease."""
    for inside in reversed(re.findall(r"\(([^()]*)\)", sign)):
        name = inside.split(",")[0].split(";")[0].strip()
        if name and not name.lower().startswith("not") and _kind_of_guess(name) is not None:
            return name
    return sign


def agreement(name: str, likely: str) -> str | None:
    """How the check's name fits the read's own guess: "words" (a telling word in common),
    "kind" (both a disease, or both a pest), or None (a pest named after a disease guess, or
    no guess). Eval 13 Oct (256 photos, read prompt unchanged, guess = the read's symptom
    words): right 23, wrong 22 -> 7, healthy false alarms 11 -> 0 of 150."""
    if agrees(name, likely):
        return "words"
    guess = _kind_of_guess(likely)
    kind = "disease" if name in DISEASES else "pest"
    return "kind" if guess in (kind, "both") else None


def agrees(name: str, likely: str) -> bool:
    """Does the check's listed name share a telling word with the first read's own guess?
    End-to-end eval, 13 Oct: when the read got the plant wrong, the check picked from the
    wrong list ("aphids" for rust, "leafhoppers" for powdery mildew); this rejects those."""
    return bool(_words(name) & _words(likely))


def check_problem(
    adapter: ModelAdapter,
    image: bytes,
    mime: str,
    plant_key: str,
    common: str,
    *,
    likely: str | None = None,  # the read's own guess; None skips the agreement (tests only)
) -> ProblemSeen | None:
    """One vision call: does the photo plainly show one of this plant's problems? None when
    nothing is checkable (no call), the reply is "none", the call or reply fails, or (given
    the first read's own guess as `likely`) the name does not agree with it."""
    names = checkable(plant_key)
    if not names:
        return None
    table = signs()
    user = (
        f"This plant is {common} ({plant_key}). Does the photo plainly show one of these?\n"
        + "\n".join(f"- {n}: {table[n]['signs']}" for n in names)
        + "\nIf not, answer none."
    )
    schema = {
        "type": "object",
        "properties": {
            "problem": {"type": "string", "enum": [*names, "none"]},
            "seen": {"type": "string"},
        },
        "required": ["problem", "seen"],
    }
    try:
        raw = adapter.complete_with_image(
            SYSTEM, user, image, mime, schema, max_tokens=PROBLEM_MAX_TOKENS
        )
        reply = _Reply.model_validate_json(extract_json(raw))
    except (AdapterError, ValueError, ValidationError):
        log.exception("problem check failed plant=%s", plant_key)
        return None
    name = reply.problem.strip()
    if name == "none":
        return None
    if name not in names:  # the model ignored the enum: not one we can describe
        log.warning("problem check named an unlisted problem plant=%s", plant_key)
        return None
    fit = "words" if likely is None else agreement(name, likely)
    if fit is None:
        log.info("problem check %r disagrees with the read's %r plant=%s", name, likely, plant_key)
        return None
    entry = table[name]
    return ProblemSeen(
        name=name,
        looks_like=entry["signs"],
        source=entry["source"],
        seen=reply.seen.strip()[:SEEN_MAX],
        sure=fit == "words",
    )
