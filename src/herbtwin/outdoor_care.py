"""What is normal for a plant outdoors in a given UK month, and 2 or 3 points on looking after it.

The indoor card's twin (indoor_care.py, #340). 23 Oct, Kash on a phone walk of the live site:
"Why is tips for the month on for indoor but not outdoor?" What is normal now is the season
table's own signs (seasonal.py), so a plant with no season row gets no card. The season table
says what is normal, not what to do, so the care points are a small table of ours in
data/seasonal/outdoor_care_uk.json: groups of herbs kept alike (basil, leafy herbs, herbs that
die back, woody herbs, and a herb alone where its stage differs), one row per group per run of
months, 2 or 3 points each. Facts from the RHS herb and herbs-in-containers pages, restated in
our own words, and kept to the outcome table's months for a job (data/seasonal/README.md). A
plant or month with no row of ours (a rose, a fern, basil in January) gets no card rather
than a guess. The answer drops any point that argues with its own cards (answer.py).
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from herbtwin.answer import short_sign
from herbtwin.schemas import OutdoorNow
from herbtwin.seasonal import normal_for, season_sources

OUTDOOR_PATH = Path(__file__).resolve().parents[2] / "data" / "seasonal" / "outdoor_care_uk.json"
SHOWN_NORMAL = 2  # the first signs, as the wait page shows them, so the card stays a glance
# on an outdoor card, "outdoor plant's leaves blackened" says outdoor twice
_OUTDOOR_LEAD = re.compile(r"^outdoor plant(?:'s)?\s+", re.I)
_INDOORS = re.compile(r"\bindoors?\b|\bwindowsills?\b|\bunder glass\b", re.I)
_POT = re.compile(r"\bpots?\b", re.I)


class OutdoorCare(BaseModel):
    group: str  # "basil", "leafy herbs", "herbs that die back", "woody herbs"
    plants: list[str] = Field(min_length=1)  # species keys, as the season table's
    months: list[int] = Field(min_length=1)
    tips: list[str] = Field(min_length=1, max_length=3)  # "Water: …", "Picking: …"
    # for a pot (or a container we can't see), never a bed: shelter from the rain, a feed in a pot
    pot_tips: list[str] = Field(default_factory=list, max_length=1)
    # for a bed only: what differs in the ground ("only in long dry spells" is wrong for a pot
    # in hot weather; review of this PR, from the RHS thyme and rosemary pages)
    bed_tips: list[str] = Field(default_factory=list, max_length=1)
    evidence_tier: Literal["A", "B", "C", "D"]  # tiers as in docs/reference/risk-models.md
    sources: list[str] = Field(min_length=1)


@cache
def load_outdoor(path: Path = OUTDOOR_PATH) -> tuple[OutdoorCare, ...]:
    return tuple(OutdoorCare.model_validate(e) for e in json.loads(path.read_text()))


@cache
def _index(path: Path = OUTDOOR_PATH) -> dict[tuple[str, int], OutdoorCare]:
    return {
        (name.casefold(), month): row
        for row in load_outdoor(path)
        for name in row.plants
        for month in row.months
    }


def outdoor_care_for(plant_key: str | None, month: int) -> OutdoorCare | None:
    """The row for a plant (species key, any case) in a month; no fallback."""
    row = _index().get(((plant_key or "").strip().casefold(), month))
    return row.model_copy(deep=True) if row else None


def _sign(sign: str) -> str:
    return _OUTDOOR_LEAD.sub("", short_sign(sign))


def outdoor_now(plant_key: str | None, month: int, container: str = "unknown") -> OutdoorNow | None:
    """The card for a plant outdoors in a UK month: its season signs and our row's points,
    or None without both (no season row, a houseplant's, or no row of ours). A bed has no
    pot and soil, not compost (as Keep an eye on says it: judge walk, border rosemary)."""
    row = outdoor_care_for(plant_key, month)
    norm = normal_for(plant_key, month) if plant_key else None
    if row is None or norm is None or norm.indoor:
        return None
    bed = container == "ground"
    signs = [
        _sign(s) for s in norm.normal_signs if not (_INDOORS.search(s) or (bed and _POT.search(s)))
    ][:SHOWN_NORMAL]
    said = "; ".join(s for s in signs if s)
    tips = [*row.tips, *(row.bed_tips if bed else row.pot_tips)]
    if bed:
        tips = [
            re.sub(r"\b([Cc])ompost\b", lambda m: "Soil" if m[1] == "C" else "soil", t)
            for t in tips
        ]
    return OutdoorNow(
        month=month,
        normal=f"Normal now: {said}." if said else "",
        tips=tips,
        # what is normal from the season's own sources, the points from ours, once each
        sources=list(dict.fromkeys([*season_sources(norm), *row.sources])),
    )
