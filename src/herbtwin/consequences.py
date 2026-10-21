"""What happens if you do each action (D34). Never a model call.

Water, shelter, light and leaving it: the plant model's view. Prune: the outcomes table
row. Treat: only when the advisor named one of this plant's known problems (whole
phrase). Feed, repot and the other finer actions (D43): this month's row, or "best done
in <months>" when the plant has rows for other months only. Otherwise "no reliable data on what this changes".
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from typing import Literal, get_args

from herbtwin.outcomes import OutcomeAction, load_outcomes, outcome_for, problems_for
from herbtwin.plant_model import ModelView
from herbtwin.schemas import CareAction

NO_DATA = "no reliable data on what this changes"
# actions with a right time of year: off-season they say when instead. Checking for pests,
# humidity, rotating and isolating are done when needed, never deferred (review, B1).
SEASONAL = ("feed", "repot", "change_soil", "mulch")
Source = Literal["plant_model", "outcome_table", "norm_rule", "web_search", "none"]
# a row for this month that advises against the job: "Not now: RHS advises not to feed aloes
# in winter", "Little benefit: winter light is too low…", "Skip feeding now: …", "Best
# avoided: growth slows…" (the herbs' Sep–Feb repot rows), "feed only sparingly, if at all"
# (orchid winter). Every seasonal row's opener was checked on 19 Oct; the rest advise doing it
_NOT_NOW = re.compile(r"^(?:not now|skip|little benefit|best avoided)\b|\bif at all\b", re.I)
_FEED = re.compile(r"\b(feed|feeding|fertili[sz]e|fertili[sz]er)\b")
_REPOT = re.compile(r"\b(repot|re-pot|repotting|pot it on|bigger pot)\b")


@dataclass(frozen=True)
class Consequence:
    text: str
    source: Source
    less_sure: bool  # literature-based: a sourced row, not the plant model
    off_season: bool = False  # a seasonal job outside this plant's months ("best done in …")


NONE = Consequence(NO_DATA, "none", False)


def named_problem(answer: str, problems: list[str], plant_key: str | None = None) -> str | None:
    """The longest of `problems` the answer names as a whole phrase, or None. A problem
    led by the plant's own name may be named without it when two words are left and no
    other listed problem has them: "downy mildew" on basil is basil downy mildew (21 Oct:
    one repeat in 5 said only that, found no row, and headlined "Treat it." over a disease
    with no cure). "rust" or "beetle" alone could be anything, so needs the full name."""
    text = answer.casefold()
    names = {p.casefold(): p for p in problems}
    own = _own_names(plant_key)
    for short, p in sorted(_shortened(names, own).items(), key=lambda x: len(x[0]), reverse=True):
        if re.search(rf"\b{re.escape(short)}\b", text):
            return p
    return None


def _own_names(plant_key: str | None) -> set[str]:
    """The plant's one-word common names ("basil", "mint"), from the season norms."""
    if plant_key is None:
        return set()
    from herbtwin.seasonal import load_norms  # here: seasonal is the bigger module

    return {
        c.casefold()
        for n in load_norms()
        if n.plant == plant_key
        for c in n.common_names
        if " " not in c
    }


def _shortened(names: dict[str, str], own: set[str]) -> dict[str, str]:
    """Each listed name, and the safe short form of those led by the plant's own name."""
    out = dict(names)
    for full, p in names.items():
        first, _, rest = full.partition(" ")
        if (
            first in own
            and len(rest.split()) >= 2
            and not any(rest in other for other in names if other != full)
        ):
            out.setdefault(rest, p)
    return out


def _months(months: set[int]) -> str:
    names = [calendar.month_abbr[m] for m in sorted(months)]
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} or {names[-1]}"


def _table(plant_key: str, action: str, month: int, problem: str | None = None) -> Consequence:
    row = outcome_for(plant_key, action, month, problem)
    if row is not None:
        rest = action in SEASONAL and bool(_NOT_NOW.search(row.if_you_do))
        return Consequence(row.if_you_do, "outcome_table", True, rest)
    if action in SEASONAL:
        other = {  # the months a row says to do it: never a "not now" row's
            m
            for r in load_outcomes()
            if r.plant == plant_key and r.action == action and not _NOT_NOW.search(r.if_you_do)
            for m in r.months
        }
        if other:
            return Consequence(f"best done in {_months(other)}", "outcome_table", True, True)
    return NONE


def consequence_for(
    action: CareAction,
    *,
    plant_key: str | None,
    month: int,
    answer: str,
    views: dict[CareAction, ModelView],
) -> Consequence:
    if action in views:
        return Consequence(views[action].why, "plant_model", False)
    if plant_key is None:
        return NONE
    if action == "treat_or_remove":
        problem = named_problem(answer, problems_for(plant_key), plant_key)
        return _table(plant_key, "treat_or_remove", month, problem) if problem else NONE
    if action in get_args(OutcomeAction):
        return _table(plant_key, action, month)
    if action == "other":
        # an older or vaguer answer: find the action in the text
        text = answer.casefold()
        if _FEED.search(text):
            return _table(plant_key, "feed", month)
        if _REPOT.search(text):
            return _table(plant_key, "repot", month)
    return NONE
