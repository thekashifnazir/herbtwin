"""The RHS plant page (B5; Kash, 6 Oct): find the species' own details page and read its
growing conditions. Only that page counts, at its final address - never a cultivar, never
a redirect to another plant (a stale id redirects; B5 plan Step 0)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from herbtwin.config import Settings
from herbtwin.search import TIMEOUT_S, Provider, Tavily, TinyFish, WebSearch, is_trusted

RHS: tuple[str, ...] = ("rhs.org.uk",)
# rhs.org.uk/advice/rhs-hardiness-rating: minimum temperature ranges in degrees C, as
# (damage below, severe below). The scale is open at both ends: H1A's 12 and H7's -25 are ours.
HARDINESS_C: dict[str, tuple[float, float]] = {
    "H1A": (15.0, 12.0),
    "H1B": (15.0, 10.0),
    "H1C": (10.0, 5.0),
    "H2": (5.0, 1.0),
    "H3": (1.0, -5.0),
    "H4": (-5.0, -10.0),
    "H5": (-10.0, -15.0),
    "H6": (-15.0, -20.0),
    "H7": (-20.0, -25.0),
}


@dataclass(frozen=True)
class RhsFacts:
    hardiness: str | None
    position: str | None
    moisture: str | None
    drought_resistant: bool | None
    cultivation: str | None


def species_slug(species: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", species.lower()).strip("-")


def is_species_page(url: str, species: str) -> bool:
    slug = species_slug(species)
    if "-" not in slug or not is_trusted(url, RHS):  # a genus alone, or "unknown"
        return False
    path = urlsplit(url).path.rstrip("/")
    return re.fullmatch(rf"/plants/\d+/{re.escape(slug)}(-[a-z])?/details", path) is not None


def names_species(title: str, text: str, species: str) -> bool:
    """The page names the species itself (title before "|", or its first "# " heading),
    not a cultivar. Checked beside the address because a hosted reader may report the
    address asked for rather than where a stale id redirected (review, B5)."""
    want = " ".join(species.lower().split())
    heading = next((line[2:] for line in text.splitlines() if line.startswith("# ")), "")
    for candidate in (title.split("|")[0], heading):
        name = " ".join(re.sub(r"[*_]", "", candidate).lower().split())
        if re.fullmatch(rf"{re.escape(want)}( \([a-z]\))?", name):
            return True
    return False


def find_rhs(species: str, finder: WebSearch | None) -> tuple[str, str | None] | None:
    """The plant's RHS page, and which search found it (the page says "found with Tavily")."""
    if finder is None or "-" not in species_slug(species):
        return None
    found = finder.search(f"{species} plant")
    url = next((h.url for h in found.hits if is_species_page(h.url, species)), None)
    return (url, found.provider) if url is not None else None


def find_rhs_page(species: str, finder: WebSearch | None) -> str | None:
    found = find_rhs(species, finder)
    return found[0] if found is not None else None


def _field(text: str, name: str) -> str | None:
    m = re.search(rf"^{re.escape(name)}\s*:\s*(.+)$", text, re.M | re.I)
    return m.group(1).strip() if m else None


def _under(text: str, heading: str, line: str = r"[^:\n]+") -> str | None:
    """The first line under a markdown heading (blank lines allowed between)."""
    m = re.search(rf"^#+ {re.escape(heading)}[ \t]*\n(?:[ \t]*\n)*({line})$", text, re.M | re.I)
    return m.group(1).strip() if m else None


def parse_rhs(text: str) -> RhsFacts:
    hardiness = (_field(text, "Hardiness") or "").upper()
    ratings = ["H" + r for r in re.findall(r"\bH(1[ABC]|[2-7])\b", hardiness)]
    drought = _field(text, "Drought Resistance")
    return RhsFacts(
        hardiness=max(ratings, key=lambda r: HARDINESS_C[r][0], default=None),
        position=_field(text, "Position") or _under(text, "Position"),
        moisture=_field(text, "Moisture"),
        drought_resistant=None if drought is None else drought.lower().startswith("yes"),
        cultivation=_under(text, "Cultivation", line=r".+"),
    )


def rhs_finder_from(settings: Settings, http: httpx.Client | None = None) -> WebSearch | None:
    """TinyFish (free) then Tavily, rhs.org.uk only. Not behind the chat's search switch:
    it replaces the research stage's old always-on Tavily search."""
    client = http or httpx.Client(timeout=TIMEOUT_S)
    providers: list[Provider] = []
    if settings.tinyfish_api_key:
        providers.append(TinyFish(settings.tinyfish_api_key, client))
    if settings.tavily_key:
        providers.append(Tavily(settings.tavily_key, client))
    return WebSearch(providers, RHS) if providers else None
