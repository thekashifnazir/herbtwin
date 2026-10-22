"""Seen recently in the UK (22 Oct): how many UK records of this plant's pests and diseases
GBIF holds from the last 60 days, and the latest one's date, from open-licence datasets only
(CC0 and CC BY 4.0; never CC BY-NC). Each line links to the same search on GBIF.org, which
lists every record and who made it (the CC BY attribution).

GBIF gets a species key, the country (GB) and the date range: never the person or where
they are. The counts are UK-wide, not near you. One lookup per species a day; a failure
shows nothing and is asked again in 5 minutes. GBIF's records lag the field by a few weeks
(a probe on 22 Oct: the latest rosemary beetle record was 3 Oct), hence 60 days, not 30."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx

from herbtwin.config import Settings
from herbtwin.lookups import Lookups

log = logging.getLogger(__name__)

TABLE = Path(__file__).resolve().parents[2] / "data" / "outcomes" / "pest_species_gbif.json"
GBIF_SEARCH = "https://api.gbif.org/v1/occurrence/search"
GBIF_PAGE = "https://www.gbif.org/occurrence/search"
COUNTRY = "GB"  # UK-wide: never the person's place
# open licences only: GBIF's names for CC0 1.0 and CC BY 4.0 (CC BY-NC records are left out)
LICENCES = ("CC0_1_0", "CC_BY_4_0")
WINDOW_DAYS = 60
MAX_SHOWN = 3
HTTP_TIMEOUT_S = 4.0  # one GBIF call
TIMEOUT_S = 5.0  # the page waits this long for them all (the rest still fill the cache)
DAY_S = 86400.0
UK = ZoneInfo("Europe/London")
# listed problems that many plants get ("cuckoo spit", "vine weevil"): their records are
# shown after the plant's own pests', and never searched for news (reported.py)
SHARED_PROBLEMS = frozenset(
    "aphids|capsid bugs|coral spot|cuckoo spit|fungus gnats|grey mould|mealybugs|powdery mildew|root rot|"
    "rust|scale insects|slugs and snails|spider mites|thrips|vine weevil|whitefly".split("|")
)


def uk_today() -> date:
    return datetime.now(UK).date()


@dataclass(frozen=True)
class Species:
    problem: str  # the problem's name in problem_signs_uk.json
    shown: str  # "Rosemary beetle"
    scientific: tuple[str, ...]
    keys: tuple[int, ...]  # GBIF backbone keys: a key's search includes its synonyms
    also: tuple[str, ...] = ()  # other names a headline may use ("Ligurian leafhopper")


@dataclass(frozen=True)
class Sighting:
    problem: str
    shown: str
    scientific: str  # "Chrysolina americana"
    count: int
    latest: date | None
    url: str  # the same search on GBIF.org

    @property
    def text(self) -> str:
        """ "Rosemary beetle: 51 UK records in the last 60 days, latest 3 Oct 2026"."""
        records = "1 UK record" if self.count == 1 else f"{self.count:,} UK records"
        said = f"{self.shown}: {records} in the last {WINDOW_DAYS} days"
        if self.latest is not None:
            said += f", latest {self.latest.day} {self.latest:%b %Y}"
        return said


@lru_cache(maxsize=1)
def species_table() -> dict[str, Species]:
    raw = json.loads(TABLE.read_text(encoding="utf-8"))["species"]
    return {
        problem: Species(
            problem,
            row["shown"],
            tuple(row["scientific"]),
            tuple(row["gbif"]),
            tuple(row.get("also", ())),
        )
        for problem, row in raw.items()
    }


def window(today: date) -> tuple[date, date]:
    return today - timedelta(days=WINDOW_DAYS), today


def gbif_params(sp: Species, today: date) -> list[tuple[str, str]]:
    """What GBIF is asked: the species, GB, the last 60 days, open licences only; no records,
    just the count and each record's date (a facet), for the latest."""
    start, end = window(today)
    return [
        *(("taxonKey", str(k)) for k in sp.keys),
        ("country", COUNTRY),
        ("eventDate", f"{start.isoformat()},{end.isoformat()}"),
        *(("license", lic) for lic in LICENCES),
        ("limit", "0"),
        ("facet", "eventDate"),
        ("facetLimit", "1000"),
    ]


def gbif_link(sp: Species, today: date) -> str:
    """The same search on GBIF.org, where each record and its maker are listed."""
    start, end = window(today)
    return f"{GBIF_PAGE}?" + urlencode(
        [
            *(("taxon_key", str(k)) for k in sp.keys),
            ("country", COUNTRY),
            ("event_date", f"{start.isoformat()},{end.isoformat()}"),
            *(("license", lic) for lic in LICENCES),
        ]
    )


def parse(data: object, today: date) -> tuple[int, date | None]:
    """(the count, the latest record's day) from GBIF's reply; ValueError on an odd one."""
    if not isinstance(data, dict) or not isinstance(data.get("count"), int):
        raise ValueError("no count in GBIF's reply")
    days: list[date] = []
    facets = [f for f in data.get("facets") or [] if isinstance(f, dict)]
    for row in (r for f in facets for r in f.get("counts") or []):
        name = row.get("name") if isinstance(row, dict) else None
        try:
            day = date.fromisoformat(str(name)[:10])
        except ValueError:
            continue
        if day <= today:  # a mistyped future date is never "latest"
            days.append(day)
    return max(data["count"], 0), max(days, default=None)


class Sightings:
    """UK records of a plant's listed pests and diseases, one GBIF call per species a day."""

    def __init__(
        self,
        http: httpx.Client,
        today: Callable[[], date] | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self._http, self._today = http, today or uk_today
        self._lookups: Lookups[tuple[str, date], Sighting | None] = Lookups(
            "sightings",
            self._fetch,
            lambda _: DAY_S,  # the key carries the day: a new day asks again
            clock=clock,
            expected=(httpx.HTTPError, ValueError),
        )

    def seen(self, problems: Iterable[str]) -> list[Sighting]:
        """Up to MAX_SHOWN: the plant's own pests first, then those many plants get, the most
        recorded first in each; a species with no records is left out, and so is one whose
        lookup failed or ran past TIMEOUT_S."""
        table, today = species_table(), self._today()
        keys = [(p, today) for p in dict.fromkeys(problems) if p in table]
        got = self._lookups.get_many(keys, TIMEOUT_S).values()
        shown = sorted(
            (s for s in got if s is not None),
            key=lambda s: (s.problem in SHARED_PROBLEMS, -s.count, s.shown),
        )
        return shown[:MAX_SHOWN]

    def _fetch(self, key: tuple[str, date]) -> Sighting | None:
        problem, today = key
        sp = species_table()[problem]
        r = self._http.get(GBIF_SEARCH, params=gbif_params(sp, today), timeout=HTTP_TIMEOUT_S)
        r.raise_for_status()
        count, latest = parse(r.json(), today)
        if count == 0:
            return None
        scientific = " and ".join(sp.scientific)
        return Sighting(problem, sp.shown, scientific, count, latest, gbif_link(sp, today))


def sightings_from(settings: Settings, http: httpx.Client | None = None) -> Sightings | None:
    """On unless HERBTWIN_SIGHTINGS is 0: GBIF is free and needs no key."""
    if not settings.sightings:
        return None
    return Sightings(http or httpx.Client(timeout=HTTP_TIMEOUT_S))
