"""A problem our outcome rows don't cover -> one sentence on how to deal with it, quoted
from a trusted gardening page (approved 19 Oct, "Tavily in the main answer").

Extractive, never generated: no model call. The search is the chat's chain (Tavily first,
trusted sites only); a hit counts only when it is about this plant (the chat's rule), and
the first whole sentence that names the problem and says what to do is taken as it is, at
most 30 words. A strict time budget: past it the answer goes on without one (today's "no
reliable data"). Only the time taken is logged, never the text.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as Late
from typing import TYPE_CHECKING

from herbtwin.chat import about_the_plant, plant_names
from herbtwin.outcomes import problems_for
from herbtwin.schemas import AnalysisRecord, ProblemSeen, WebHow
from herbtwin.search import TRUSTED, is_trusted

if TYPE_CHECKING:
    from herbtwin.chat import Search

log = logging.getLogger(__name__)
BUDGET_S = 4.0
MAX_WORDS = 30
MIN_WORDS = 5
QUOTE_CHARS = 300  # WebHow.quote's cap: 30 long words can pass it
# a slow search is left to finish in the background (its own timeout ends it): the answer
# never waits past the budget. Never more than 2 at once and nothing queued: a burst of
# uploads, or a slow provider, would otherwise pile up searches that still cost credits
# after their answers went out without them (security review, 19 Oct)
_SLOTS = 2
_POOL = ThreadPoolExecutor(max_workers=_SLOTS, thread_name_prefix="web-how")
_FREE = threading.BoundedSemaphore(_SLOTS)
# what a sentence must say to count as how to deal with it
_DO = re.compile(
    r"\b(?:remov|prun|cut|pick|spray|water|isolat|bin|avoid|destroy|dispos|burn|discard|"
    r"treat|apply|improv|ventilat|spac|thin|wip|wash|squash|rub|lift|dig|replac)\w*",
    re.I,
)
# a chemical is never advice we lift from a page: a treatment claim comes only from a sourced
# outcome row (judge finding 3, 19 Oct: a one-off grey-mould read on the basil mildew sample
# quoted fungicide advice for an edible herb, in the month its outcome row does not cover)
# (a denylist, so "names", not "recommends": "a systemic infection" is advice to keep)
_CHEMICAL = re.compile(
    # copper as a product only: copper tape is a cultural slug barrier
    r"\b(?:(?:fungicid|insecticid|pesticid|herbicid|acaricid|miticid)\w*|copper[- ]based|"
    r"copper (?:spray|soap|fungicide|dust|oxychloride)s?|pyrethr\w*|\w*thrins?|"
    # copper sprayed or applied ("spray copper on roses"); copper tape and rings are barriers
    r"(?:spray|apply|dust|use)\s+(?:(?!and\b|or\b)\w+\s+){0,2}copper\b(?![\s-]+(?:tape|rings?|"
    r"bands?|barriers?|wire|mesh|pots?|pipes?|beech|colou?red))|"
    r"chemical (?:spray|treatment|control)s?|sul(?:ph|f)ur|sul(?:ph|f)ates?|bordeaux|neem|"
    r"systemic (?:spray|treatment)s?)\b",
    re.I,
)
# a feed, not a spray: "sulphate of potash", "magnesium sulphate", Epsom salts. Masked
# before _CHEMICAL is looked for, here and in the chat (#282's list, shared)
_FEED = re.compile(
    r"\b(?:sul(?:ph|f)ate of (?:potash|ammonia)|"
    r"(?:potassium|magnesium|ammonium) sul(?:ph|f)ate|epsom salts?)\b",
    re.I,
)


def names_a_chemical(text: str) -> bool:
    """True when the text names a chemical treatment (a feed such as sulphate of potash is
    not one). Shared with the shop links (shops.py)."""
    return bool(_CHEMICAL.search(_FEED.sub(" ", text)))


_SENTENCE = re.compile(r"(?<=[.!])\s+")
_LEAD = re.compile(r"^[\s#*•>|\-–—]+")  # markdown bullets and headings before the words
_NOT_PROSE = re.compile(r"https?:|www\.|[\[\]|{}<>#]")  # links, tables, markup, headings


_GLUE = frozenset("and of the on in a".split())


def _word(w: str) -> re.Pattern:
    """One word, singular or plural and nothing longer: "aphid" or "aphids"; "rot" never
    matches "rotate"."""
    stem = w[:-1] if w.endswith("s") and len(w) > 3 else w
    return re.compile(rf"\b{re.escape(stem)}(?:s|es)?\b", re.I)


def _names(problem: str, plant: frozenset[str] = frozenset()) -> list[re.Pattern]:
    """Every word of the problem's name the sentence must hold: its qualifiers too, so
    "powdery mildew" is never a "downy mildew" sentence (integrator review, 19 Oct). The
    plant's own names are not needed ("basil" in basil downy mildew): the page is about
    the plant already."""
    words = [w for w in problem.lower().split() if w not in _GLUE]
    return [_word(w) for w in words if w not in plant] or [_word(w) for w in words]


def _says(s: str, needed: list[re.Pattern]) -> bool:
    return bool(needed) and all(n.search(s) for n in needed)


def quote_from(
    snippet: str, problem: str, plant: frozenset[str] = frozenset(), others: tuple[str, ...] = ()
) -> str | None:
    """The first whole sentence of the snippet that names the problem and says what to do,
    as written; None when no sentence does. A cut-off last sentence never counts, nor one
    that also names another of the plant's problems (it may be about that one), nor one
    that names a chemical."""
    needed = _names(problem, plant)
    rivals = [_names(o, plant) for o in others if o.lower() != problem.lower()]
    for raw in _SENTENCE.split(snippet):
        s = _LEAD.sub("", raw).strip()
        words = s.split()
        if (
            s.endswith((".", "!"))
            and len(s) <= QUOTE_CHARS
            and MIN_WORDS <= len(words) <= MAX_WORDS
            and not _NOT_PROSE.search(s)
            and _says(s, needed)
            and not any(_says(s, r) for r in rivals)
            and _DO.search(s)
            and not names_a_chemical(s)
        ):
            return s
    return None


def find_how(
    search: Search | None,
    rec: AnalysisRecord,
    problem: ProblemSeen,
    plant: str,
    *,
    budget_s: float = BUDGET_S,
) -> WebHow | None:
    if search is None:
        return None
    if not _FREE.acquire(blocking=False):
        log.info("web how for %s: skipped, %d searches already running", problem.name, _SLOTS)
        return None
    started = time.monotonic()
    query = f"how to treat {problem.name} on {plant}"
    try:
        job = _POOL.submit(search.search, query)
    except Exception:  # noqa: BLE001 - the pool is shutting down: no quote, the answer goes on
        _FREE.release()
        log.exception("web how for %s could not start", problem.name)
        return None
    job.add_done_callback(lambda _: _FREE.release())
    try:
        found = job.result(timeout=budget_s)
    except Late:
        log.info("web how for %s: no reply within %.0f s", problem.name, budget_s)
        return None
    except Exception:  # noqa: BLE001 - the quote is extra: it never stops an answer
        log.exception("web how for %s failed", problem.name)
        return None
    hits = [{"title": h.title, "url": h.url, "snippet": h.snippet} for h in found.hits]
    names, _, key = plant_names(rec)
    plant = frozenset(w for n in names for w in n.split())
    others = tuple(problems_for(key)) if key else ()
    how = None
    for h in about_the_plant(hits, rec):
        quote = quote_from(h["snippet"], problem.name, plant, others)
        if quote is not None and is_trusted(h["url"], TRUSTED) and found.provider:
            how = WebHow(quote=quote, url=h["url"], found_with=found.provider)
            break
    log.info(
        "web how for %s: %s via %s in %.2f s",
        problem.name,
        "quoted" if how else "nothing quotable",
        found.provider,
        time.monotonic() - started,
    )
    return how
