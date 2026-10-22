"""The UK crop calendar as the grow engine reads it (spot spec section 7, D72): 155
edibles with sow, plant and harvest months, container, sun, soil and hardiness facts, and
each row's sources. Built by scripts/build_crop_calendar.py into
data/crop_calendar/calendar.json (tracked: facts and links only, no source prose). A
missing file gives no crops: the grow list then says the calendar is not available."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

log = logging.getLogger(__name__)

CALENDAR_PATH = Path(__file__).resolve().parents[2] / "data" / "crop_calendar" / "calendar.json"
# minimum temperature each RHS hardiness rating survives (RHS hardiness ratings)
RATING_MIN_C = {
    "H1a": 15.0,
    "H1b": 10.0,
    "H1c": 5.0,
    "H2": 1.0,
    "H3": -5.0,
    "H4": -10.0,
    "H5": -15.0,
    "H6": -20.0,
    "H7": -40.0,
}
RATINGS = tuple(RATING_MIN_C)
SOURCE_NAMES = {
    "rhs_raw": "RHS",
    "garden_organic": "Garden Organic",
    "real_seeds": "Real Seeds",
    "gardeners_world": "Gardeners' World",
}


@dataclass(frozen=True)
class Crop:
    id: str
    name: str
    group: str
    perennial: bool  # grown as a perennial: the first harvest is a year or more away
    sow_indoors: frozenset[int]
    sow_outdoors: frozenset[int]
    plant_out: frozenset[int]
    harvest: frozenset[int]
    rating: str | None  # RHS H-rating
    frost_tender: bool
    ground_only: bool
    min_litres: float | None
    min_depth_cm: float | None
    sun: str  # full, full_or_part, part_or_shade
    clay_ok: bool | None
    needs_drainage: bool | None
    ph: str | None  # acid_required, ..., any
    overwinters: str  # y, n, with_protection
    mild_months: dict[str, frozenset[int]]
    days_to_harvest: int | None
    evidence_tier: str  # C or D
    sources: tuple[str, ...]
    # each cross-check source's pooled windows: name -> {"sow": months, "plant_out": months}
    windows_by_source: dict[str, dict[str, frozenset[int]]] = field(default_factory=dict)
    cross_checks: int = 0  # independent calendars that cover the crop: a proxy for "common"
    spreads: bool = False  # the sources say it spreads or is invasive in open ground
    # its Latin names, lower case, for matching a photo read to it: "mentha" for "Mentha
    # spp.", both for "Matricaria chamomilla / Chamaemelum nobile" (22 Oct, the chat)
    latin: tuple[str, ...] = ()

    def rating_in_pot(self) -> str | None:
        """One rating less hardy in a container (RHS: pots get colder)."""
        if self.rating is None or self.rating not in RATINGS:
            return self.rating
        return RATINGS[max(0, RATINGS.index(self.rating) - 1)]


def _pooled(src: dict) -> dict[str, frozenset[int]]:
    """A source's month lists pooled as the calendar build compares them: indoor and
    outdoor sowing together; RHS "Plant" with "Plant out"."""
    out: dict[str, frozenset[int]] = {}
    for window, keys in (
        ("sow", ("sow_indoors", "sow_outdoors", "sow")),
        ("plant_out", ("plant_out", "plant")),
    ):
        lists = [src[k] for k in keys if isinstance(src.get(k), list)]
        if lists:
            out[window] = frozenset().union(*lists)
    return out


def _spreads(r: dict) -> bool:
    """The calendar's own notes say so: "to stop it spreading", "very invasive in open
    ground", "Spreads readily" (RHS wording)."""
    said = " ".join(str(x.get("note") or "") for x in (r["container"], r["soil"]))
    said = f"{said} {r.get('notes') or ''}".lower()
    return "spread" in said or "invasive" in said


def _latin(name: str) -> tuple[str, ...]:
    """Each whole Latin name, less "spp."; an abbreviated one ("R. scutatus") is left out."""
    out = []
    for part in name.split("/"):
        words = part.lower().replace("spp.", "").split()
        if words and not words[0].endswith("."):
            out.append(" ".join(words))
    return tuple(out)


def crop_of(r: dict) -> Crop:
    c, s, d = r["container"], r["soil"], r.get("days_to_harvest") or {}
    return Crop(
        id=r["id"],
        name=r["common_name"],
        group=r["group"],
        perennial=r["grown_as"] == "perennial",
        sow_indoors=frozenset(r["sow_indoors"]),
        sow_outdoors=frozenset(r["sow_outdoors"]),
        plant_out=frozenset(r["plant_out"]),
        harvest=frozenset(r["harvest"]),
        rating=r["hardiness_rhs"],
        frost_tender=bool(r.get("frost_tender")),
        ground_only=bool(c["ground_only"]),
        min_litres=c["min_litres"],
        min_depth_cm=c["min_depth_cm"],
        sun=r["sun"],
        clay_ok=s["clay_ok"],
        needs_drainage=s["needs_drainage"],
        ph=s["ph"],
        overwinters=r["overwinters_outdoors"],
        mild_months={k: frozenset(v) for k, v in (r.get("mild_months") or {}).items()},
        days_to_harvest=d.get("min"),
        evidence_tier=r["evidence_tier"],
        sources=tuple(x["url"] for x in r["sources"]),
        cross_checks=len(r.get("cross_checks") or {}),
        spreads=_spreads(r),
        latin=_latin(r.get("scientific_name") or ""),
        windows_by_source={
            name: _pooled(v)
            for name, v in (r.get("cross_checks") or {}).items()
            if isinstance(v, dict)
        },
    )


@cache
def load_calendar(path: Path = CALENDAR_PATH) -> tuple[Crop, ...]:
    try:
        return tuple(crop_of(r) for r in json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        log.warning("crop calendar missing: %s", path.name)
    except (OSError, ValueError, KeyError, TypeError):
        log.exception("crop calendar unreadable: %s", path.name)
    return ()
