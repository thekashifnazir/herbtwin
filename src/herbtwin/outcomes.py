"""What happens if you prune, treat, feed or repot a plant: a literature-backed table.

The table lives in data/outcomes/outcomes_uk.json, one row per plant, action, problem
(treat only) and season. It lets the app show a sourced consequence beside an action
("cut mint to 5 cm after flowering: fresh leaves within weeks") instead of a guessed one.
A false or overconfident consequence is the costly error, so a lookup that does not match
a row exactly returns None ("no reliable data"), never the nearest row.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Literal, get_args

from pydantic import BaseModel, Field, model_validator

from herbtwin.seasonal import load_norms

OutcomeAction = Literal[
    "prune",
    "treat_or_remove",
    "feed",
    "repot",
    "change_soil",
    "mulch",
    "humidity",
    "rotate",
    "check_pests",
    "isolate",
]

OUTCOMES_PATH = Path(__file__).resolve().parents[2] / "data" / "outcomes" / "outcomes_uk.json"

MAX_WORDS = 30


def _words(text: str) -> int:
    return len(text.split())


class ActionOutcome(BaseModel):
    plant: str  # key as in norms_uk.json `plant`, or a genus key such as "mentha"
    action: OutcomeAction
    problem: str | None  # treat only: the named problem, lower case; None otherwise
    problem_aliases: list[str]  # other names a person or the advisor may use
    months: list[int] = Field(min_length=1)  # months (1..12) this outcome holds
    if_you_do: str  # <= 30 words: what happens if you do it now
    if_you_dont: str | None  # <= 30 words, when the source says so
    caution: str | None
    evidence_tier: Literal["A", "B", "C", "D"]  # tiers as in docs/reference/risk-models.md
    sources: list[str] = Field(min_length=1)  # URLs

    @model_validator(mode="after")
    def _check(self) -> ActionOutcome:
        if self.plant != self.plant.strip().lower():
            raise ValueError(f"plant key must be lower case: {self.plant!r}")
        if any(not 1 <= m <= 12 for m in self.months) or len(set(self.months)) != len(self.months):
            raise ValueError(f"months must be distinct values in 1..12: {self.months}")
        if (self.action == "treat_or_remove") != (self.problem is not None):
            raise ValueError("a treat row names its problem; other rows do not")
        if self.problem is None and self.problem_aliases:
            raise ValueError("problem aliases without a problem")
        for name in (self.problem, *self.problem_aliases):
            if name is not None and (not name.strip() or name != name.lower()):
                raise ValueError(f"problem names are non-empty lower case: {name!r}")
        if not self.if_you_do.strip():
            raise ValueError("if_you_do is empty")
        for text in (self.if_you_do, self.if_you_dont):
            if text is not None and _words(text) > MAX_WORDS:
                raise ValueError(f"over {MAX_WORDS} words: {text!r}")
        if not all(s.startswith(("https://", "http://")) for s in self.sources):
            raise ValueError(f"every source is a URL: {self.sources}")
        return self


@cache
def load_outcomes(path: Path = OUTCOMES_PATH) -> tuple[ActionOutcome, ...]:
    return tuple(ActionOutcome.model_validate(e) for e in json.loads(path.read_text()))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


@cache
def _plant_keys() -> dict[str, str]:
    """Any name the seasonal norms know (scientific key or common name) -> plant key."""
    keys: dict[str, str] = {}
    for norm in load_norms():
        for name in (norm.plant, *norm.common_names):
            keys[_norm(name)] = norm.plant
    return keys


def _names(row: ActionOutcome) -> set[str]:
    return {_norm(n) for n in (row.problem or "", *row.problem_aliases) if n}


def outcome_for(
    plant: str, action: str, month: int, problem: str | None = None
) -> ActionOutcome | None:
    """The outcome of an action on a plant in a month, or None when there is no reliable row.

    `plant` is a scientific key or common name, any case (as `seasonal.normal_for`).
    For "treat_or_remove", `problem` must equal the row's problem or one of its aliases
    (case-insensitive, whole phrase); an unmatched problem returns None, never the closest
    row. For prune, feed and repot, `problem` is ignored.
    """
    key = _plant_keys().get(_norm(plant))
    act = _norm(action)
    if key is None or act not in get_args(OutcomeAction):
        return None
    if act == "treat_or_remove":
        if problem is None or not problem.strip():
            return None
        wanted = _norm(problem)
    for row in load_outcomes():
        if row.plant != key or row.action != act or month not in row.months:
            continue
        if act == "treat_or_remove" and wanted not in _names(row):
            continue
        # Deep copy: the table is cached, so a caller editing a list must not change it.
        return row.model_copy(deep=True)
    return None


def problems_for(plant: str) -> list[str]:
    """The named problems with a treat row for this plant (any name), sorted."""
    key = _plant_keys().get(_norm(plant))
    return sorted({r.problem for r in load_outcomes() if r.plant == key and r.problem is not None})


def problems_in(plant: str, month: int) -> list[str]:
    """The named problems with a treat row for this plant (any name) in this month, sorted:
    what to watch for now (the wait page, 21 Oct)."""
    key = _plant_keys().get(_norm(plant))
    return sorted(
        {
            r.problem
            for r in load_outcomes()
            if r.plant == key and r.problem is not None and month in r.months
        }
    )
