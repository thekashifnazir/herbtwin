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
from typing import NamedTuple
from urllib.parse import quote, urlsplit

import httpx

from herbtwin.config import Settings
from herbtwin.search import SNIPPET_CHARS, SearchFailed, Tavily, is_trusted
from herbtwin.search import TIMEOUT_S as SEARCH_TIMEOUT_S
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
    # a physical or biological pest control (CONTROLS): may name its pest, never a chemical
    control: bool = False
    also: tuple[str, ...] = ()  # ...and one of these too, when set ("copper" and "slug")


COMPOST = Product("Peat-free compost", "peat-free compost", ("compost",))
# for soil: a search for one also finds wall-damp and wood meters ("Dryzone Moisture Meter",
# "Stanley Moisture Meter", probe of 22 Oct), so the title must say soil or plant
METER = Product(
    "A soil moisture meter",
    "soil moisture meter for plants",
    ("soil moisture", "soil meter", "plant moisture"),
)
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
# Handy to have (22 Oct, Kash: "why aren't we doing products too as doesn't that help our
# tavily case?"): an answer that needs nothing still says so, and under it 1 to 2 things
# for what it tells the person to watch for (the headline's cold night, the Keep an eye on
# signs), never for the job, which needs nothing
NIGHT_FLEECE = Product("Horticultural fleece, for a cold night", FLEECE.query, FLEECE.must)
POT_FEET = Product("Pot feet, to lift it out of the wet", "pot feet", ("feet",))
# (a sign's words, the thing that helps, where: outdoors, an outdoor pot, or anywhere). The
# cold night is the twin's, with its day (answer.LEAVE_BUT_PROTECT, answer.FROST_SIGN): a
# month's sign that only names a frost is often normal dieback ("dies back ... after the
# first hard frost") or comes "before any cold night", so it gets no fleece; an unwrapped
# pot does. Indoors a pot in the wet wants its saucer emptied, not feet
FOR_WATCH: tuple[tuple[re.Pattern, Product, str], ...] = (
    (
        re.compile(r"\bthe cold night on \w+|\bpot (?:not wrapped|unwrapped)\b", re.I),
        NIGHT_FLEECE,
        "outdoor",
    ),
    (
        re.compile(r"\bstanding in (?:rain or )?water\b|\bwaterlogged pot\b", re.I),
        POT_FEET,
        "outdoor pot",
    ),
    (
        re.compile(
            r"\b(?:wet|sodden|soggy|waterlogged) compost\b|"
            r"\bcompost (?:is |stays |staying |still )*(?:wet|sodden|waterlogged)\b|"
            r"\bnever dries\b",
            re.I,
        ),
        CHECK_METER,
        "",
    ),
)
# Handy to have for a pest the photo check named (22 Oct, Kash: yes to non-chemical pest
# controls): a barrier, a trap or a biological control only, never a spray, pellets or any
# chemical or "organic" pesticide (ferric phosphate, plant oil or soap). RHS: nematodes for
# slugs and vine weevil; fine mesh keeps carrot fly, allium leaf miner and aphids off;
# yellow sticky traps catch whitefly, fungus gnats and thrips. Hand-picking needs nothing
# (rosemary and mint beetles), and glasshouse predators are not a garden buy
# the probe of 22 Oct: "Nemaslug Slug Killer" is the slug nematode; a copper tape search
# also finds decorating tape; a sticky trap search found a spider glue trap
SLUG_NEMATODES = Product(
    "Slug nematodes, a biological control", "slug nematodes", ("nematode", "nemaslug"), True
)
COPPER_TAPE = Product(
    "Copper tape, a barrier round a pot", "copper slug tape", ("copper",), True, ("slug", "snail")
)
WEEVIL_NEMATODES = Product(
    "Vine weevil nematodes, a biological control", "vine weevil nematodes", ("nematode",), True
)
INSECT_MESH = Product(
    "Insect mesh, to keep them off", "insect mesh netting", ("mesh", "netting"), True
)
STICKY_TRAPS = Product("Yellow sticky traps", "yellow sticky traps", ("sticky",), True, ("yellow",))
# the pest's name (ProblemSeen.name) -> (the control, where it helps), first first
CONTROLS: dict[str, tuple[tuple[Product, str], ...]] = {
    "slugs and snails": ((SLUG_NEMATODES, "outdoor"), (COPPER_TAPE, "pot")),
    "vine weevil": ((WEEVIL_NEMATODES, ""),),
    "aphids": ((INSECT_MESH, "outdoor"),),
    "carrot fly": ((INSECT_MESH, "outdoor"),),
    "allium leaf miner": ((INSECT_MESH, "outdoor"),),
    "whitefly": ((STICKY_TRAPS, ""),),
    "fungus gnats": ((STICKY_TRAPS, ""),),
    "thrips": ((STICKY_TRAPS, ""),),
}
MAX_HANDY = 2
RANGE = 3  # Handy to have: up to 3 pages for each, each at a different shop (22 Oct, Kash)
RESULTS = 10  # a search's results: enough for a range from one search (one credit)
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
# a pest control may name its pest ("Insect Mesh Netting", "Copper Slug Tape") and be a
# sticky or beer trap or a biological control; everything else above still never shows, and
# nor does an "organic" pesticide: ferric phosphate, plant oil, soap or a wash
_CONTROL_SAYS = re.compile(r"\b(?:sticky|beer)\s+traps?\b|\bbiological\s+control\b", re.I)
# a nematode is sold as a "killer" or a "pest control" ("Nemaslug Slug Killer"): with a
# nematode brand named, those words are its name, not a chemical's ("... Slug Killer
# nematode" from another brand is not let through on the word alone)
_NEMATODE = re.compile(r"\b(?:nemaslug|nemasys)\b", re.I)  # the brands, never just the word
_NEMATODE_SAYS = re.compile(r"\b(?:\w*killers?|pest\s+control|control)\b", re.I)
# ...but only on a page for nematodes alone: a bundle could join them to a slug killer
_JOINED = re.compile(r"\b(?:and|with|plus|bundle|kit|set)\b|[+&]", re.I)
_NEVER_A_CONTROL = re.compile(
    rf"\b(?:{_PRODUCT_WORDS}|organic|natural|ferric|soaps?|oils?|wash|drench\w*|"
    # what a slug killer is sold as with no chemical word (review of #429 round 3)
    r"spinosad|sluggo|slug gone|slug clear|nix|kills?|killing|granules?|grains?|deterrents?|"
    r"bio(?!logical)\w*|powders?|dusts?|gels?|liquids?|concentrates?|diatomaceous|"
    r"remed\w*|medic\w*|cures?|herbal|weeds?)\b",
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
    r"\s*(?:[|–—:-]|\bat\b)\s*(?:delivery by\s+)?(?:"
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


# a price as the page listed it when Tavily read it: one £ figure, on a product page (a range
# page lists many), and never a delivery threshold, a price filter or a saving ("Free delivery
# over £75", "Under £20", "save £5": probe of 22 Oct)
_POUNDS = re.compile(r"£\s?(\d{1,4}(?:\.\d{2})?)(?!\d|[.,]\d)(\s*(?:off|per|each)\b|\s*/)?", re.I)
_NOT_ITS_PRICE = re.compile(
    r"\b(?:over|under|above|below|orders?|spend|save|saving|to|up to|worth|min\w*|was|rrp|"
    r"of|per|each|x|payments?|instal+ments?)\W*$",
    re.I,
)
_RANGE_PAGE = re.compile(r"\.(?:cat|c)(?:$|[?#])")
# "from £5": sizes or packs at different prices, so no one price is this page's
_FROM_PRICE = re.compile(r"\bfrom\W*£", re.I)


def listed_price(url: str, content: str) -> str | None:
    """ "£8.99" when the page's text holds one clear price, else None: never a guess."""
    if _RANGE_PAGE.search(urlsplit(url).path) or _FROM_PRICE.search(content):
        return None
    if len(content) >= SNIPPET_CHARS and "£" in content[-12:]:
        return None  # the text was cut near a figure: "£12.95" may read "£12."
    seen = {
        m[1]
        for m in _POUNDS.finditer(content)
        if not m[2] and not _NOT_ITS_PRICE.search(content[max(0, m.start() - 20) : m.start()])
    }
    return f"£{seen.pop()}" if len(seen) == 1 else None


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


class Offer(NamedTuple):
    """A page found for a kind of thing, as the cache keeps it."""

    shop: str
    title: str
    url: str
    price: str | None


@dataclass(frozen=True)
class ShopLink:
    product: str
    shop: str
    title: str  # the page's own title, without the shop's name
    url: str  # what the page links to (through an affiliate template when one is set)
    paid: bool  # an affiliate template was used
    price: str | None = None  # "£8.99" as the page listed it when we looked (listed_price)


@dataclass(frozen=True)
class Handy:
    """One thing handy to have, and up to RANGE pages for it, each at a different shop."""

    product: str
    options: list[ShopLink]
    control: bool = False  # a pest control: the card says why it is there (Kash, 22 Oct)


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


def handy_for(
    signs: list[str], outdoor: bool, in_pot: bool, pest: str | None = None
) -> list[Product]:
    """What is handy: a non-chemical control for the pest the photo showed first, then for
    the things to watch for, in their order, each once, at most MAX_HANDY; none when
    nothing fits."""
    out: list[Product] = []
    for product, where in CONTROLS.get((pest or "").lower(), ()):
        if (where == "outdoor" and not outdoor) or (where == "pot" and not in_pot):
            continue
        out.append(product)
    for sign in signs:
        for words, product, where in FOR_WATCH:
            if (where and not outdoor) or (where == "outdoor pot" and not in_pot):
                continue
            if words.search(sign) and product not in out:
                out.append(product)
    return out[:MAX_HANDY]


def shop_page(url: str, title: str, product: Product) -> str | None:
    """The retailer's name when this is a page we would link: one of our retailers, one of
    its product or range pages, about this product, and nothing we never sell."""
    if not is_trusted(url, DOMAINS):
        return None
    host = (urlsplit(url).hostname or "").lower()
    domain = next(d for d in DOMAINS if host == d or host.endswith("." + d))
    name, page = RETAILERS[domain]

    def says(words: tuple[str, ...]) -> bool:
        return any(re.search(rf"\b{re.escape(w)}s?\b", title, re.I) for w in words)

    if not page.search(url) or not says(product.must) or (product.also and not says(product.also)):
        return None  # about this product in the title's own words: "pot" never "potash"
    # the page's address says what it sells too ("/roundup-weedkiller-pot.prd")
    said = f"{title} {re.sub(r'[^A-Za-z0-9]+', ' ', urlsplit(url).path)}"
    if product.control:
        allowed = _CONTROL_SAYS.sub(" ", said)
        if _NEMATODE.search(title):
            if _JOINED.search(title):
                return None
            allowed = _NEMATODE_SAYS.sub(" ", allowed)
        never = _NEVER_A_CONTROL.search(allowed)
    else:
        never = _NEVER.search(said)
    if names_a_chemical(said) or never or _PROTECTS.search(title):
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
        self._cache: dict[tuple[str, str], tuple[float, tuple[Offer, ...], float]] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=MAX_PRODUCTS, thread_name_prefix="shops")

    def _cached(self, key: tuple[str, str]) -> tuple[bool, tuple[Offer, ...]]:
        with self._lock:
            hit = self._cache.get(key)
        if hit is None:
            return False, ()
        at, found, ttl = hit
        return self._clock() - at < ttl, found

    def _search(self, product: Product, region: str) -> tuple[Offer, ...]:
        """The pages we would link, in the search's order, at most RANGE and each at a
        different shop; none when there are none."""
        key = (product.query, region)
        fresh, cached = self._cached(key)
        if fresh:
            return cached
        if not self._cap.take():
            log.info("shop links: the day's %d searches are used", self._cap.limit)
            return ()
        try:
            hits = self._tavily.search(f"{product.query} buy {region}", DOMAINS, RESULTS)
        except SearchFailed as e:
            log.info("shop search failed: %s", e)
            hits = None
        except Exception:  # noqa: BLE001 - shop links are extra: never a reason to fail
            log.exception("shop search broke")
            hits = None
        found: list[Offer] = []
        for h in hits or []:
            shop = shop_page(h.url, h.title, product)
            if shop is None or shop in {f.shop for f in found}:
                continue
            title = plain_title(h.title, product.name)
            found.append(Offer(shop, title, h.url, listed_price(h.url, h.snippet)))
            if len(found) == RANGE:
                break
        kept = tuple(found)
        ttl = FAILED_TTL_S if hits is None else FOUND_TTL_S if found else MISSED_TTL_S
        with self._lock:
            self._cache[key] = (self._clock(), kept, ttl)
        return kept

    def links(
        self, actions: list[str], region: str = "UK", outdoor: bool = False
    ) -> list[ShopLink]:
        """A link for each kind of thing that helps, in order, within TIMEOUT_S; whatever
        has not come back by then is left out (and still lands in the cache)."""
        return [h.options[0] for h in self._found(products_for(actions, outdoor), region)]

    def handy(
        self,
        signs: list[str],
        region: str = "UK",
        outdoor: bool = False,
        in_pot: bool = False,
        pest: str | None = None,
    ) -> list[Handy]:
        """Handy to have: the same search and the same rules, for what to watch for, with a
        range of up to RANGE shops each and the price each page listed, when it said one."""
        return self._found(handy_for(signs, outdoor, in_pot, pest), region)

    def _found(self, wanted: list[Product], region: str) -> list[Handy]:
        jobs = [self._pool.submit(self._search, p, region) for p in wanted]
        wait(jobs, timeout=TIMEOUT_S)
        for job in jobs:
            job.cancel()  # one not started yet never runs for a page that has gone
        out = []
        for product, job in zip(wanted, jobs, strict=True):
            if job.cancelled() or not job.done() or job.exception() or not job.result():
                continue
            options = []
            for shop, title, url, price in job.result():
                href, paid = _linked(url, self._affiliates)
                options.append(ShopLink(product.name, shop, title, href, paid, price))
            out.append(Handy(product.name, options, product.control))
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
