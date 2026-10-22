"""What the person's own note under the answer says about the plant: where it grows, its
light, and the signs they see. Plain word matching, no model call (22 Oct site walk, Top 5
#1: told "It is in a pot on a sunny balcony and the lower leaves are going yellow.", the
refined page still said "In the ground" and used the soil maps for it).

Only plain statements count. A question, a plan or how it was ("Should I put it in a pot?",
"it used to be indoors") says nothing about the plant now; a negated phrase ("not in a pot")
is dropped, never turned round; and when a note says both of a pair ("some in pots, some in
the ground") we don't guess."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from herbtwin.compass import DIRECTION_TEXT, nearest_direction
from herbtwin.schemas import (
    CHANGED_TEXT,
    LAST_WATERED_TEXT,
    SOIL_FEEL_TEXT,
    SQUEEZE_TEXT,
    WINDOW,
    Told,
)

Kind = Literal["container", "setting", "sun"]

# (pattern, kind, value, our words). The words are ours, short, for "You told us: …"
_WHERE: tuple[tuple[re.Pattern[str], Kind, str, str], ...] = tuple(
    (re.compile(p, re.I), kind, value, words)
    for p, kind, value, words in (
        (r"\bwindow ?box(?:es)?\b", "container", "pot", "in a window box"),
        (r"\braised beds?\b", "container", "ground", "in a raised bed"),
        (
            r"\b(?:pot|pots|potted|planter|planters|tub|tubs|container|containers|trough"
            r"|grow ?bag)\b(?! (?:next to|beside|near) (?:it|this one|mine)\b)",
            "container",
            "pot",
            "in a pot",
        ),
        (
            r"\b(?:in(?:to)? the (?:ground|soil)|planted out"
            r"|(?:flower ?|veg(?:etable)? |garden |herb )beds?|in (?:the|a|my) (?:beds?|borders?)"
            r"|borders?(?! (?:on|with)\b)|veg(?:etable)? patch)\b",
            "container",
            "ground",
            "in the ground",
        ),
        (r"\bbalcon(?:y|ies)\b", "setting", "outdoor", "on a balcony"),
        (r"\bpatio\b", "setting", "outdoor", "on a patio"),
        (
            # never "garden centre" (where it was bought) or "outside leaves" (a part of it)
            r"\b(?:outdoors?|outside(?! (?:leaves|stems|edge|of the (?:leaves|pot)))"
            r"|garden(?! cent(?:re|er))|terrace|allotment|doorstep|courtyard|decking)\b",
            "setting",
            "outdoor",
            "outdoors",
        ),
        (r"\bwindow ?sills?\b|\bwindowsills?\b", "setting", "indoor", "on a windowsill"),
        (
            r"\b(?:indoors?|inside(?! (?:the |its )?(?:pot|leaves|stems))|kitchen(?! garden)"
            r"|living room|bedroom|bathroom|in the house|in my (?:flat|house))\b",
            "setting",
            "indoor",
            "indoors",
        ),
        (
            r"\b(?:sunny|sunniest|full sun|lots of sun|plenty of sun|sun all day|all-day sun"
            r"|south[- ]facing)\b",
            "sun",
            "sunny",
            "sunny",
        ),
        (
            r"\b(?:shady|shaded|shade|north[- ]facing|not much sun|little sun"
            r"|no (?:direct )?sun|dark corner|gloomy)\b",
            "sun",
            "shady",
            "shady",
        ),
    )
)

_PART = {
    **dict.fromkeys(("lower", "bottom", "older", "old"), "lower"),
    **dict.fromkeys(("top", "upper", "new", "young", "newer"), "new"),
    "outer": "outer",
}
_PARTS = "|".join(_PART)

# the signs a person names, each with our words for it (a function of the match)
_SIGNS: tuple[tuple[re.Pattern[str], object], ...] = tuple(
    (re.compile(p, re.I), words)
    for p, words in (
        (
            rf"\b(?:(?P<part>{_PARTS})\s+)?leaves?\s+(?:(?:are|is|have|has)\s+)?"
            r"(?:(?:going|turning|gone|turned|getting|looking|all)\s+)?yellow\w*",
            lambda m: _part_words(m, "yellow"),
        ),
        (
            rf"\byellow(?:ing|ed)?\s+(?:(?P<part>{_PARTS})\s+)?leaves\b",
            lambda m: _part_words(m, "yellow"),
        ),
        (
            rf"\b(?:(?P<part>{_PARTS})\s+)?leaves?\s+(?:(?:are|is|have|has)\s+)?"
            r"(?:going|turning|gone|turned|getting)\s+brown\b",
            lambda m: _part_words(m, "brown"),
        ),
        (
            r"\bbrown(?:ing)?\s+(?P<what>tips|edges|spots|patches|leaves|stems)\b",
            lambda m: f"brown {m['what'].lower()}",
        ),
        (r"\b(?:wilt(?:ing|ed|s)?|droop(?:ing|y|s|ed)?|floppy|limp)\b", "drooping"),
        (r"\b(?:holes?|holey|nibbled|chewed)\b", lambda m: _on_leaves(m, "holes in the leaves")),
        (r"\b(?:spots|spotty|spotted)\b", lambda m: _on_leaves(m, "spots on the leaves")),
        (r"\b(?:mildew|powdery|white powder)\b", "white powdery patches"),
        (
            r"\b(?P<pest>aphids?|greenfly|blackfly|whitefly|caterpillars?|slugs?|snails?"
            r"|beetles?|bugs?|insects?|mites?|thrips|mealybugs?|vine weevils?)\b",
            lambda m: m["pest"].lower(),
        ),
        (r"\b(?:flowering|bolting|bolted|gone to seed|going to seed)\b", "flowering"),
        (r"\bleggy\b", "leggy"),
        (r"\bleaves?\s+(?:are\s+)?curl(?:ing|ed)\b|\bcurl(?:ing|ed)\s+leaves\b", "leaves curling"),
    )
)

_LEAF = re.compile(r"\b(?:leaf|leaves|foliage)\b", re.I)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_CLAUSE = re.compile(r"[,;:()]|\s(?:and|but|so|because|though|although|while|whereas)\s", re.I)
# a plan, a wish or the past, not how it is now
_HYPOTHETICAL = re.compile(
    r"\b(?:if|should|could|would|shall|might|will|plan(?:ning)?|thinking|want(?:ing)? to"
    r"|going to|used to|was|were|previously|originally)\b",
    re.I,
)
_QUESTION_START = re.compile(
    r"^\s*(?:what|how|why|when|where|which|can|could|do|does|did|is|are|was|has|have|should"
    r"|would|will)\b",
    re.I,
)
_NEGATED = re.compile(r"\b(?:not|no|never|without|hardly|nor)\b|n['’]t\b", re.I)
_MOVED_FROM = re.compile(r"\b(?:from|out of)\s+(?:\w+\s+)?$", re.I)


def _on_leaves(m: re.Match[str], words: str) -> str | None:
    # "holes" and "spots" alone are a pot's or a garden's too ("drainage holes", "sunny
    # spots"): a sign only with the leaves named in the same clause
    return words if _LEAF.search(m.string) else None


def _part_words(m: re.Match[str], colour: str) -> str:
    part = _PART.get((m["part"] or "").lower())
    return f"{part} leaves {colour}" if part else f"leaves {colour}"


@dataclass(frozen=True)
class NoteFacts:
    container: Literal["pot", "ground"] | None = None
    setting: Literal["indoor", "outdoor"] | None = None
    sun: Literal["sunny", "shady"] | None = None
    signs: tuple[str, ...] = ()
    where_words: tuple[str, ...] = ()  # container, then setting, in our words

    @property
    def said(self) -> tuple[str, ...]:
        """Everything read, in our words: where, then light, then signs."""
        return (*self.where_words, *((self.sun,) if self.sun else ()), *self.signs)


def _clauses(text: str) -> list[str]:
    """The note's plain statements: a question's last clause and any plan are left out."""
    kept = []
    for sentence in _SENTENCE.split(text.strip()):
        asked = sentence.rstrip(" \"'”’!.)").endswith("?")
        parts = [p for p in _CLAUSE.split(sentence) if p and p.strip()]
        for i, part in enumerate(parts):
            if _HYPOTHETICAL.search(part):
                continue
            if asked and (i == len(parts) - 1 or _QUESTION_START.search(part)):
                continue
            kept.append(part)
    return kept


def _stated(clause: str, m: re.Match[str]) -> bool:
    """Said as so: no "not" in the few words before it, and not where it was moved from."""
    before = clause[: m.start()]
    if _MOVED_FROM.search(before):
        return False
    return not _NEGATED.search(" ".join(before.split()[-4:]))


def note_facts(text: str | None) -> NoteFacts:
    if not text or not text.strip():
        return NoteFacts()
    found: dict[Kind, dict[str, str]] = {"container": {}, "setting": {}, "sun": {}}
    signs: list[str] = []
    for clause in _clauses(text):
        for pattern, kind, value, words in _WHERE:
            for m in pattern.finditer(clause):
                if _stated(clause, m):
                    found[kind].setdefault(value, words)
        taken: list[tuple[int, int]] = []  # "brown spots" is one sign, not two
        for pattern, words in _SIGNS:
            for m in pattern.finditer(clause):
                if any(m.start() < e and s < m.end() for s, e in taken) or not _stated(clause, m):
                    continue
                said = words(m) if callable(words) else words
                if said is None:
                    continue
                taken.append(m.span())
                if said not in signs:
                    signs.append(said)

    def one(kind: Kind) -> tuple[str | None, str | None]:
        # both of a pair said: we don't guess which
        got = found[kind]
        return next(iter(got.items())) if len(got) == 1 else (None, None)

    container, held = one("container")
    setting, place = one("setting")
    sun, _ = one("sun")
    return NoteFacts(
        container=container,  # type: ignore[arg-type]
        setting=setting,  # type: ignore[arg-type]
        sun=sun,  # type: ignore[arg-type]
        signs=tuple(signs),
        where_words=tuple(w for w in (held, place) if w),
    )


QUOTE_MAX = 80


def _note_words(text: str | None, said_already: tuple[str, ...] = ()) -> tuple[bool, str] | None:
    """(asked, words): what we read in the note, in our words, or the note itself, quoted
    and trimmed, when we read nothing in it. Words the picks already said are not said
    twice."""
    if not text or not text.strip():
        return None
    read = note_facts(text).said
    if read:  # what the picks already said is not said twice
        said = [w for w in read if w not in said_already]
        return (False, ", ".join(said)) if said else None
    note = " ".join(text.split())
    if len(note) > QUOTE_MAX:
        note = note[:QUOTE_MAX].rsplit(" ", 1)[0].rstrip(" ,.;:") + "…"
    asked = note.rstrip(" \"'”’!.)").endswith("?")
    return asked, f"“{note}”"


def echo(text: str | None) -> str | None:
    """The line under "Changed after what you told us": what we read in the note, in our
    words, or the note itself, quoted and trimmed, when we read nothing in it."""
    got = _note_words(text)
    if got is None:
        return None
    asked, words = got
    return f"{'You asked' if asked else 'You told us'}: {words}"


# "Anything changed recently?", answered in a few words
_CHANGED_SAID = {
    "moved": "{} recently",
    "repotted": "{} recently",
    "new_plant": "a {}",
    "nothing": "{} changed recently",
}


def _picks(told: Told) -> list[str]:
    """Each pick given under the answer, in the questions' own words."""
    picks = []
    if told.heading is not None:
        tap = told.heading
        way = tap.direction or nearest_direction(tap.heading or 0.0)
        picks.append(f"faces {DIRECTION_TEXT[way]}")
    if told.setting:
        picks.append(f"{told.setting}s")
    if told.window:
        picks.append(WINDOW[told.window].echo)  # schemas.WINDOW
    if told.place:
        picks.append(f"in {told.place}")
    if told.soil_feel:
        picks.append(f"soil {SOIL_FEEL_TEXT[told.soil_feel]}")
    if told.squeeze:
        picks.append(f"squeeze test: {SQUEEZE_TEXT[told.squeeze]}")
    # "not sure" is no reading: it is not said back as one
    if told.last_watered and told.last_watered != "not_sure":
        picks.append(f"watered {LAST_WATERED_TEXT[told.last_watered]}")
    if told.changed:
        picks.append(_CHANGED_SAID[told.changed].format(CHANGED_TEXT[told.changed]))
    return picks


def told_echo(told: Told | None) -> str | None:
    """The line under "Checked again" or "Changed after what you told us": every pick given
    and the note, said back (22 Oct site walk 2: a NW pick was never said, so the page read
    as if nothing had been heard). None when nothing was told."""
    if told is None:
        return None
    picks = _picks(told)
    note = _note_words(told.question, tuple(picks))
    if note is not None and note[0]:  # a question is asked, not told
        asked = f"You asked: {note[1]}"
        return f"You told us: {'; '.join(picks)}. {asked}" if picks else asked
    if note is not None:
        picks.append(note[1])
    return "You told us: " + "; ".join(picks) if picks else None
