"""Local help (21 Oct, Kash): for someone who typed a UK town or postcode, two or three pages
that list gardeners in that town, found with Tavily on known directories. Each must be that
directory's page for this town (a probe on 21 Oct found US and other towns' pages in the
same results). Plus the RHS's own advice on hiring one, which is the same for everyone."""

from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

import httpx

from herbtwin.config import Settings
from herbtwin.schemas import Location
from herbtwin.search import TIMEOUT_S as SEARCH_TIMEOUT_S
from herbtwin.search import SearchFailed, Tavily, is_trusted
from herbtwin.shops import DAILY_SEARCHES, DailyCap
from herbtwin.where import in_uk

log = logging.getLogger(__name__)

# domain -> the name shown, and what its page for a UK town looks like ({town}: the slug)
DIRECTORIES: dict[str, tuple[str, str]] = {
    "checkatrade.com": ("Checkatrade", r"/search/gardener/in/{town}(?:$|[/?#])"),
    "bark.com": ("Bark", r"/en/gb/gardeners/{town}(?:$|[/?#])"),
    "yell.com": ("Yell", r"/s/gardeners-{town}\.html"),
    "taskrabbit.co.uk": ("TaskRabbit", r"/locations/{town}/"),
    "mybuilder.com": ("MyBuilder", r"/gardening-landscaping/[\w-]+/{town}(?:$|[/?#])"),
}
DOMAINS = tuple(DIRECTORIES)
MAX_LINKS = 3
RHS_HIRING = "https://www.rhs.org.uk/garden-design/hiring-gardeners-contractors"

FOUND_TTL_S = 7 * 86400.0
MISSED_TTL_S = 86400.0
FAILED_TTL_S = 300.0
TIMEOUT_S = 6.0  # the page shows nothing rather than wait (the search still fills the cache)


@dataclass(frozen=True)
class HelpLink:
    name: str  # the directory
    url: str


def centres_near(town: str) -> str:
    """A map search for garden centres near the town the person typed: a link they open, so
    nothing goes to the map until they tap it (21 Oct, Kash: "get people to go to local
    garden centres")."""
    return "https://www.google.com/maps/search/?api=1&query=" + quote(
        f"garden centres near {town}, UK"
    )


def town_of(location: Location | None) -> str | None:
    """The town the person typed, as the place lookup named it ("Bristol, GB" -> "Bristol"),
    when it is in the UK. A photo's own GPS or the device's place is never sent anywhere."""
    if location is None or location.source != "typed" or not in_uk(location.lat, location.lon):
        return None
    if not location.label.endswith(", GB"):  # in_uk's box takes in Ireland too
        return None
    town = location.label.removesuffix(", GB").strip()
    # a postcode's district: "Bristol, City of", "Herefordshire, County of"
    town = re.sub(r",\s*(?:city|county) of$|^(?:city|county) of\s+", "", town, flags=re.I)
    # a half postcode ("LE1") names no town a directory lists
    if not re.fullmatch(r"[A-Za-z][A-Za-z' .-]{1,40}", town):
        return None
    return town


def _slug(town: str) -> str:
    return "-".join(re.findall(r"[a-z]+", town.lower().replace("'", "")))


def town_page(url: str, town: str) -> str | None:
    """The directory's name when this is its page for this town, else None."""
    if not is_trusted(url, DOMAINS):
        return None
    host = (urlsplit(url).hostname or "").lower()
    domain = next(d for d in DOMAINS if host == d or host.endswith("." + d))
    name, pattern = DIRECTORIES[domain]
    path = urlsplit(url).path.lower()
    return name if re.search(pattern.format(town=re.escape(_slug(town))), path) else None


class LocalHelp:
    """One Tavily search per town, kept for a week (a miss for a day)."""

    def __init__(self, tavily: Tavily, clock=None, cap: DailyCap | None = None):
        self._tavily, self._clock = tavily, clock or time.monotonic
        self._cap = cap or DailyCap(DAILY_SEARCHES)  # shared with the shop links in the app
        # town -> (when, what was found, how long it holds)
        self._cache: dict[str, tuple[float, tuple[HelpLink, ...], float]] = {}
        # re-entrant: a search already done runs its done-callback at once, inside the lock
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="local-help")
        self._running: dict[str, Future] = {}

    def links(self, town: str) -> list[HelpLink]:
        key = _slug(town)
        with self._lock:
            hit = self._cache.get(key)
        if hit is not None:
            at, found, ttl = hit
            if self._clock() - at < ttl:
                return list(found)
        # one search per town at a time: a page for a town already being looked up waits
        # on that search, never starts another (a hanging Tavily must not stack paid calls)
        with self._lock:
            job = self._running.get(key)
            if job is None:
                job = self._pool.submit(self._search, town, key)
                self._running[key] = job
                job.add_done_callback(lambda _, k=key: self._done(k))
        try:  # within TIMEOUT_S; a slower search still lands in the cache for the next page
            return list(job.result(timeout=TIMEOUT_S))
        except FutureTimeout:
            job.cancel()  # not started yet: it never runs for a page that has gone
            log.info("local help search slower than %.0f s", TIMEOUT_S)
            return []

    def _done(self, key: str) -> None:
        with self._lock:
            self._running.pop(key, None)

    def _search(self, town: str, key: str) -> list[HelpLink]:
        if not self._cap.take():
            log.info("local help: the day's %d searches are used", self._cap.limit)
            return []
        try:
            hits = self._tavily.search(f"gardener in {town}", DOMAINS, 8)
        except SearchFailed as e:
            log.info("local help search failed: %s", e)
            hits = None
        except Exception:  # noqa: BLE001 - local help is extra: never a reason to fail
            log.exception("local help search broke")
            hits = None
        if hits is None:  # an outage: one call per town per 5 minutes
            with self._lock:
                self._cache[key] = (self._clock(), (), FAILED_TTL_S)
            return []
        found: list[HelpLink] = []
        for h in hits:
            name = town_page(h.url, town)
            if name is not None and name not in {x.name for x in found}:
                found.append(HelpLink(name, h.url))
        found = found[:MAX_LINKS]
        with self._lock:
            self._cache[key] = (self._clock(), tuple(found), FOUND_TTL_S if found else MISSED_TTL_S)
        return found


def local_help_from(
    settings: Settings, http: httpx.Client | None = None, cap: DailyCap | None = None
) -> LocalHelp | None:
    """The finder when HERBTWIN_LOCAL_HELP and Tavily are both on, else None."""
    if not settings.local_help or not settings.tavily_key:
        return None
    client = http or httpx.Client(timeout=SEARCH_TIMEOUT_S)
    return LocalHelp(Tavily(settings.tavily_key, client), cap=cap)
