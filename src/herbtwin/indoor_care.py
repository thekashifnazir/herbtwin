"""What is normal for a plant indoors in a given UK month, and how to look after it then.

The outdoor season (seasonal.py) and the forecast don't apply on a windowsill, so an indoor
answer had little beyond its main card (21 Oct, a gardener's test: indoor "doesn't have much
info"). The table in data/seasonal/indoor_care_uk.json covers groups of plants that are kept
alike (soft herbs, woody herbs, leafy houseplants, succulents, the orchid, the Christmas
cactus) and a fallback for any other indoor plant: one row per group per run of months, with
the month's normal state, 3 to 5 care tips and at most one Also-do card. Facts from RHS and
university extension pages, restated in our own words (data/seasonal/README.md).
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from herbtwin.schemas import CareAction

INDOOR_PATH = Path(__file__).resolve().parents[2] / "data" / "seasonal" / "indoor_care_uk.json"
FALLBACK = "any indoor plant"


class IndoorCare(BaseModel):
    group: str  # "soft herbs", "succulents", ...; FALLBACK has no plants
    plants: list[str]  # species keys, as the season table's (species.match_species)
    months: list[int] = Field(min_length=1)
    normal: str  # what is normal indoors in these months, one sentence
    tips: list[str] = Field(min_length=3, max_length=5)  # light, water, air, warmth, repot/feed
    also_do: CareAction | None = None  # the months' one job, as an Also-do card
    because: str | None = None  # the card's reason
    if_you_do: str | None = None  # the card's "what to expect"
    evidence_tier: Literal["A", "B", "C", "D"]  # tiers as in docs/reference/risk-models.md
    sources: list[str] = Field(min_length=1)


@cache
def load_indoor(path: Path = INDOOR_PATH) -> tuple[IndoorCare, ...]:
    return tuple(IndoorCare.model_validate(e) for e in json.loads(path.read_text()))


@cache
def _index(path: Path = INDOOR_PATH) -> dict[tuple[str, int], IndoorCare]:
    index: dict[tuple[str, int], IndoorCare] = {}
    for row in load_indoor(path):
        for name in row.plants or [FALLBACK]:
            for month in row.months:
                index[(name.casefold(), month)] = row
    return index


def indoor_care_for(plant_key: str | None, month: int) -> IndoorCare | None:
    """The row for a plant (species key, any case) in a month, else the any-plant row."""
    index = _index()
    row = index.get(((plant_key or "").strip().casefold(), month)) or index.get((FALLBACK, month))
    # Deep copy: the index is cached, so a caller editing a list must not change later lookups.
    return row.model_copy(deep=True) if row else None
