"""A trusted page's own sentence beside the answer, when it says the same (19 Oct; the
check passed its pre-registered round-5 test: 4/435 false agrees, Wilson upper 2.3%,
recall 81.5%, data/eval/reports/2026-10-19-trusted-extract-r5-test.json).

One Tavily search per answer, trusted sites only, once the advisors have decided
(pipeline.decide; round 7, 21 Oct): the query names the answer's action ("parsley cutting
back"), so the page is about what we advise, where a search before the advice found page
introductions (0 quotes on the 6 judge samples, data/eval/reports/2026-10-21-trusted-hit-
rate.json). The first page about the plant with sentences that name one of our actions
gives them (trusted_judge.candidates, at most 6); Nemotron Ultra reads each into a form
(trusted_extract: E0, then the condition pass), in parallel, never seeing our advice. Plain
code (trusted_check.decide) holds each form against what we know of the plant and the
answer's own action; the first agree is quoted as the page wrote it. An action the check
was never tested on searches the plant's care and reads nothing: the page is kept, never
quoted. Unsure, switched off, late or broken shows nothing. Quote only: the answer's
confidence is unchanged.
"""

from __future__ import annotations

import calendar
import json
import logging
import re
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as Late
from dataclasses import asdict, dataclass
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
from herbtwin.stages.trusted_backs import backs
from herbtwin.stages.trusted_check import Condition, Form, PlantState, could_agree, decide
from herbtwin.stages.trusted_extract import extract, with_conditions
from herbtwin.stages.trusted_judge import candidates

if TYPE_CHECKING:
    from herbtwin.chat import Search

log = logging.getLogger(__name__)
# from the search's start: the search (up to ~4 s), the pages (~0.5 s), two reads (p95
# 2.9 s each, round 6) and a last check on an agree, after the advisors: the answer waits
# for it, never longer than this
BUDGET_S = 12.0
EXTRACTED = 3  # the search's first trusted pages about the plant, read whole (round 8)
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
# each checked action in a gardener's search words, so the page found is about it (round 7)
ACTION_WORDS = {
    "water": "watering",
    "dont_water": "overwatering",
    "shelter": "winter protection",
    "move_light": "sunny position",
    "prune": "cutting back",
    "treat_or_remove": "control",  # after the problem's name: "rosemary beetle control"
}


def reads(action: str, problem: str | None) -> bool:
    """The page's sentences are read for this answer: its action is one the check was
    tested on, and treating names the problem (decide needs it named)."""
    return action in CHECKED and (action != "treat_or_remove" or bool(problem))


def query(plant: str, problem: str | None, action: str, month: int) -> str:
    """The search: the plant and the action's words when its sentences are read, else
    the plant's problem (or its care) this month, as before round 7."""
    if not reads(action, problem):
        return f"{plant} {problem or 'care'} {calendar.month_name[month]}"
    named = problem if action == "treat_or_remove" else None
    return " ".join(x for x in (plant, named, ACTION_WORDS[action]) if x)


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


def _fresh_at(lines: list[str]) -> list[int]:
    """The lines that start a fresh thought: the first, one after a line that ended a
    sentence, or one after a heading that negates nothing; never a list item under a
    lead-in ending in ":" or under a negating heading, until the list ends."""
    out: list[int] = []
    prev, under = "", False
    for i, line in enumerate(lines):
        bullet = bool(_BULLET.match(line))
        heading = bool(_HEADING.match(prev))
        after = not prev or prev.rstrip()[-1:] in ".!?" or (heading and not _NEGATING.search(prev))
        if after and not (bullet and under):
            out.append(i)
        if line.rstrip().endswith(":") or (_HEADING.match(line) and _NEGATING.search(line)):
            under = True
        elif not bullet:
            under = False
        prev = line
    return out


def _fresh(lines: list[str]) -> list[str]:
    return [lines[i] for i in _fresh_at(lines)]


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
    """The search's trusted pages about the plant, in its order (at most 8); none from any
    provider but Tavily."""
    if found.provider != "tavily":
        return []
    return [h["url"] for h in about(_hits(found)) if is_trusted(h["url"], TRUSTED)][:8]


def _first_about(hits: list[dict], problem: str | None) -> list[dict]:
    """Pages whose address names the problem first, else in the search's order (round 8:
    for "basil aphids control" the plant's own page won, and its sentences were about
    sowing)."""
    return sorted(hits, key=lambda h: not (problem and page_names(h["url"], problem)))


def _lines(h: dict, bodies: dict[str, str]) -> list[str]:
    """A page's lines: its whole text when it was read (round 8), else the search's
    snippet lines."""
    body = bodies.get(h["url"])
    return [x.strip() for x in body.splitlines() if x.strip()] if body else h["lines"]


# a page read whole is markdown: links keep their words, emphasis goes; a sentence with
# any markup left is never read, so a quote never shows it
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_EMPHASIS = re.compile(r"\*\*|__")
_MARKUP = re.compile(r"[*_`\[\]|]")


def _unmark(line: str) -> str:
    return _EMPHASIS.sub("", _LINK.sub(r"\1", line))


def _sentences(lines: list[str], action: str | None) -> list[tuple[str, str | None]]:
    """The page's whole sentences that could back this action, each with the heading
    above it, in the page's order."""
    fresh, out, heading = set(_fresh_at(lines)), [], None
    for i, line in enumerate(lines):
        if _HEADING.match(line):
            heading = _unmark(line).lstrip("#").strip()[:200] or None
        if i not in fresh:
            continue
        # line by line: a list line with no full stop never runs into the next sentence
        for s in candidates([_unmark(line)]):
            if (
                _whole(s)
                and not _MARKUP.search(s)
                and could_agree(s, action)
                and all(s != t for t, _ in out)
            ):
                out.append((s, heading))
    return out


def pick(
    found: Found,
    about: Callable[[list[dict]], list[dict]],
    read: bool = True,
    action: str | None = None,
    bodies: dict[str, str] | None = None,
    problem: str | None = None,
) -> tuple[str, list[tuple[str, str | None]]] | None:
    """The first trusted page about the plant with whole sentences that could back this
    action (any of ours, when none is given), and those sentences as the page wrote them
    with their headings (at most 6); else the first trusted page about the plant, with
    none; None when there is no such page. A page in `bodies` is read whole (round 8),
    else its snippet; a page whose address names `problem` goes first. `read=False`
    takes the first page and no sentences. Tavily only:
    the chain falls back to other providers, this never does."""
    if found.provider != "tavily":
        return None
    first = None
    for h in _first_about(about(_hits(found)), problem):
        if not is_trusted(h["url"], TRUSTED):
            continue
        if not read:
            return h["url"], []
        said = _sentences(_lines(h, bodies or {}), action)
        if said:
            return h["url"], said[:MAX_SENTENCES]
        first = first or h["url"]
    return (first, []) if first else None


def _bodies(search: Search, urls: list[str]) -> dict[str, str]:
    """The pages read whole, or none on any trouble: the snippets are read instead."""
    extract = getattr(search, "extract", None)
    if extract is None or not urls:
        return {}
    try:
        return extract(urls)
    except Exception as e:  # noqa: BLE001 - the pages are extra: the snippets still read
        log.warning("trusted page: pages not read (%s)", type(e).__name__)
        return {}


def page_names(url: str, *names: str | None) -> bool:
    """The page's own address names it ("/herbs/parsley/", "/rosemary-beetle")."""
    path = urlsplit(url).path.lower().replace("-", " ").replace("_", " ")
    return any(re.search(rf"\b{re.escape(n.lower())}\b", path) for n in names if n and len(n) > 2)


def on_page(form: Form | None, url: str, state: PlantState) -> Form | None:
    """The form as read on its page (round 8): on a page whose address names the problem
    we found ("/rosemary-beetle"), treating names that problem, as the page is about it;
    round 7 missed "Pick off the adult beetles and larvae by hand and destroy." so."""
    if (
        form is None
        or state.action != "treat_or_remove"
        or form.action != "treat_or_remove"
        or not state.problem
        or not page_names(url, state.problem)
    ):
        return form
    kept = [c for c in form.conditions if c.kind != "named_problem"]
    named = Condition(kind="named_problem", value=state.problem[:60])
    return form.model_copy(update={"conditions": [*kept, named][:6]})


def _read_page(
    search: Search,
    adapter: ModelAdapter,
    plant: str,
    query: str,
    about: Callable,
    read: bool,
    state: PlantState | None,
) -> TrustedCheck | None:
    found = search.search(query)
    problem = state.problem if state and state.action == "treat_or_remove" else None
    first = [h["url"] for h in _first_about([{"url": u} for u in pages(found, about)], problem)]
    bodies = _bodies(search, first[:EXTRACTED]) if read else {}
    picked = pick(found, about, read, state.action if state else None, bodies, problem)
    if picked is None:
        return None
    url, said = picked
    texts = [s for s, _ in said]
    forms = list(_READERS.map(lambda s: _read(adapter, plant, s), texts)) if said else []
    sentences, done = [], False
    for (text, heading), form in zip(said, forms, strict=True):
        agreed = state is not None and decide(on_page(form, url, state), state, text) == "agree"
        # the last gate, with our advice in view: only on an agree, it only takes one away,
        # and only until one is backed (the first is the quote)
        backed = (
            gated(state) if agreed and not done and backs(adapter, state, text, heading) else None
        )
        done = done or backed is not None
        sentences.append(PageSentence(text=text, form=form, heading=heading, backed=backed))
    return TrustedCheck(
        url=url, found_with="tavily", sentences=sentences, pages=pages(found, about)
    )


def start(
    search: Search | None,
    adapter: ModelAdapter | None,
    plant: str,
    problem: str | None,
    action: str,
    month: int,
    about: Callable[[list[dict]], list[dict]],
    state: PlantState | None = None,
) -> Checking | None:
    """One search for the plant and the answer's action (query), and its page's
    sentences read when the action is checked; None when there is no search or model,
    or two are running."""
    if search is None or adapter is None or not plant:
        return None
    if not _FREE.acquire(blocking=False):
        log.info("trusted page: skipped, %d checks already running", _SLOTS)
        return None
    read = reads(action, problem)
    try:
        job = _POOL.submit(
            _read_page,
            search,
            adapter,
            plant,
            query(plant, problem, action, month),
            about,
            read,
            state,
        )
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


def gated(state: PlantState) -> str:
    """The exact plant state the last gate judged, as a key: its yes holds for that state
    alone, so a refine, a shown action that differs from the advisors', or anything else
    that changes what we know drops the quote rather than reuse a yes given for another
    (post-test change after round 8, review: it can only remove quotes)."""
    return json.dumps(asdict(state), sort_keys=True)


def quoted(page: TrustedCheck | None, state: PlantState) -> TrustedCheck | None:
    """The page with its first sentence that backs this answer quoted, as written; no
    quote when none does."""
    if page is None:
        return None
    quote = next(
        (
            s.text
            for s in page.sentences
            if s.backed == gated(state)
            and decide(on_page(s.form, page.url, state), state, s.text) == "agree"
        ),
        None,
    )
    return page.model_copy(update={"quote": quote})
