"""A trusted page's own sentence beside the answer, when it says the same (19 Oct; the
check passed its pre-registered round-5 test: 4/435 false agrees, Wilson upper 2.3%,
recall 81.5%, data/eval/reports/2026-10-19-trusted-extract-r5-test.json).

One Tavily search per answer, trusted sites only, started when the answer is first
decided and run while the advisors think (pipeline.decide). The first page about the
plant gives its candidate sentences (trusted_judge.candidates, at most 6); Nemotron Ultra
reads each into a form (trusted_extract: E0, then the condition pass), in parallel, never
seeing our advice. After the advisors, plain code (trusted_check.decide) holds each form
against what we know of the plant and the answer's own action; the first agree is quoted
as the page wrote it. Unsure, switched off, late or broken shows nothing. Quote only: the
answer's confidence is unchanged.
"""

from __future__ import annotations

import calendar
import logging
import re
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as Late
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from herbtwin.adapters.base import ModelAdapter
from herbtwin.answer import is_seedlings
from herbtwin.schemas import (
    AnalysisRecord,
    CareAction,
    Environment,
    Observation,
    PageSentence,
    Told,
    TrustedCheck,
)
from herbtwin.search import TRUSTED, Found, WebSearch, is_trusted
from herbtwin.stages.trusted_check import Form, PlantState, decide
from herbtwin.stages.trusted_extract import extract, with_conditions
from herbtwin.stages.trusted_judge import candidates

if TYPE_CHECKING:
    from herbtwin.chat import Search

log = logging.getLogger(__name__)
# from the search's start: the search (up to ~4 s) then two reads (p95 2.2 s each), all
# while the advisors think; joined after them, so only the part past them is waited for
BUDGET_S = 10.0
MAX_SENTENCES = 6  # ~6 x $0.00125 a page
MAX_CHARS = 400  # PageSentence.text: a longer sentence is left out, never the whole page
# words run together where the page's markup was ("potted parsleySome crops", live)
_GLUED = re.compile(r"[a-z](?<!p)[A-Z]|(?<=p)[A-GI-Z]")  # but "pH" is a word
# a line read on its own must not have lost what came before it: a lead-in ("Common
# mistakes to avoid:"), a lone "Never", or a heading that negates its list (review, 19 Oct)
_BULLET = re.compile(r"^\s*(?:[-*•–]|\d+[.)])\s")
_HEADING = re.compile(r"^\s*#")
_NEGATING = re.compile(
    r"\b(?:not|never|no|avoid\w*|mistakes?|don't|don’t|myths?|wrong|problems?|instead)\b", re.I
)
THINKING_OFF = {"chat_template_kwargs": {"enable_thinking": False}}  # as tested in round 5
# web_how's rule: never more than 2 checks at once and nothing queued; busy means no check
_SLOTS = 2
_POOL = ThreadPoolExecutor(max_workers=_SLOTS, thread_name_prefix="trusted-page")
_FREE = threading.BoundedSemaphore(_SLOTS)
_READERS = ThreadPoolExecutor(max_workers=_SLOTS * MAX_SENTENCES, thread_name_prefix="trusted-read")
HOT_C = 25.0  # a day this warm in the week ahead is a hot spell
DRY_DAYS = 12  # of the last 14, under 1 mm: a dry spell
RAIN_MM, RAIN_DAYS = 1.0, 3  # a day with this much rain in the next 3 is rain ahead
# the answer's actions the check was tested on; any other (isolate is not "treat it",
# leave_normal never agrees by design) is unsure
CHECKED = frozenset({"water", "dont_water", "move_light", "shelter", "treat_or_remove", "prune"})


def tavily_only(search: Search | None) -> Search | None:
    """The chain's Tavily alone: on a Tavily failure the chain would go on to Exa or
    TinyFish, which the check never quotes (round 5 was tested on Tavily's pages)."""
    providers = getattr(search, "providers", None)
    if providers is None:
        return search  # a test's fake: _read_page still refuses any provider but Tavily
    mine = [p for p in providers if p.name == "tavily"]
    return WebSearch(mine, search.domains) if mine else None


@dataclass(frozen=True)
class Checking:
    """A search and its reading under way, started as soon as the plant is known."""

    job: Future
    started: float


def _read(adapter: ModelAdapter, plant: str, sentence: str) -> Form | None:
    form = extract(adapter, plant=plant, sentence=sentence, prompt="E0")
    return (
        None
        if form is None
        else with_conditions(adapter, plant=plant, sentence=sentence, form=form)
    )


def _fresh(lines: list[str]) -> list[str]:
    """The lines that start a fresh thought: the first, one after a line that ended a
    sentence, or one after a heading that negates nothing; never a list item under a
    lead-in ending in ":" or under a negating heading, until the list ends."""
    out: list[str] = []
    prev, under = "", False
    for line in lines:
        bullet = bool(_BULLET.match(line))
        heading = bool(_HEADING.match(prev))
        after = not prev or prev.rstrip()[-1:] in ".!?" or (heading and not _NEGATING.search(prev))
        if after and not (bullet and under):
            out.append(line)
        if line.rstrip().endswith(":") or (_HEADING.match(line) and _NEGATING.search(line)):
            under = True
        elif not bullet:
            under = False
        prev = line
    return out


def _whole(sentence: str) -> bool:
    """The page's own sentence, whole: not cut at the snippet's start ("...water well."),
    not run into a neighbour by markup, and short enough to keep."""
    return sentence[:1].isupper() and len(sentence) <= MAX_CHARS and not _GLUED.search(sentence)


def _hits(found: Found) -> list[dict]:
    return [
        {
            "title": h.title,
            "url": h.url,
            "snippet": h.snippet,
            "lines": list(h.lines) or [h.snippet],
        }
        for h in found.hits
    ]


def pages(found: Found, about: Callable[[list[dict]], list[dict]]) -> list[str]:
    """The search's trusted pages about the plant, in its order (at most 8), for "Read
    more"; none from any provider but Tavily."""
    if found.provider != "tavily":
        return []
    return [h["url"] for h in about(_hits(found)) if is_trusted(h["url"], TRUSTED)][:8]


def pick(found: Found, about: Callable[[list[dict]], list[dict]]) -> tuple[str, list[str]] | None:
    """The first trusted page about the plant that has whole sentences to read, and those
    sentences as the page wrote them (at most 6); else the first trusted page about the
    plant, with none, kept for "Read more" (read_more); None when there is no such page.
    Tavily only: the chain falls back to other providers, this never does."""
    if found.provider != "tavily":
        return None
    first = None
    for h in about(_hits(found)):
        if not is_trusted(h["url"], TRUSTED):
            continue
        # line by line: a list line with no full stop never runs into the next sentence
        said = [s for s in candidates(_fresh(h["lines"])) if _whole(s)][:MAX_SENTENCES]
        if said:
            return h["url"], said
        first = first or h["url"]
    return (first, []) if first else None


def _read_page(
    search: Search, adapter: ModelAdapter, plant: str, query: str, about: Callable
) -> TrustedCheck | None:
    found = search.search(query)
    picked = pick(found, about)
    if picked is None:
        return None
    url, said = picked
    forms = list(_READERS.map(lambda s: _read(adapter, plant, s), said)) if said else []
    return TrustedCheck(
        url=url,
        found_with="tavily",
        sentences=[PageSentence(text=s, form=f) for s, f in zip(said, forms, strict=True)],
        pages=[u for u in pages(found, about) if u != url],
    )


def start(
    search: Search | None,
    adapter: ModelAdapter | None,
    plant: str,
    problem: str | None,
    month: int,
    about: Callable[[list[dict]], list[dict]],
) -> Checking | None:
    """One search for the plant and its problem (or its care) this month, and its first
    page's sentences read; None when there is no search or model, or two are running."""
    if search is None or adapter is None or not plant:
        return None
    if not _FREE.acquire(blocking=False):
        log.info("trusted page: skipped, %d checks already running", _SLOTS)
        return None
    query = f"{plant} {problem or 'care'} {calendar.month_name[month]}"
    try:
        job = _POOL.submit(_read_page, search, adapter, plant, query, about)
    except Exception:  # noqa: BLE001 - the pool is shutting down: no check, the answer goes on
        _FREE.release()
        log.exception("trusted page could not start")
        return None
    job.add_done_callback(lambda _: _FREE.release())
    return Checking(job, time.monotonic())


def finish(checking: Checking | None) -> TrustedCheck | None:
    """The page and its forms, within the budget counted from the search's start; None
    otherwise. Only timings are logged, never the page's words."""
    if checking is None:
        return None
    try:
        page = checking.job.result(
            timeout=max(0.0, BUDGET_S - (time.monotonic() - checking.started))
        )
    except Late:
        log.info("trusted page: not read within %.0f s", BUDGET_S)
        return None
    except Exception as e:  # noqa: BLE001 - the check is extra: it never stops an answer
        # the name only: a validation error's text would quote the page's words
        log.warning("trusted page failed (%s)", type(e).__name__)
        return None
    log.info(
        "trusted page: %s in %.2f s",
        f"{len(page.sentences)} sentences read" if page else "no page",
        time.monotonic() - checking.started,
    )
    return page


def _ahead(env: Environment | None, on: date, days: int = 7) -> list:
    """The forecast's days after the photo's, within so many days (by date, never by
    position: a gap in the forecast must not pull a later day in)."""
    end = on + timedelta(days=days)
    return [d for d in env.days if on < d.date <= end] if env else []


def plant_state(rec: AnalysisRecord, action: CareAction, told: Told | None) -> PlantState:
    """What we know of the plant, for decide: anything unknown stays unknown, so a
    condition on it is unsure. The forecast comes from the stored weather alone, so a
    stored answer rebuilt is decided the same way."""
    obs: Observation | None = rec.observation
    top = obs.species[0] if obs and obs.species else None
    setting = (told.setting if told and told.setting else None) or (
        obs.setting if obs else "unknown"
    )
    feel = told.soil_feel if told else None
    if feel is not None:
        soil = {"dry": "dry", "cool": "moist", "damp": "moist", "wet": "wet"}[feel]
    else:
        surface = obs.soil_surface if obs else "not_visible"
        soil = None if surface == "not_visible" else surface
    on = rec.taken_at.date()
    ahead = _ahead(rec.environment, on)
    past = [d for d in rec.environment.days if d.date < on][-14:] if rec.environment else []
    known = bool(ahead)
    return PlantState(
        plant=(top.common_name or top.name).lower() if top else "",
        month=rec.taken_at.month,
        action=action if action in CHECKED else "",
        setting=setting,
        container=obs.container if obs else "unknown",
        soil=soil,
        cold_ahead=any(d.t_min <= 0.0 for d in ahead) if known else None,
        hot_dry=(
            any(d.t_max >= HOT_C for d in ahead) or sum(d.rain_mm < 1.0 for d in past) >= DRY_DAYS
            if known
            else None
        ),
        rain_ahead=(
            any(d.rain_mm >= RAIN_MM for d in _ahead(rec.environment, on, RAIN_DAYS))
            if known
            else None
        ),
        problem=rec.problem.name if rec.problem else None,
        seedlings=obs is not None and is_seedlings(obs),
    )


def page_names(url: str, *names: str | None) -> bool:
    """The page's own address names the plant ("/herbs/parsley/", "/ocimum-basilicum"): a
    page found for a problem can be about another plant (the RHS lily-beetle page for
    rosemary beetle, 21 Oct), and a link to it would mislead."""
    path = urlsplit(url).path.lower().replace("-", " ").replace("_", " ")
    return any(re.search(rf"\b{re.escape(n.lower())}\b", path) for n in names if n and len(n) > 2)


def read_more(rec: AnalysisRecord) -> str | None:
    """The trusted page found for this answer, to link as "Read more" when nothing on it is
    quoted: no claim that it agrees, so only when its address names the plant. The page
    is named by its site on the answer page, never by its title (a page's own words)."""
    page, pack = rec.trusted, rec.pack
    if page is None or page.quote or pack is None:
        return None
    # our own names for the plant (the pack's Latin and common name), never the photo
    # model's ("Sweet basil", a cultivar's quotes)
    names = (pack.species, *pack.common_name.split("/"))
    return next((u for u in (page.url, *page.pages) if page_names(u, *names)), None)


def quoted(page: TrustedCheck | None, state: PlantState) -> TrustedCheck | None:
    """The page with its first sentence that backs this answer quoted, as written; no
    quote when none does."""
    if page is None:
        return None
    quote = next((s.text for s in page.sentences if decide(s.form, state, s.text) == "agree"), None)
    return page.model_copy(update={"quote": quote})
