"""Web search for the follow-up chat (spec section 6, D42; Kash's chain of 6 Oct): Tavily,
then Exa, then TinyFish, then none. Off unless HERBTWIN_SEARCH_ENABLED is set and a key is present. Only
trusted gardening sites; every result is data, its fence runs removed. Plain httpx, as
research.py and the Supabase store."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from herbtwin.advice_context import FENCE_RUN
from herbtwin.config import Settings

log = logging.getLogger(__name__)
TAVILY_SEARCH_URL = "https://api.tavily.com/search"
TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"
EXA_SEARCH_URL = "https://api.exa.ai/search"
TINYFISH_SEARCH_URL = "https://api.search.tinyfish.ai"
TIMEOUT_S = 15.0
MAX_HITS = 5
# asked for more than a reply cites, so UK pages can come first and pages about another plant
# can be left out with enough to spare (19 Oct live: a basil downy mildew search's top 5 were
# all general mildew pages, while 6th-8th named basil). A Tavily basic search costs the
# same for 8 as for 5; Exa bills its highlights per page, about $0.003 more
ASKED = 8
MAX_QUERY = 200
SNIPPET_CHARS = 600
TITLE_CHARS = 200
UNAVAILABLE = "search is not available right now"
# Kash, 6 Oct: chat search limited to trusted sites (RHS etc.)
TRUSTED = (
    "rhs.org.uk",
    "kew.org",
    "gardenersworld.com",
    "missouribotanicalgarden.org",
    "extension.umn.edu",
    "extension.psu.edu",
    # added by Kash, 6 Oct
    "plants.ces.ncsu.edu",  # NC State plant toolbox: hardiness, light, soil per plant
    "ipm.ucanr.edu",  # UC pest guides
    "extension.illinois.edu",
    "gardenorganic.org.uk",  # UK organic pest control and soil
    "rbge.org.uk",  # Royal Botanic Garden Edinburgh
    "herbsociety.org.uk",
    "planthealthportal.defra.gov.uk",  # UK pest and disease alerts
    "pfaf.org",
)
# UK gardening sites, listed first (19 Oct judge walk: "Will frost hurt the peas this week?"
# for London cited an Illinois frost page, and RHS answers sat under US extension pages)
UK_SITES = (
    "rhs.org.uk",
    "kew.org",
    "gardenersworld.com",
    "gardenorganic.org.uk",
    "rbge.org.uk",
    "herbsociety.org.uk",
    "planthealthportal.defra.gov.uk",
    "pfaf.org",
)


@dataclass(frozen=True)
class Hit:
    title: str
    url: str
    snippet: str  # one line: the page's line breaks are spaces here
    # the same text line by line (the trusted-page check: a heading or a list line with no
    # full stop must never run into the next sentence, seen live 19 Oct)
    lines: tuple[str, ...] = ()
    # when the provider says the page was published (Tavily's news search: "Wed, 22 Oct 2025
    # 00:00:00 GMT"); None when it does not say
    published: str | None = None


@dataclass(frozen=True)
class Found:
    hits: list[Hit]
    provider: str | None  # who answered; None when no provider could
    note: str | None  # plain words when there is nothing to show


class SearchFailed(Exception):
    """One provider could not answer; the chain moves on."""


class Provider(Protocol):
    name: str

    def search(self, query: str, domains: tuple[str, ...], n: int) -> list[Hit]: ...


def _clean(text: object, limit: int) -> str:
    s = " ".join(str(text or "").split())
    while FENCE_RUN.search(s):
        s = FENCE_RUN.sub("", s)
    return s[:limit]


def _lines(text: object, limit: int) -> tuple[str, ...]:
    """The text's non-empty lines, each cleaned as a snippet is, within the snippet's
    length."""
    out: list[str] = []
    left = limit
    for raw in str(text or "").splitlines():
        line = _clean(raw, left)
        if line and left > 0:
            out.append(line)
            left -= len(line) + 1
    return tuple(out)


def is_trusted(url: object, domains: tuple[str, ...]) -> bool:
    if not isinstance(url, str):
        return False
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host == d or host.endswith("." + d) for d in domains)


def uk_first(hits: list[Hit]) -> list[Hit]:
    """UK sites first, each group in the provider's own order."""
    return sorted(hits, key=lambda h: not is_trusted(h.url, UK_SITES))


def request_json(
    http: httpx.Client,
    method: str,
    url: str,
    headers: dict,
    *,
    body: dict | None = None,
    params: dict | None = None,
) -> dict:
    try:
        r = http.request(method, url, headers=headers, json=body, params=params, timeout=TIMEOUT_S)
    except httpx.HTTPError as e:
        raise SearchFailed(type(e).__name__) from e
    if r.status_code >= 400:
        raise SearchFailed(f"HTTP {r.status_code}")
    try:
        data = r.json()
    except ValueError as e:
        raise SearchFailed("reply was not JSON") from e
    if not isinstance(data, dict):
        raise SearchFailed("reply was not a JSON object")
    return data


def _hits(
    rows: object, domains: tuple[str, ...], snippet_of: Callable[[dict], object]
) -> list[Hit]:
    out = []
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, dict) and is_trusted(r.get("url"), domains):
            title, snippet = (
                _clean(r.get("title"), TITLE_CHARS),
                _clean(snippet_of(r), SNIPPET_CHARS),
            )
            published = r.get("published_date")
            out.append(
                Hit(
                    title,
                    r["url"],
                    snippet,
                    _lines(snippet_of(r), SNIPPET_CHARS),
                    _clean(published, 40) if isinstance(published, str) else None,
                )
            )
    return out


@dataclass
class Tavily:
    key: str
    http: httpx.Client
    name: str = "tavily"

    def search(self, query: str, domains: tuple[str, ...], n: int) -> list[Hit]:
        data = request_json(
            self.http,
            "POST",
            TAVILY_SEARCH_URL,
            {"Authorization": f"Bearer {self.key}"},
            body={
                "query": query,
                "max_results": n,
                "include_domains": list(domains),
                "search_depth": "basic",
            },
        )
        return _hits(data.get("results"), domains, lambda r: r.get("content"))

    def extract(self, urls: list[str], domains: tuple[str, ...]) -> dict[str, str]:
        """Whole pages as markdown, for the trusted-page check (round 8): one call, 1
        credit per 5 pages; only trusted pages asked, only trusted pages kept."""
        asked = [u for u in urls if is_trusted(u, domains)][:5]
        if not asked:
            return {}
        data = request_json(
            self.http,
            "POST",
            TAVILY_EXTRACT_URL,
            {"Authorization": f"Bearer {self.key}"},
            body={"urls": asked, "format": "markdown", "extract_depth": "basic"},
        )
        return {
            r["url"]: r["raw_content"]
            for r in data.get("results") or []
            if isinstance(r, dict)
            and r.get("url") in asked
            and isinstance(r.get("raw_content"), str)
        }

    def recent(self, query: str, domains: tuple[str, ...], n: int) -> list[Hit]:
        """Tavily's search over the last month, each hit with the day it was published
        (Seen recently in the UK, reported.py). Tavily has no `days`: the window is
        time_range "month", and filter_by_published_date drops pages outside it (and adds
        their dates). The domains are preferred, not required (the 22 Oct probe ran so);
        _hits keeps only theirs, and the caller checks each date itself."""
        data = request_json(
            self.http,
            "POST",
            TAVILY_SEARCH_URL,
            {"Authorization": f"Bearer {self.key}"},
            body={
                "query": query,
                "max_results": n,
                "search_depth": "basic",
                "topic": "general",
                "time_range": "month",
                "filter_by_published_date": True,
                "include_domains": list(domains),
                "include_domains_mode": "prefer",
            },
        )
        return _hits(data.get("results"), domains, lambda r: r.get("content"))


def _highlights(r: dict) -> object:
    parts = [h for h in r.get("highlights") or [] if isinstance(h, str)]
    return " … ".join(parts) or r.get("text")


@dataclass
class Exa:
    key: str
    http: httpx.Client
    name: str = "exa"

    def search(self, query: str, domains: tuple[str, ...], n: int) -> list[Hit]:
        data = request_json(
            self.http,
            "POST",
            EXA_SEARCH_URL,
            {"x-api-key": self.key},
            body={
                "query": query,
                "numResults": n,
                "type": "auto",
                "includeDomains": list(domains),
                "contents": {"highlights": {"maxCharacters": SNIPPET_CHARS}},
            },
        )
        return _hits(data.get("results"), domains, _highlights)


def _sites(domains: tuple[str, ...]) -> str:
    ors = " OR ".join(f"site:{d}" for d in domains)
    return ors if len(domains) == 1 else f"({ors})"


@dataclass
class TinyFish:
    """Free at any balance (vendor, May 2026). No domain parameter: site: filters go in the
    query, and every hit is re-checked like the others."""

    key: str
    http: httpx.Client
    name: str = "tinyfish"

    def search(self, query: str, domains: tuple[str, ...], n: int) -> list[Hit]:
        data = request_json(
            self.http,
            "GET",
            TINYFISH_SEARCH_URL,
            {"X-API-Key": self.key},
            params={"query": f"{query} {_sites(domains)}"},
        )
        return _hits(data.get("results"), domains, lambda r: r.get("snippet"))[:n]


@dataclass
class WebSearch:
    providers: list[Provider]
    domains: tuple[str, ...] = field(default=TRUSTED)

    @property
    def names(self) -> list[str]:
        return [p.name for p in self.providers]

    def search(self, query: str) -> Found:
        q = " ".join(query.split())[:MAX_QUERY]
        if not q:
            return Found([], None, "empty query")
        for p in self.providers:
            try:
                hits = uk_first(p.search(q, self.domains, ASKED))
            except SearchFailed as e:
                log.warning("search provider %s failed: %s", p.name, e)
                continue
            except Exception:  # noqa: BLE001 - a provider's odd reply must not break the chat
                log.exception("search provider %s broke", p.name)
                continue
            # all ASKED: each caller keeps the ones about its plant, then its own few
            return Found(hits[:ASKED], p.name, None if hits else "nothing found on trusted sites")
        return Found([], None, UNAVAILABLE)

    def extract(self, urls: list[str]) -> dict[str, str]:
        """Whole trusted pages from the first provider that reads them (Tavily); {} when
        none can."""
        for p in self.providers:
            if hasattr(p, "extract"):
                return p.extract(urls, self.domains)
        return {}


def web_search_from(settings: Settings, http: httpx.Client | None = None) -> WebSearch | None:
    """The chain from settings: None when the switch is off or no key is set."""
    if not settings.search_enabled:
        return None
    client = http or httpx.Client(timeout=TIMEOUT_S)
    providers: list[Provider] = []
    if settings.tavily_key:
        providers.append(Tavily(settings.tavily_key, client))
    if settings.exa_api_key:
        providers.append(Exa(settings.exa_api_key, client))
    if settings.tinyfish_api_key:
        providers.append(TinyFish(settings.tinyfish_api_key, client))
    return WebSearch(providers) if providers else None
