"""Where to get it (21 Oct, Kash: "we can use tavily for the product links"): for the
answer's actions, a few kinds of thing to buy, each with a page found with Tavily on a
known UK garden retailer. Never a chemical, never a plant as medicine, never a price; only
the retailers below, and only their product or range pages (a probe on 21 Oct found their
blogs and guides in the same results).

The links are plain. An affiliate template per retailer can be set later
(HERBTWIN_SHOP_AFFILIATES); a link through one says so on the page."""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import UTC, date, datetime
from urllib.parse import quote, urlsplit

import httpx

from herbtwin.config import Settings
from herbtwin.search import TIMEOUT_S as SEARCH_TIMEOUT_S
from herbtwin.search import SearchFailed, Tavily, is_trusted
from herbtwin.stages.web_how import PEST_PRODUCTS, names_a_chemical

log = logging.getLogger(__name__)

# domain -> the name shown, and what one of its product or range pages looks like
RETAILERS: dict[str, tuple[str, re.Pattern]] = {
    "diy.com": ("B&Q", re.compile(r"\.(?:prd|cat)(?:$|[?#])")),
    "dobbies.com": ("Dobbies", re.compile(r"/\d+\.[pc](?:$|[?#])")),
    "wickes.co.uk": ("Wickes", re.compile(r"/p/\d+")),
    "homebase.co.uk": ("Homebase", re.compile(r"/p/\d+")),
    "crocus.co.uk": ("Crocus", re.compile(r"/product/")),
    "thompson-morgan.com": ("Thompson & Morgan", re.compile(r"/p/|/garden-essentials/")),
    "harrodhorticultural.com": ("Harrod Horticultural", re.compile(r"-pid\d+\.html")),
    "haxnicks.co.uk": ("Haxnicks", re.compile(r"/products/")),
}
DOMAINS = tuple(RETAILERS)


@dataclass(frozen=True)
class Product:
    name: str  # as the page names it
    query: str  # what Tavily is asked
    must: tuple[str, ...]  # a page title must hold one of these words


COMPOST = Product("Peat-free compost", "peat-free compost", ("compost",))
METER = Product("A soil moisture meter", "soil moisture meter for plants", ("moisture",))
# "hold off watering" says check before you water: the same meter, for checking (integrator)
CHECK_METER = Product("A soil moisture meter, to check before you water", METER.query, METER.must)
FLEECE = Product("Horticultural fleece", "horticultural fleece", ("fleece",))
GROW_LIGHT = Product("A plant grow light", "LED plant grow light", ("grow light", "grow lamp"))
# the answer's action -> what helps do it (1 to 3); none for "leave it", "check first" or "treat"
FOR_ACTION: dict[str, tuple[Product, ...]] = {
    "repot": (
        Product("A pot with drainage holes", "plant pot with drainage holes", ("pot",)),
        COMPOST,
        Product("A saucer for the pot", "plant pot saucer", ("saucer",)),
    ),
    "change_soil": (COMPOST, Product("Horticultural grit", "horticultural grit", ("grit",))),
    "shelter": (FLEECE,),  # outdoors only (products_for)
    "water": (METER,),
    "dont_water": (CHECK_METER,),
    "feed": (Product("Liquid seaweed feed", "liquid seaweed plant feed", ("seaweed",)),),
    "mulch": (Product("Bark mulch", "bark mulch", ("mulch",)),),
    "humidity": (Product("A pebble tray", "plant humidity pebble tray", ("tray",)),),
    # 21 Oct, Kash's live look: a "light tidy" answer showed no shops
    "prune": (
        Product("Secateurs", "garden secateurs", ("secateurs",)),
        Product("Herb snips", "herb snips scissors", ("snips",)),
    ),
    "move_light": (GROW_LIGHT,),  # indoors only (products_for)
    "check_pests": (
        Product(
            "A hand lens, to look under the leaves",
            "hand lens magnifier garden",
            ("lens", "magnifier", "magnifying"),
        ),
    ),
}
MAX_PRODUCTS = 3
# what a pest, weed or disease product is sold as: never a shop link, and never a headline
# under "Reported this month" (reported.py). Brands and pesticide actives that end in no
# "-cide" (#338, #345 reviews: "Bug Clear Ultra", "Derris powder") are web_how.PEST_PRODUCTS,
# shared with the main card's reason; pyrethrum, the -thrins, sulphur, copper sulphate and
# Bordeaux are names_a_chemical's
_PRODUCT_WORDS = (
    r"pellets?|\w*killers?|sprays?|repellents?|traps?|poisons?|"
    rf"{PEST_PRODUCTS}|"
    # #338 integrator review: "vine weevil protection", "Bayer protection", "Ant bait station"
    r"bayer|baits?|control|repel\w*|treatments?|\w+cides?|"
    # a powder only as a pest product (bone meal powder and powder-coated trellis pass)
    r"(?:insect|dusting|pest|flea|louse|lice)\s+powders?|neem|"
    # a wound paint after pruning: the RHS advises against them (#352 review)
    r"sealants?|(?:wound|pruning|tree) paints?"
)
SOLD_AGAINST_PESTS = re.compile(rf"\b(?:{_PRODUCT_WORDS})\b", re.I)
# never sold here: a pest product (above), anything named for the pest, weed or disease it
# is sold against, or a plant sold as a cure
_NEVER = re.compile(
    rf"\b(?:{_PRODUCT_WORDS}|"
    r"remed\w*|medic\w*|cures?|heal(?:s|ing)?|herbal|"
    r"slugs?|snails?|weeds?|pests?|insects?|bugs?|aphids?|fung\w*|mould|mildew|"
    r"weevils?|ants?)\b",
    re.I,
)
# in a title only: "Westland Plant Protection compost". A shop files fleece under "plant
# protection" in its address, so the address may say it
_PROTECTS = re.compile(r"\bprotect\w*", re.I)
# a price or an offer in a title: the card never shows one
_PRICE = re.compile(r"£|\$|€|\bprices?\b|\bsale\b|\boffers?\b|\d+\.\d\d\b|\d+\s?% off", re.I)
# a page title as the shop writes it, made plain: "Buy Sylvagrow compost: Delivery by Crocus"
_BUY = re.compile(r"^buy\s+", re.I)
_TITLE_TAIL = re.compile(
    r"\s*[|–—:-]\s*(?:delivery by\s+)?(?:"
    + "|".join(re.escape(name) for name, _ in RETAILERS.values())
    + r"|wickes\.co\.uk)\b.*$",
    re.I,
)
TITLE_CHARS = 70  # a long listing title is cut at a word


def plain_title(title: str, fallback: str) -> str:
    t = _BUY.sub("", _TITLE_TAIL.sub("", title)).strip()
    if len(t) > TITLE_CHARS:
        t = t[:TITLE_CHARS].rsplit(" ", 1)[0].rstrip(",;:-") + "…"
    return (t[:1].upper() + t[1:]) if t else fallback


TIMEOUT_S = 6.0  # the whole lookup; the page shows nothing rather than wait
FOUND_TTL_S = 7 * 86400.0  # a retailer's range page lasts; a week saves the credits
MISSED_TTL_S = 86400.0  # nothing found: ask again tomorrow
FAILED_TTL_S = 300.0  # the search failed: an outage costs one call per product per 5 min
DAILY_SEARCHES = 200  # Tavily calls a day for the shop links; then none until tomorrow


class DailyCap:
    """Calls per UTC day. At the ceiling the block simply shows nothing until tomorrow."""

    def __init__(self, limit: int, today: Callable[[], date] | None = None):
        self.limit, self._today = limit, today or (lambda: datetime.now(UTC).date())
        self._day, self._used = None, 0
        self._lock = threading.Lock()

    def take(self) -> bool:
        with self._lock:
            day = self._today()
            if day != self._day:
                self._day, self._used = day, 0
            if self._used >= self.limit:
                return False
            self._used += 1
            return True


@dataclass(frozen=True)
class ShopLink:
    product: str
    shop: str
    title: str  # the page's own title, without the shop's name
    url: str  # what the page links to (through an affiliate template when one is set)
    paid: bool  # an affiliate template was used


def products_for(actions: list[str], outdoor: bool = False) -> list[Product]:
    """The kinds of thing that help with the answer's actions, first action first, each
    once, at most MAX_PRODUCTS. Fleece only for a plant outdoors: indoors "shelter" means
    away from a cold window or a draught (integrator, 21 Oct). A grow light only indoors."""
    out: list[Product] = []
    for action in actions:
        for p in FOR_ACTION.get(action, ()):
            if p == FLEECE and not outdoor:
                continue
            if p == GROW_LIGHT and outdoor:  # outdoors, better light means moving it
                continue
            if p not in out and p.query not in {o.query for o in out}:
                out.append(p)
    return out[:MAX_PRODUCTS]


def shop_page(url: str, title: str, product: Product) -> str | None:
    """The retailer's name when this is a page we would link: one of our retailers, one of
    its product or range pages, about this product, and nothing we never sell."""
    if not is_trusted(url, DOMAINS):
        return None
    host = (urlsplit(url).hostname or "").lower()
    domain = next(d for d in DOMAINS if host == d or host.endswith("." + d))
    name, page = RETAILERS[domain]
    if not page.search(url) or not any(
        re.search(rf"\b{re.escape(w)}s?\b", title, re.I) for w in product.must
    ):
        return None  # about this product in the title's own words: "pot" never "potash"
    # the page's address says what it sells too ("/roundup-weedkiller-pot.prd")
    said = f"{title} {re.sub(r'[^A-Za-z0-9]+', ' ', urlsplit(url).path)}"
    if names_a_chemical(said) or _NEVER.search(said) or _PROTECTS.search(title):
        return None
    if _PRICE.search(title):
        return None
    return name


def affiliates_from(raw: str | None) -> dict[str, str]:
    """ "diy.com=https://x.example/?u={url};crocus.co.uk=…" -> {domain: template}. A template
    must be https and hold {url}; anything else is dropped with a log line, never used."""
    out: dict[str, str] = {}
    for part in (raw or "").split(";"):
        domain, _, template = part.strip().partition("=")
        domain, template = domain.strip().lower(), template.strip()
        if not domain:
            continue
        if domain in RETAILERS and template.startswith("https://") and "{url}" in template:
            out[domain] = template
        else:
            log.warning("shop affiliate template for %r ignored", domain)
    return out


def _linked(url: str, affiliates: Mapping[str, str]) -> tuple[str, bool]:
    host = (urlsplit(url).hostname or "").lower()
    for domain, template in affiliates.items():
        if host == domain or host.endswith("." + domain):
            return template.replace("{url}", quote(url, safe="")), True
    return url, False


class ShopFinder:
    """One Tavily search per kind of thing and region, kept for a week (a miss for a day),
    so a busy day costs a handful of credits."""

    def __init__(
        self,
        tavily: Tavily,
        affiliates: Mapping[str, str] | None = None,
        clock=None,
        cap: DailyCap | None = None,
    ):
        self._tavily, self._affiliates = tavily, dict(affiliates or {})
        self._clock = clock or time.monotonic
        self._cap = cap or DailyCap(DAILY_SEARCHES)
        # key -> (when, what was found, how long it holds)
        self._cache: dict[tuple[str, str], tuple[float, tuple[str, str, str] | None, float]] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=MAX_PRODUCTS, thread_name_prefix="shops")

    def _cached(self, key: tuple[str, str]) -> tuple[bool, tuple[str, str, str] | None]:
        with self._lock:
            hit = self._cache.get(key)
        if hit is None:
            return False, None
        at, found, ttl = hit
        return self._clock() - at < ttl, found

    def _search(self, product: Product, region: str) -> tuple[str, str, str] | None:
        """(shop, title, url) of the first page we would link, or None."""
        key = (product.query, region)
        fresh, found = self._cached(key)
        if fresh:
            return found
        if not self._cap.take():
            log.info("shop links: the day's %d searches are used", self._cap.limit)
            return None
        try:
            hits = self._tavily.search(f"{product.query} buy {region}", DOMAINS, 6)
        except SearchFailed as e:
            log.info("shop search failed: %s", e)
            hits = None
        except Exception:  # noqa: BLE001 - shop links are extra: never a reason to fail
            log.exception("shop search broke")
            hits = None
        found = None
        for h in hits or []:
            if (shop := shop_page(h.url, h.title, product)) is not None:
                found = (shop, plain_title(h.title, product.name), h.url)
                break
        ttl = FAILED_TTL_S if hits is None else FOUND_TTL_S if found else MISSED_TTL_S
        with self._lock:
            self._cache[key] = (self._clock(), found, ttl)
        return found

    def links(
        self, actions: list[str], region: str = "UK", outdoor: bool = False
    ) -> list[ShopLink]:
        """A link for each kind of thing that helps, in order, within TIMEOUT_S; whatever
        has not come back by then is left out (and still lands in the cache)."""
        wanted = products_for(actions, outdoor)
        jobs = [self._pool.submit(self._search, p, region) for p in wanted]
        wait(jobs, timeout=TIMEOUT_S)
        for job in jobs:
            job.cancel()  # one not started yet never runs for a page that has gone
        out = []
        for product, job in zip(wanted, jobs, strict=True):
            if job.cancelled() or not job.done() or job.exception() or job.result() is None:
                continue
            shop, title, url = job.result()
            href, paid = _linked(url, self._affiliates)
            out.append(ShopLink(product.name, shop, title, href, paid))
        return out


def shops_from(
    settings: Settings, http: httpx.Client | None = None, cap: DailyCap | None = None
) -> ShopFinder | None:
    """The finder when HERBTWIN_SHOP_LINKS and Tavily are both on, else None (nothing shows)."""
    if not settings.shop_links or not settings.tavily_key:
        return None
    client = http or httpx.Client(timeout=SEARCH_TIMEOUT_S)
    return ShopFinder(
        Tavily(settings.tavily_key, client),
        affiliates_from(settings.shop_affiliates),
        cap=cap or DailyCap(settings.shop_daily_searches),
    )
