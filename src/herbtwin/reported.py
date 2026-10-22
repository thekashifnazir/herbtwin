"""Seen recently in the UK, the news part (21 Oct, reworked 22 Oct): under the UK records
(sightings.py), up to two headlines from the last month that name one of this plant's own
pests or diseases, found with Tavily. Only the headline, the site, the date and a link:
never the page's own advice, and never a headline that names a pest product or a chemical
(web_how's names_a_pest_product and names_a_chemical, the main card's guards, and
shops.SOLD_AGAINST_PESTS, the shop links' own list).

Tavily is asked by pest ("rosemary beetle UK"), not by plant, over the last month
(time_range "month", filter_by_published_date: Tavily's search has no `days`, which the first
version sent). A probe on 22 Oct found dated reports for 2 of 5 pests: a Guardian country
diary on rosemary beetle (7 Oct) and Warwick Crop Centre's carrot fly monitoring (11 and
15 Oct). The RHS and GOV.UK publish almost nothing dated, so national news, the gardening
press and Warwick's pest monitoring are on the list; local news is not (no list of it to
vet). Tavily gets the pest's name, nothing about the person or the plant's place. One search
per pest a month (a miss is asked again the next day); any failure shows nothing."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import unquote, urlsplit

import httpx

from herbtwin.chat import plant_names
from herbtwin.config import Settings
from herbtwin.lookups import Lookups
from herbtwin.outcomes import problems_for
from herbtwin.schemas import AnalysisRecord
from herbtwin.search import TIMEOUT_S as SEARCH_TIMEOUT_S
from herbtwin.search import Hit, SearchFailed, Tavily
from herbtwin.shops import DAILY_SEARCHES, SOLD_AGAINST_PESTS, DailyCap
from herbtwin.sightings import SHARED_PROBLEMS, species_table, uk_today
from herbtwin.stages.web_how import names_a_chemical, names_a_pest_product

log = logging.getLogger(__name__)

# host -> (the name shown, the only paths taken there). The RHS, Defra's plant health portal
# and Forest Research; GOV.UK only as www.gov.uk (a probe on 21 Oct with "gov.uk" returned a
# parish council's news page); Warwick Crop Centre's pest monitoring, not the rest of the
# university (its PhD adverts name basil downy mildew too); BBC News, not its TV schedules
# (both came back on 22 Oct); the Guardian, BBC Gardeners' World and Horticulture Week
SITES: dict[str, tuple[str, str]] = {
    "rhs.org.uk": ("RHS", "/"),
    "planthealthportal.defra.gov.uk": ("Defra Plant Health Portal", "/"),
    "forestresearch.gov.uk": ("Forest Research", "/"),
    "www.gov.uk": ("GOV.UK", "/"),
    "warwick.ac.uk": ("Warwick Crop Centre", "/fac/sci/lifesci/wcc/"),
    "theguardian.com": ("The Guardian", "/"),
    "bbc.co.uk": ("BBC News", "/news/"),
    "gardenersworld.com": ("BBC Gardeners' World", "/"),
    "hortweek.com": ("Horticulture Week", "/"),
}
DOMAINS = tuple(SITES)
MAX_SHOWN = 2
MAX_PESTS = 3  # searches per plant; each is kept a month and shared by every plant it hits
ASKED = 10  # a basic search costs the same for 10 as for 5; most are not dated reports
WINDOW_DAYS = 31  # "this month": the window Tavily is asked for, checked again here
TIMEOUT_S = 6.0  # the page shows nothing rather than wait (the search still fills the cache)
MISSED_TTL_S = 86400.0  # nothing found: ask again tomorrow
FOUND_TTL_S = 31 * 86400.0  # found: the month's key holds it (each page re-checks the dates)
TITLE_CHARS = 120

# a site's name at the end of its headline: "Rosemary beetle / RHS Gardening"
_TAIL = re.compile(
    r"\s*[|–—/-]\s*(?:rhs\b.*|gov\.uk|uk plant health risk register|warwick crop centre|"
    r"bbc news|the guardian|gardeners'? ?world.*|horticulture week)$",
    re.I,
)


@dataclass(frozen=True)
class Report:
    title: str  # the page's own headline, without the site's name
    site: str
    date: str  # "21 Oct 2026"
    url: str


def published_on(raw: str | None) -> date | None:
    """The day a hit says it was published: Tavily's "Wed, 22 Oct 2025 00:00:00 GMT", or an
    ISO date. None when it says nothing we can read."""
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).date()
    except (TypeError, ValueError, IndexError):
        pass
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def site_of(url: object) -> str | None:
    """The site's name for an https page on one of SITES, under its paths; else None."""
    if not isinstance(url, str):
        return None
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https":
        return None
    for domain, (name, path) in SITES.items():
        if (host == domain or host.endswith("." + domain)) and parts.path.startswith(path):
            return name
    return None


def names_of(pest: str) -> tuple[str, ...]:
    """What a page may call the pest: its name, its other names and its scientific names."""
    sp = species_table().get(pest)
    return (pest, *(sp.also + sp.scientific if sp else ()))


def _mentions(names: Iterable[str], text: str) -> bool:
    alts = "|".join(re.escape(n) for n in sorted({n for n in names if n}, key=len, reverse=True))
    return bool(alts) and re.search(rf"\b(?:{alts})(?:e?s)?\b", text, re.I) is not None


def report_of(hit: Hit, pest: str, today: date) -> Report | None:
    """The report to show for this hit, or None: an https page on one of SITES, dated in the
    last WINDOW_DAYS, whose headline, address or snippet names the pest (only the headline
    is shown); never one whose headline names a pest product or a chemical."""
    site = site_of(hit.url)
    if site is None:
        return None
    when = published_on(hit.published)
    # undated: an evergreen guide, not something reported now
    if when is None or not (today - timedelta(days=WINDOW_DAYS) <= when <= today + timedelta(1)):
        return None
    title = _TAIL.sub("", " ".join(hit.title.split())).strip()
    if site == "The Guardian" and " | " in title:  # "Country diary: … | Susie White": the byline
        title = title.rsplit(" | ", 1)[0].strip()
    if not title:
        return None
    if names_a_chemical(title) or names_a_pest_product(title) or SOLD_AGAINST_PESTS.search(title):
        return None
    path = re.sub(r"[^A-Za-z0-9]+", " ", unquote(urlsplit(hit.url).path))
    if not _mentions(names_of(pest), f"{title} {path} {hit.snippet}"):
        return None
    if len(title) > TITLE_CHARS:
        title = title[:TITLE_CHARS].rsplit(" ", 1)[0].rstrip(",;:-") + "…"
    return Report(title, site, f"{when.day} {when:%b %Y}", hit.url)


def query_for(pest: str) -> str:
    """What Tavily is asked: the pest's name and the country, nothing else."""
    return f"{pest} UK"


def searched(problems: Iterable[str]) -> list[str]:
    """The plant's own pests and diseases Tavily is asked about, at most MAX_PESTS: never one
    many plants get (SHARED_PROBLEMS), as no search for it could be about this plant."""
    return sorted({p for p in problems if p.casefold() not in SHARED_PROBLEMS})[:MAX_PESTS]


@dataclass(frozen=True)
class Subject:
    plant: str  # the common name, for the logs
    problems: tuple[str, ...]  # its listed problems (outcomes.problems_for)


def subject_of(rec: AnalysisRecord) -> Subject | None:
    """The identified plant, or None when the photo named no plant we have data on."""
    _, _, key = plant_names(rec)
    if not key or rec.observation is None or not rec.observation.species:
        return None
    return Subject(rec.observation.species[0].common_name, tuple(problems_for(key)))


class CapReached(Exception):
    """The day's shared Tavily searches are used."""


class Reported:
    """One Tavily search per pest a month, kept for the month (a miss for a day)."""

    def __init__(
        self,
        tavily: Tavily,
        clock: Callable[[], float] | None = None,
        today: Callable[[], date] | None = None,
        cap: DailyCap | None = None,
    ):
        self._tavily = tavily
        self._today = today or uk_today
        self._cap = cap or DailyCap(DAILY_SEARCHES)  # shared with the shop links in the app
        self._lookups: Lookups[tuple[str, str], tuple[Hit, ...]] = Lookups(
            "reported",
            self._search,
            lambda kept: FOUND_TTL_S if kept else MISSED_TTL_S,
            clock=clock,
            workers=MAX_PESTS,
            expected=(SearchFailed, CapReached),
        )

    def reports(self, subject: Subject) -> list[Report]:
        """Up to MAX_SHOWN reports, within TIMEOUT_S; nothing on a miss or any failure."""
        today = self._today()
        keys = [(p, f"{today:%Y-%m}") for p in searched(subject.problems)]
        got = self._lookups.get_many(keys, TIMEOUT_S)
        found = [[r for h in got.get(k, ()) if (r := report_of(h, k[0], today))] for k in keys]
        out: list[Report] = []
        # each pest's first, then the rest: one pest's pages never fill the card alone
        for r in [f[0] for f in found if f] + [r for f in found for r in f[1:]]:
            if r.url in {o.url for o in out} or r.title.casefold() in {
                o.title.casefold() for o in out
            }:
                continue
            out.append(r)
        return out[:MAX_SHOWN]

    def _search(self, key: tuple[str, str]) -> tuple[Hit, ...]:
        pest, _ = key
        if not self._cap.take():
            raise CapReached(f"the day's {self._cap.limit} searches are used")
        hits = self._tavily.recent(query_for(pest), DOMAINS, ASKED)
        today = self._today()
        # kept as hits, so each page re-checks the dates against its own day
        return tuple(h for h in hits if report_of(h, pest, today))


def reported_from(
    settings: Settings, http: httpx.Client | None = None, cap: DailyCap | None = None
) -> Reported | None:
    """The finder when Tavily is on (HERBTWIN_TAVILY_ENABLED and a key), else None."""
    if not settings.tavily_key:
        return None
    client = http or httpx.Client(timeout=SEARCH_TIMEOUT_S)
    return Reported(Tavily(settings.tavily_key, client), cap=cap)
