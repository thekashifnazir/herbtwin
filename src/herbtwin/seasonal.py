"""What is normal for a plant in a given UK month: literature-backed seasonal norms.

The table lives in data/seasonal/norms_uk.json, one entry per plant per month. It lets the
app say "leave it, this is normal for the time of year" (mint dead to the rhizome in
October) and name the signs that would NOT be normal now.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

SeasonalStatus = Literal[
    "active_growth",
    "flowering",
    "bolting_risk",
    "normal_dieback",
    "dormant",
    "regrowth",
    "leaf_fall",
    "evergreen_hold",
]

# a source about a pest or disease backs an entry's problem signs, never what is normal now
# (22 Oct site walk: "Season in October: dying back, from RHS, our care notes, Frontiers,
# AHDB, UF/IFAS, UConn" cited mildew papers for a season fact): the RHS's pest, disease and
# problem pages, and the other problem papers the table cites by name
_PROBLEM_PAGE = re.compile(r"rhs\.org\.uk/(?:biodiversity|disease|problems)/")
PROBLEM_PAPERS = frozenset(
    {
        "https://www.frontiersin.org/journals/plant-science/articles/10.3389/fpls.2023.1237577/pdf",
        "https://archive.ahdb.org.uk/pe-024a-improving-knowledge-and-control-of-downy-mildew-in-protected-and-outdoor-crops",
        "https://ask.ifas.ufl.edu/publication/PP271",
        "https://homegarden.cahnr.uconn.edu/factsheets/basil-downy-mildew",
        "https://en.wikipedia.org/w/index.php?title=Puccinia_menthae&oldid=1224542185",
        "https://hgic.clemson.edu/factsheet/rose-diseases/",
    }
)
NORMS_PATH = Path(__file__).resolve().parents[2] / "data" / "seasonal" / "norms_uk.json"


class SeasonalNorm(BaseModel):
    plant: str  # key: lower-case scientific name, e.g. "mentha spicata"
    common_names: list[str]
    region: Literal["UK"]
    month: int = Field(ge=1, le=12)
    status: list[SeasonalStatus] = Field(min_length=1)  # what is happening now
    normal_signs: list[str]  # looks bad but is normal now
    problem_signs: list[str]  # would NOT be normal now
    next_change: str  # plain words: "new shoots from the underground stems in March to April"
    next_change_month: int | None = Field(default=None, ge=1, le=12)
    indoor: bool = False  # houseplant entry: no frost, room conditions
    evidence_tier: Literal["A", "B", "C", "D"]  # tiers as in docs/reference/risk-models.md
    sources: list[str] = Field(min_length=1)  # URLs or doc refs


@cache
def load_norms(path: Path = NORMS_PATH) -> tuple[SeasonalNorm, ...]:
    return tuple(SeasonalNorm.model_validate(e) for e in json.loads(path.read_text()))


@cache
def _index(path: Path = NORMS_PATH) -> dict[tuple[str, int], SeasonalNorm]:
    index: dict[tuple[str, int], SeasonalNorm] = {}
    for norm in load_norms(path):
        for name in (norm.plant, *norm.common_names):
            index[(name.casefold(), norm.month)] = norm
    return index


def normal_for(plant: str, month: int, region: str = "UK") -> SeasonalNorm | None:
    """The norm for a plant (scientific or common name, any case) in a month, or None."""
    if region.strip().upper() != "UK":
        return None
    norm = _index().get((plant.strip().casefold(), month))
    # Deep copy: the index is cached, so a caller editing a list must not change later lookups.
    return norm.model_copy(deep=True) if norm else None


def season_sources(norm: SeasonalNorm) -> list[str]:
    """The sources behind what is normal now (the season line's "from ..."): the entry's
    own, less the pest and disease pages behind its problem signs."""
    return [s for s in norm.sources if not (_PROBLEM_PAGE.search(s) or s in PROBLEM_PAPERS)]


def plants() -> list[str]:
    return sorted({norm.plant for norm in load_norms()})
