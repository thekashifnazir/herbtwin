"""Runs the stages in order, collecting typed failures instead of raising. One record per run.

read_photo does everything that costs a vision call or a fetch and returns a Reading;
decide runs the plant model, the advisor x3, confidence and the Answer, and can run again
on the same Reading with what the person told us (refine, spec section 4).

photo -> observe -> where and when -> research, season, weather, plant model -> advise x3
-> confidence -> Answer (spec section 2). Only an observe failure or "not a plant" stops
the run early; anything else that fails becomes a missing factor and a StageFailure.
"""

from __future__ import annotations

import contextvars
import logging
import re
import threading
import time
import uuid
from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import nullcontext
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx

from herbtwin import receipt
from herbtwin.adapters import get_adapter, get_observe_adapter
from herbtwin.adapters.base import CallRecord, ModelAdapter
from herbtwin.advice_context import WeatherFacts, render_context, told_note, weather_facts
from herbtwin.answer import (
    PHOTO_QUESTION,
    TENDER_MONTHS,
    build_answer,
    is_bolted,
    is_seedlings,
    rule_overrides,
    visible_damage,
    weather_explains,
)
from herbtwin.chat import about_the_plant
from herbtwin.confidence import SEVERAL, FactorInputs, assess, photo_issue
from herbtwin.config import Settings
from herbtwin.consequences import SEASONAL, consequence_for
from herbtwin.history import (
    HISTORY_DAYS,
    AdviceScore,
    Evidence,
    StoredAnswer,
    Visit,
    recent_visits,
    trend_line,
    utc,
)
from herbtwin.indoor_care import indoor_care_for
from herbtwin.light import light_block, light_class, light_factor, need_of, read_light
from herbtwin.note_facts import note_facts
from herbtwin.outcomes import outcome_for, problems_for, problems_in
from herbtwin.plant_model import (
    Verdict,
    compare_actions,
    is_tender,
    no_dry_day,
    shelters_from_cold,
    worth_doing,
)
from herbtwin.remote_traces import RemoteTraces, remote_traces_from
from herbtwin.schemas import (
    AnalysisRecord,
    BackupRead,
    CareAction,
    KnowledgePack,
    LightClass,
    LightReading,
    Observation,
    ProblemSeen,
    SpeciesCandidate,
    SpotRead,
    StageFailure,
    TexturePrior,
    Told,
    coarse,
)
from herbtwin.scoring import predict, score_lines
from herbtwin.search import WebSearch, web_search_from
from herbtwin.seasonal import normal_for
from herbtwin.species import PlantMatch, match_species
from herbtwin.spot_priors import lookup
from herbtwin.spot_questions import texture_prior
from herbtwin.stages import trusted_page
from herbtwin.stages.advise import (
    PANEL_TEMPERATURES,
    AdviceRun,
    Panel,
    PanelError,
    advise_panel,
    has_words,
)
from herbtwin.stages.environment import EnvironmentError_, fetch_environment
from herbtwin.stages.observe import ObserveError, observe
from herbtwin.stages.problem import check_problem, second_look_reason
from herbtwin.stages.research import DEFAULT_KC, Lookup, lookup_from, research
from herbtwin.stages.twin import simulate
from herbtwin.stages.web_how import find_how
from herbtwin.sun import sun_hours
from herbtwin.tracing import StageTracer, TraceStore, bind
from herbtwin.twin_bank import key as twin_key
from herbtwin.where import (
    PLACE_NOT_FOUND_HINT,
    exif_exposure,
    for_model,
    geocode,
    in_uk,
    photo_date,
    resolve_location,
    strip_metadata,
)

log = logging.getLogger(__name__)

# The forecast API holds 14 past days: an older photo's weather is not in the window.
WEATHER_DAYS_BACK = 13
OUTSIDE_UK_NOTE = "This place is outside the UK, so UK season norms do not apply."
# D36 (5 Oct): the advisor does not see the SEASON block. On the UK seasonal set it caught
# 70% of real problems without it and 57% with it (3 asks each, n 83); the norm still sets
# the headline, the season factor and the watch line.
ADVISOR_SEES_SEASON = False


@dataclass
class Deps:
    observe_adapter: ModelAdapter
    advise_adapter: ModelAdapter
    settings: Settings
    trace_store: TraceStore
    cache_dir: Path
    http: httpx.Client | None = None
    search: WebSearch | None = None  # the chat's web search; None when switched off
    lookup: Lookup | None = None  # where research finds care facts beyond the seed (B5)
    workers: int = 3  # parallel advisor asks; tests pass 1 for a fixed mock order
    traces: RemoteTraces | None = None  # LangSmith (D64); None when its key is unset
    chat_adapter: ModelAdapter | None = None  # the chat's tool loop; None: the advise model
    check_adapter: ModelAdapter | None = None  # the trusted-page reader; None: no check


def trusted_check_on(settings: Settings) -> bool:
    """The trusted-page check runs: switched on, on Token Factory, with Tavily and the
    search (the credits name its model only then)."""
    return (
        settings.trusted_check
        and settings.backend == "tokenfactory"
        and bool(settings.check_model)
        and settings.tavily_key is not None
        and settings.search_enabled
    )


def _check_adapter(settings: Settings) -> ModelAdapter | None:
    """Nemotron Ultra with thinking off, as the trusted-page check was tested; Token
    Factory only (mock and Ollama runs have no check)."""
    if not trusted_check_on(settings):
        return None
    adapter = get_adapter(settings.backend, settings.check_model, settings)
    adapter.extra_body = trusted_page.THINKING_OFF
    return adapter


def build_deps(settings: Settings, trace_db: Path = Path("traces.db")) -> Deps:
    traces = remote_traces_from(settings)
    return Deps(
        observe_adapter=get_observe_adapter(settings),
        advise_adapter=get_adapter(settings.backend, settings.advise_model, settings),
        chat_adapter=(
            get_adapter(settings.backend, settings.fast_model, settings)
            if settings.fast_model
            else None
        ),
        check_adapter=_check_adapter(settings),
        settings=settings,
        trace_store=TraceStore(trace_db, on_record=traces.record if traces else None),
        traces=traces,
        cache_dir=Path("data/packs"),
        search=web_search_from(settings),
        lookup=lookup_from(settings, Path("data/pages")),
    )


def _fallback_pack(species: str, common: str) -> KnowledgePack:
    return KnowledgePack(
        species=species,
        common_name=common,
        kc=DEFAULT_KC,
        water_need="unknown",
        sun="unknown",
        frost_damage_c=5.0,
        frost_severe_c=0.0,
        notes="fallback pack after research failure",
        verified=False,
    )


@dataclass
class Reading:
    """Evidence read from a photo before advising. Refines reuse it without another vision call."""

    rec: AnalysisRecord  # observation, location, environment, pack and season filled in
    match: PlantMatch
    top: SpeciesCandidate | None
    month: int
    season_missing: str | None
    weather_missing: str | None
    weather: WeatherFacts | None
    failures: list[StageFailure]
    # the trusted-page check (stages/trusted_page.py): run once the answer is first
    # decided; a refine, or a stored answer rebuilt, never searches or reads again
    checked: bool = False


@dataclass(frozen=True)
class History:
    """The plant's earlier visits as the advisor and the page see them (spec section 5)."""

    visits: list[Visit]
    trend: str | None
    days_since: int | None
    light_readings: list[LightReading] = field(default_factory=list)  # C1, last 60 days


def history_for(
    answers: list[StoredAnswer],
    obs: Observation,
    now: datetime,
    scores: list[AdviceScore] | None = None,
    problem: ProblemSeen | None = None,
) -> History:
    """Visits in the last 60 days before this photo (each with how the advice before it
    turned out, when that was asked), the trend against the latest one, and the light
    readings of those 60 days (the plant's light class builds from them)."""
    visits = recent_visits(answers, now, lines=score_lines(scores or []))
    if not visits:
        return History([], None, None)
    last = max(answers, key=lambda a: (a.taken_at == visits[0].taken_at, a.taken_at))
    window = timedelta(days=HISTORY_DAYS)
    lights = [
        a.evidence.light
        for a in answers
        if a.evidence.light is not None and timedelta(0) <= utc(now) - a.taken_at <= window
    ]
    return History(
        visits, trend_line(obs, last, problem), (utc(now) - visits[0].taken_at).days, lights
    )


def evidence_of(reading: Reading) -> Evidence:
    r = reading.rec
    return Evidence(
        location=r.location,
        taken_at_source=r.taken_at_source,
        environment=r.environment,
        pack=r.pack,
        season=r.season,
        notes=list(r.notes),
        failures=list(reading.failures),
        season_missing=reading.season_missing,
        weather_missing=reading.weather_missing,
        light=r.light,
        light_missing=r.light_missing,
        photo_sha256=r.photo_sha256,
        problem=r.problem,
        trusted=r.trusted.model_copy(update={"quote": None}) if r.trusted else None,
    )


def reading_from(stored: StoredAnswer) -> Reading:
    """A stored answer's Reading, rebuilt for a refine after the 1-hour cache."""
    e, obs = stored.evidence, stored.observation
    if stored.told is not None:  # "Wrong? Switch", and where their note says it grows
        obs = told_observation(obs, stored.told)
    rec = AnalysisRecord(
        record_id=stored.id.replace("-", ""),
        taken_at=stored.taken_at,
        taken_at_source=e.taken_at_source,
        location=e.location,
        observation=obs,
        environment=e.environment,
        pack=e.pack,
        state=None,
        season=e.season,
        light=e.light,
        light_missing=e.light_missing,
        photo_sha256=e.photo_sha256,
        problem=e.problem,
        trusted=e.trusted,
        notes=list(e.notes),
    )
    top = obs.species[0] if obs.species else None
    species, common = (top.name, top.common_name) if top else ("unknown", "unknown")
    weather = weather_facts(e.environment, stored.taken_at.date()) if e.environment else None
    return Reading(
        rec=rec,
        match=match_species(species, common),
        top=top,
        month=stored.taken_at.month,
        season_missing=e.season_missing,
        weather_missing=e.weather_missing,
        weather=weather,
        failures=list(e.failures),
        checked=True,  # a stored answer's page was searched once already
    )


BASELINES = ("leave_normal", "dont_water")  # leaving it: what the twin weighs choices against


@dataclass(frozen=True)
class TwinTested:
    """What the twin made of each choice against leaving it, as Compare all choices shows
    it, sent to the wait page once the twin has run (idea 2, 18 Oct)."""

    verdicts: tuple[tuple[CareAction, Verdict], ...]


@dataclass(frozen=True)
class AdvisorReplied:
    """The advisor asks that have come back so far, in the order they finished; None is an
    ask that failed. Sent as each one lands."""

    said: tuple[CareAction | None, ...]
    of: int


def says_several(obs: Observation) -> bool:
    """The read's own words say other plants share the frame ("several herbs", "a mix of"):
    the shared rule in confidence.SEVERAL."""
    return bool(SEVERAL.search(obs.quality_note))


def several_plants(obs: Observation) -> bool:
    """The photo holds more than the plant we answer for (Kash's photos 02 to 06, 18 Oct):
    a planted bed, trough or border, or a read that says other plants share the frame."""
    return obs.scene == "bed_or_border" or says_several(obs)


@dataclass(frozen=True)
class SeasonFound:
    """Our own data for the wait page (21 Oct, Kash): what is normal for the plant this
    month and the problems our outcome rows list for it now. UK norms, so only for a UK
    place, as `rec.season`."""

    name: str  # the plant as the page names it
    month: int
    normal: tuple[str, ...]
    next_change: str | None
    problems: tuple[str, ...]


@dataclass(frozen=True)
class WeatherFound:
    """The weather the twin and the advisors get, for the wait page as soon as it is in."""

    on: date
    facts: WeatherFacts


@dataclass(frozen=True)
class WeatherMissed:
    """The weather did not come back (`fetch_failed`), there was no place to ask it for
    (`no_location`), the place typed was not found (`place_not_found`), or the photo is too
    old for it (`photo_too_old`): the wait says which, never a step done (22 Oct site walk:
    "Checking the weather where you are" ticked as done although the fetch had failed)."""

    why: str


@dataclass(frozen=True)
class PlantFound:
    """The plant the photo model named, and that model's id, from the trace of the call
    whose reply was read: the backup's when the backup answered (21 Oct, judges: which
    model does each step?). None when no call was traced."""

    name: str
    read_by: str | None
    backup: BackupRead | None = None  # the backup read it, not the first model, and why


Progress = Callable[
    [str | TwinTested | AdvisorReplied | SeasonFound | WeatherFound | WeatherMissed | PlantFound],
    None,
]

NOT_A_PLANT_LINE = "This doesn't look like a plant"
# said only when Tavily found the care facts' RHS page (rhs.find_rhs): never for TinyFish,
# and never for a herb of our own file, which searches nothing. Worded to stay true for a
# pack from the cache, which Tavily found on an earlier read (review, 21 Oct)
# the wait's step while the trusted page is searched and read (only when it is)
CHECKING_A_PAGE = "Looking for a trusted gardening page with Tavily"
FOUND_WITH_TAVILY = "Care facts from its RHS page, found with Tavily"


# a photo of different plants asks which one once the read is done (web/tapping.py): the
# wait says so first, and names no plant before the person picks (22 Oct phone walk: "Found
# geranium (not sure)", then "One question first: Tap your plant")
SEVERAL_LINE = "We can see more than one plant: you'll tap the one you mean next"
LOOKING_UP_SEVERAL = "Looking up care facts"


def backup_read(adapter: ModelAdapter, read_by: str | None, raced: bool) -> BackupRead | None:
    """Our backup photo model read the photo, not the first one, and why: it won the race
    against a slow first model that had not failed (`raced`), the first was skipped after failing recently
    (FallbackAdapter.resting), or the first sent no usable reading. None for the first
    model's read, or a reader with no backup."""
    first = getattr(getattr(adapter, "first", None), "model", None)
    backup = getattr(getattr(adapter, "backup", None), "model", None)
    if not first or not backup or first == backup or read_by != backup:
        return None
    why = "slow" if raced else "resting" if getattr(adapter, "resting", False) else "failed"
    return BackupRead(first=first, backup=backup, why=why)


def bare_line(pot: bool) -> str:
    return f"This looks like a {'pot' if pot else 'bed'}, ready for planting"


# the read stops at the photo: the wait page drops its questions on these (web/progress.py)
STOPPED_LINES = frozenset({bare_line(True), bare_line(False), NOT_A_PLANT_LINE})

# The wait page's quick questions (web/waiting.py): set by the page for one read, and asked
# once as the advice starts, so a reply sent while the photo was read goes into this answer.
# Gets the caller's told, returns it with the replies; a refine never sees it (its own
# request's context)
LATE_TOLD: ContextVar[Callable[[Told | None], Told | None] | None] = ContextVar(
    "late_told", default=None
)


def _say(
    progress: Progress | None,
    line: str
    | TwinTested
    | AdvisorReplied
    | SeasonFound
    | WeatherFound
    | WeatherMissed
    | PlantFound,
) -> None:
    """Tell the person what the run is doing (D58). A broken hook never stops a run."""
    if progress is None:
        return
    try:
        progress(line)
    except Exception:  # noqa: BLE001 - progress is a courtesy; the answer matters more
        log.exception("progress hook failed")


def _location_evidence(
    deps: Deps,
    rec: AnalysisRecord,
    match: PlantMatch,
    month: int,
    age_days: int,
    progress: Progress | None = None,
) -> tuple[str | None, str | None, WeatherFacts | None, list[StageFailure]]:
    rec.season = None
    rec.environment = None
    if rec.receipt:  # fetched again below, or not at all (now indoors, or no place)
        rec.receipt = [s for s in rec.receipt if s.stage != "weather"]
    rec.notes = [note for note in rec.notes if note != OUTSIDE_UK_NOTE]

    if rec.location is None:
        season_missing = "no_location"
    elif not in_uk(rec.location.lat, rec.location.lon):
        season_missing = "outside_uk"
    elif match.key is None or (norm := normal_for(match.key, month)) is None:
        season_missing = "no_norm"
    else:
        rec.season = norm
        season_missing = None
    if season_missing == "outside_uk":
        rec.notes.append(OUTSIDE_UK_NOTE)

    indoors = rec.observation is not None and rec.observation.setting == "indoor"
    if indoors:
        weather_missing = "indoors"
    elif rec.location is None:
        weather_missing = "no_location"
        # they typed a place we could not find: not "no place given" (review of #422)
        typed = any(note.endswith(PLACE_NOT_FOUND_HINT) for note in rec.notes)
        _say(progress, WeatherMissed("place_not_found" if typed else weather_missing))
    elif not -1 <= age_days <= WEATHER_DAYS_BACK:
        weather_missing = "photo_too_old"
        _say(progress, WeatherMissed(weather_missing))
    else:
        weather_missing = None

    weather = None
    failures = []
    if weather_missing is None and rec.location is not None:
        _say(progress, "Checking the weather where you are")
        try:
            with receipt.timed(rec, "weather"):
                rec.environment = fetch_environment(
                    rec.location.lat,
                    rec.location.lon,
                    on=rec.taken_at.date(),
                    client=deps.http,
                )
            weather = weather_facts(rec.environment, rec.taken_at.date())
        except EnvironmentError_ as e:
            log.exception("environment failed run=%s", rec.record_id)
            failures.append(StageFailure(stage="environment", message=str(e)))
            weather_missing = "fetch_failed"
            _say(progress, WeatherMissed(weather_missing))
    return season_missing, weather_missing, weather, failures


# closer photo checks running beside research and the weather: 8, as many as the photo
# reads (web/progress.py). Every read waits for its own, so none outlives its read; with
# none free a check runs before the rest, as it did before
_CLOSER_SLOTS = 8
_CLOSERS = ThreadPoolExecutor(max_workers=_CLOSER_SLOTS, thread_name_prefix="closer-look")
_CLOSER_FREE = threading.BoundedSemaphore(_CLOSER_SLOTS)


def _beside(fn: Callable[..., ProblemSeen | None], *args) -> Future[ProblemSeen | None] | None:
    """`fn(*args)` on a closer-look thread, in this context; None when none is free."""
    if not _CLOSER_FREE.acquire(blocking=False):
        return None
    try:
        job = _CLOSERS.submit(contextvars.copy_context().run, fn, *args)
    except RuntimeError:  # the pool is shutting down
        _CLOSER_FREE.release()
        return None
    job.add_done_callback(lambda _: _CLOSER_FREE.release())
    return job


def _look_closer(
    deps: Deps,
    rec: AnalysisRecord,
    adapter: ModelAdapter,
    image: bytes,
    mime: str,
    key: str,
    plant: str,
    said: str,
    month: int,
) -> ProblemSeen | None:
    """The second, targeted photo check, and for a problem we have no treating row on, a
    sentence quoted from a trusted page instead of "no reliable data" (found with the
    chat's search, within 4 s). Never raises: both are extras that never stop an answer.
    Reads only the photo and rec's observation, which nothing changes meanwhile."""
    try:
        found = check_problem(adapter, image, mime, key, plant, likely=said)
    except Exception:  # noqa: BLE001 - the photo check is extra: it never stops an answer
        log.exception("photo check raised run=%s", rec.record_id)
        return None
    if found is not None and outcome_for(key, "treat_or_remove", month, found.name) is None:
        try:
            found.how = find_how(deps.search, rec, found, plant)
        except Exception:  # noqa: BLE001 - the quote is extra: it never stops an answer
            log.exception("web how raised run=%s", rec.record_id)
    return found


def read_photo(
    deps: Deps,
    image: bytes,
    mime: str,
    *,
    received: datetime,
    device: tuple[float, float] | None = None,
    place: str | None = None,
    progress: Progress | None = None,
    tapped: bool = False,
    more: Sequence[tuple[bytes, str]] = (),
    same_as: AnalysisRecord | None = None,
    asks_which: Callable[[Observation], bool] | None = None,
) -> AnalysisRecord | Reading:
    """The photo-reading half. A record when the run stopped early (unreadable photo,
    observe failure, not a plant), else a Reading for decide. `tapped`: the square the
    person tapped in a photo of several (web/tapping.py), so the plant is theirs, not ours.
    `more`: up to two more photos of the same plant (a leaf close up, the soil), read with
    the main photo in its one call; the date, light, twin key, tap and closer photo check
    stay with the main photo, and the location comes from the first photo that has one.
    `same_as`: an earlier answer of this plant read again with more photos ("Add photos for
    a surer answer"): its place and date stand, since its held photo has no metadata left.
    `asks_which`: whether this read will ask which plant once it is done (web/tapping.py),
    so the wait names no plant before the person picks one."""
    record_id = uuid.uuid4().hex  # unguessable: it unlocks a refine of this answer
    tracer = StageTracer(deps.trace_store, record_id)
    if same_as is not None:
        taken_at, taken_src = same_as.taken_at, same_as.taken_at_source
        location, notes = same_as.location, []
    else:
        taken_at, taken_src = photo_date(image, received)
        location, notes = resolve_location(
            image,
            device=device,
            place=place,
            home=deps.settings.home,
            client=deps.http,
            more=[data for data, _ in more],
        )
    rec = AnalysisRecord(
        record_id=record_id,
        taken_at=taken_at,
        taken_at_source=taken_src,
        location=location,
        observation=None,
        environment=None,
        pack=None,
        state=None,
        notes=notes,
    )
    failures: list[StageFailure] = []

    try:
        clean = strip_metadata(image, mime)  # no EXIF (GPS, date) reaches a model provider
        # what the models are sent: at most 1600 px on the long side (where.for_model)
        sent, sent_mime = for_model(clean, mime)
        cleaned = [for_model(strip_metadata(data, kind), kind) for data, kind in more]
    except ValueError as e:
        log.exception("photo unreadable run=%s", record_id)
        rec.failures = [StageFailure(stage="observe", message=str(e))]
        return rec
    rec.photo_sha256 = twin_key(clean)  # the twin bank's lookup key
    _say(progress, "Reading the photo")
    reader, answered = bind(deps.observe_adapter, "observe", tracer), []
    won: list[str | None] = []
    failed_first: list[bool] = []  # the backup won the race after the first model failed

    def traced(call: CallRecord) -> None:
        answered.append(call.model)  # a reply, not a failure: only answered calls are traced
        tracer(call)

    reader.on_call = traced
    try:
        # a race's winner, named by observe: the loser's call is traced too, maybe after it
        obs = observe(
            reader,
            sent,
            sent_mime,
            more=cleaned,
            won_by=won.append,
            first_failed=lambda: failed_first.append(True),
        )
    except ObserveError as e:
        log.exception("observe failed run=%s", record_id)
        rec.failures = [StageFailure(stage="observe", message=str(e), raw=e.raw)]
        return rec
    rec.observation = obs
    # bare ground: no plant to advise on, so the page offers the spot answer from this read.
    # A planted bed still gets its answer: herbs grown side by side read as a bed too (29%
    # of the garden photos, 16 Oct), and losing their advice would cost more than it saves
    if obs.bare_bed:  # compost in an empty pot too: its spot answer is for a pot
        _say(progress, bare_line(obs.container == "pot"))
        return rec
    if not obs.is_plant:
        _say(progress, NOT_A_PLANT_LINE)
        return rec

    top = obs.species[0] if obs.species else None
    species, common = (top.name, top.common_name) if top else ("unknown", "unknown")
    name = (top.common_name or top.name) if top else "the plant"
    read_by = won[-1] if won else answered[-1] if answered else None
    rec.photo_backup = backup_read(reader, read_by, raced=bool(won) and not failed_first)
    # a rough read (blurry, dark, …) of a plant it can't name surely: the wait says the name
    # is a guess and shows no season card for it (22 Oct walk: a blurred parsley was
    # "Found garden mint", then "Normal for garden mint in October")
    rough = top is not None and (
        photo_issue(obs.photo_quality, obs.quality_note, top.confidence) is not None
    )
    try:
        several = asks_which is not None and asks_which(obs)
    except Exception:  # noqa: BLE001 - only the wait's wording: the read goes on
        log.exception("asks_which raised run=%s", record_id)
        several = False
    if several:
        _say(progress, SEVERAL_LINE)
    else:
        found = PlantFound(f"{name} (not sure)" if rough else name, read_by, rec.photo_backup)
        _say(progress, found)
    if top and tapped:
        rec.notes.append(TAPPED_NOTE.format(name=name.lower()))
    elif top and several_plants(obs):
        rec.notes.append(
            f"Answering for the {name.lower()}, one of several plants in this photo. For "
            "another, send a close photo of just that plant."
        )
    match = match_species(species, common)
    month = taken_at.month
    loc = rec.location
    # the UK outdoor season, as the answer's own gate: indoors it does not apply (answer.py)
    outdoor_uk = loc is not None and in_uk(loc.lat, loc.lon) and obs.setting != "indoor"
    if match.key and outdoor_uk and not rough and not several:
        norm = normal_for(match.key, month)
        if norm is not None:  # shown while the rest of the read runs, before the weather
            _say(
                progress,
                SeasonFound(
                    name,
                    month,
                    tuple(norm.normal_signs),
                    norm.next_change,
                    tuple(problems_in(match.key, month)),
                ),
            )
    # the second, targeted look only when the read's own words name a disease or pest sign,
    # or match one of this plant's problem signs for the month: this gate is what keeps
    # healthy photos free of false alarms (13 Oct eval: 0 of 150). The sign match came in on
    # 17 Oct, when "grey dusty patches on leaf underside" ran no look and was called grey mould
    # Research and the weather never use what it finds, so it runs beside them (21 Oct:
    # about 17 s on its own before them, on the slowest answers)
    closer: Future[ProblemSeen | None] | None = None
    if (said := second_look_reason(obs, match.key, month)) is not None and match.key:
        look = (
            deps,
            rec,
            bind(deps.observe_adapter, "problem", tracer),
            sent,
            sent_mime,
            match.key,
            common or name,
            said,
            month,
        )
        closer = _beside(_look_closer, *look)
        if closer is None:  # no thread free: before the rest, as it always ran
            _say(progress, "Looking closer at the leaves")
            rec.problem = _look_closer(*look)

    _say(progress, LOOKING_UP_SEVERAL if several else f"Looking up how {name} likes to grow")
    try:
        with receipt.timed(rec, "research"):
            rec.pack = research(species, common, cache_dir=deps.cache_dir, lookup=deps.lookup)
    except Exception as e:  # noqa: BLE001 - recorded as a typed failure, run continues on defaults
        log.exception("research failed run=%s", record_id)
        failures.append(StageFailure(stage="research", message=f"{type(e).__name__}: {e}"))
        rec.pack = _fallback_pack(species, common)
    if rec.pack.found_with == "tavily":
        _say(progress, FOUND_WITH_TAVILY)

    age_days = (received.date() - taken_at.date()).days
    season_missing, weather_missing, weather, location_failures = _location_evidence(
        deps, rec, match, month, age_days, progress
    )
    if weather is not None and age_days <= 0:  # taken today: its "today" is today's
        _say(progress, WeatherFound(rec.taken_at.date(), weather))
    failures.extend(location_failures)
    indoors = obs.setting == "indoor"
    env = rec.environment
    rec.light, rec.light_missing = read_light(
        exif_exposure(image),
        taken_at if taken_src == "exif" else None,
        env.sky_hours if env is not None else [],
        indoor=indoors,
        sky_offset_s=env.sky_utc_offset_s if env is not None else None,
    )
    if closer is not None:  # said last: on a slow check, it is the step still running
        _say(progress, "Looking closer at the leaves")
        rec.problem = closer.result()
    _note_models(deps, rec, frozenset({"observe", "problem"}))
    return Reading(
        rec=rec,
        match=match,
        top=top,
        month=month,
        season_missing=season_missing,
        weather_missing=weather_missing,
        weather=weather,
        failures=failures,
    )


def relocate(deps: Deps, reading: Reading, place: str) -> Reading:
    """Resolve a new place and refresh only the location-dependent evidence."""
    rec = reading.rec.model_copy(deep=True)
    rec.location = geocode(place, client=deps.http)
    return _located(deps, reading, rec)


def resettle(deps: Deps, reading: Reading, setting: str) -> Reading:
    """The person says the read got indoors or outdoors wrong ("Wrong? Switch"): the same
    read with the setting forced, and the location evidence redone for it, so indoors has
    no forecast and outdoors gets one."""
    obs = reading.rec.observation
    if obs is None or obs.setting == setting:
        return reading
    rec = reading.rec.model_copy(deep=True)
    rec.observation = obs.model_copy(update={"setting": setting})
    # the light reading was made for the old setting: indoors reads none (read_light), and
    # outdoors needs the photo again, so it is not known rather than "indoors"
    if setting == "indoor":
        rec.light, rec.light_missing = None, "indoors"
    elif rec.light_missing == "indoors":
        rec.light_missing = None
    return _located(deps, reading, rec)


def told_where(told: Told) -> tuple[str | None, str | None]:
    """Indoors or out, and pot or ground, as the person told us: the switch first, then
    their own note (22 Oct site walk: "in a pot on a sunny balcony" left the band at "In the
    ground", the soil maps and a bed's advice)."""
    heard = note_facts(told.question)
    return told.setting or heard.setting, heard.container


def changes_read(told: Told) -> bool:
    """What was told corrects the photo read or its place, so the reading is redone."""
    setting, container = told_where(told)
    return bool(told.place or setting or container)


def told_observation(obs: Observation, told: Told) -> Observation:
    """The read with where the person says it grows."""
    setting, container = told_where(told)
    update = {
        k: v
        for k, v in (("setting", setting), ("container", container))
        if v and getattr(obs, k) != v
    }
    return obs.model_copy(update=update) if update else obs


def rehouse(reading: Reading, container: str) -> Reading:
    """Pot or ground as the person said: the same read and location evidence, the twin and
    the soil prior follow the observation when the advice is decided again."""
    obs = reading.rec.observation
    if obs is None or obs.container == container:
        return reading
    rec = reading.rec.model_copy(deep=True)
    rec.observation = obs.model_copy(update={"container": container})
    return replace(reading, rec=rec)


def as_told(deps: Deps, reading: Reading, told: Told) -> Reading:
    """The reading with what the person corrected under the answer: the place, the setting
    (the switch, or their note), pot or ground (their note)."""
    setting, container = told_where(told)
    if told.place:
        reading = relocate(deps, reading, told.place)
    if setting:
        reading = resettle(deps, reading, setting)
    if container:
        reading = rehouse(reading, container)
    return reading


def _located(deps: Deps, reading: Reading, rec: AnalysisRecord) -> Reading:
    age_days = (datetime.now(UTC).date() - rec.taken_at.date()).days
    season_missing, weather_missing, weather, location_failures = _location_evidence(
        deps, rec, reading.match, reading.month, age_days
    )
    failures = [failure for failure in reading.failures if failure.stage != "environment"]
    failures.extend(location_failures)
    return Reading(
        rec=rec,
        match=reading.match,
        top=reading.top,
        month=reading.month,
        season_missing=season_missing,
        weather_missing=weather_missing,
        weather=weather,
        failures=failures,
        # the same answer, told more: its page is never searched or read again
        checked=reading.checked,
    )


def spot_inputs(
    rec: AnalysisRecord,
    told: Told | None,
    klass: tuple[LightClass, str] | None,
    indoors: bool,
) -> tuple[tuple[LightClass, str] | None, TexturePrior | None]:
    """The spot answer's two inputs for a plant answer (spot spec section 8, D73): a light
    class from a compass tap when the visits gave none, and the soil texture prior for a
    plant in the ground (maps, or the squeeze when given). Code only; no model call."""
    loc, obs = rec.location, rec.observation
    texture = None
    if loc is not None and obs is not None and obs.container == "ground":
        read = SpotRead(setting="open_ground", medium="soil")
        texture = texture_prior(lookup(loc.lat, loc.lon), read, told.squeeze if told else None)
    if klass is None and not indoors and loc is not None and told and told.heading:
        sun = sun_hours(loc.lat, loc.lon, told.heading.aspect(), None, rec.taken_at.year)
        hours = sun.months[5][1]
        said = (
            "your compass reading" if told.heading.direction is None else "the direction you picked"
        )
        klass = (sun.june_class, f"about {hours:.0f} h of direct sun in June ({said})")
    return klass, texture


# the twin's claim is "no dry day in the next 2 weeks": it holds only over a 2-week forecast
HOLD_WATER_DAYS = 14


def twin_holds_water(panel: Panel, views: dict, *, days: int, dry_signs: bool) -> Panel:
    """A "water it" call gives way to leaving it when the twin finds no dry day in the 2
    weeks without watering. Site walk 2 (22 Oct), r1: three advisors said "Water it." in
    London with 6 mm of rain that day, while Compare said "no dry days or frost in the next
    2 weeks"; Kash, 22 Oct: "cool do it". Only over a full 2-week forecast (`days`), and
    never against a sign of dryness the twin may have under-read (`dry_signs`: droop or a
    dry surface in the photo, or "the soil feels dry"): a drooping basil on a dry surface
    starts about 2 mm above the twin's dry day, too close to overrule three advisors on. No
    forecast (indoors, the evals), no change."""
    if (
        panel.primary != "water"
        or days < HOLD_WATER_DAYS
        or dry_signs
        or not no_dry_day(views.get("water"))
    ):
        return panel
    return _led_by(panel, "leave_normal")


def follow_the_twin(panel: Panel, views: dict) -> Panel:
    """A split "leave it" panel follows the twin on cold: when sheltering beats leaving it
    before a cold or frost day, and at least one ask chose shelter, that ask leads. "Leave it.
    This is normal" over "Tested on your plant's twin: cold risk Sunday" read as a
    contradiction (18 Oct pre-deploy, basil flowering: 1 shelter, 2 leave). Only a leave-it
    call gives way: under "treat it" or "cut it back" shelter is already an Also do
    (on the 17 Oct steadiness runs a wider rule would have turned mildew basil's "treat it"
    into "protect it"). A panel that agrees, or has no shelter ask, keeps its call; so does
    any panel without a forecast (every expert-question eval: no twin runs there)."""
    if (
        # only "leave it": "treat it" or "cut it back" keeps shelter as an extra, and "hold off
        # watering" keeps its hold on the water card
        panel.primary != "leave_normal"
        or panel.agree == panel.total
        or not shelters_from_cold(views.get("shelter"))
    ):
        return panel
    held = [r for r in panel.runs if coarse(r.advice.primary) == "shelter"]
    if not held:
        return panel
    chosen = next((r for r in held if has_words(r.advice.answer)), held[0])
    return replace(panel, primary=chosen.advice.primary, chosen=chosen, agree=len(held))


# calls a tender herb's protection comes before (tender_first): the jobs that can wait a
# week. Never treating a problem, watering or holding off, nor "leave it", whose cold night
# is already in its headline (answer._leave_but_protect)
GIVES_WAY: frozenset[CareAction] = frozenset(
    {"prune", "feed", "repot", "change_soil", "mulch", "rotate", "humidity", "move_light", "other"}
)
LED_WITH = {  # the advisors' call, in the note under the headline when a rule of ours led
    "prune": "cutting it back",
    "feed": "feeding it",
    "repot": "repotting it",
    "change_soil": "refreshing its soil",
    "mulch": "mulching it",
    "rotate": "turning the pot",
    "humidity": "raising the humidity",
    "move_light": "moving it to better light",
    "other": "another job",
    "isolate": "keeping it away from other plants",
    "leave_normal": "leaving it",
    "water": "watering it",
}
HELD_WATER_NOTE = (
    "your plant's twin finds no dry day in the next 2 weeks without it, so leaving it leads."
)


def _led_by(panel: Panel, primary: CareAction) -> Panel:
    """The panel led by `primary`: an ask that chose it gives the words; with none, the
    chosen run stays for its other actions, and agreement is 0 (confidence drops for it)."""
    held = [r for r in panel.runs if r.advice.primary == primary]
    if not held:
        return replace(panel, primary=primary, agree=0)
    chosen = next((r for r in held if has_words(r.advice.answer)), held[0])
    return replace(panel, primary=primary, chosen=chosen, agree=len(held))


def tender_first(
    panel: Panel, views: dict, *, tender: bool, month: int, setting: str, struggling: bool
) -> Panel:
    """A tender herb (basil) outside from October to March is protected first: before a
    cold night the twin marks, or when the photo shows it struggling outdoors. The
    gardener's review (19 Oct, s052): "Cut it back." led a stressed outdoor basil in
    mid-October while protection was left for later in the week. A call that treats a
    problem or waters keeps its place, as does any plant indoors. "Leave it" gives way
    only when there is no forecast (the twin always tests shelter when it runs): with one,
    its own headline says to protect it before a cold night; without one, "this is normal
    for October" would leave a tender plant out unwarned (22 Oct walk)."""
    unwarned = panel.primary == "leave_normal" and "shelter" not in views
    if (
        not tender
        or month not in TENDER_MONTHS
        or setting == "indoor"
        or not (panel.primary in GIVES_WAY or unwarned)
        or not (
            unwarned
            or shelters_from_cold(views.get("shelter"))
            or (setting == "outdoor" and struggling)
        )
    ):
        return panel
    return _led_by(panel, "shelter")


# the openings of the notes that say how a rule of ours chose the lead, used by decide() and
# by how_led: they belong with How we worked it out, not over the advice (design wave 1, A);
# "Answering for the basil you tapped" stays up top
LED_NOTE = "The advisors led with"
BACKED_NOTE = "advisors said to protect it"


def how_led(note: str) -> bool:
    return note.startswith(LED_NOTE) or f" {BACKED_NOTE};" in note


TAPPED_NOTE = "Answering for the {name} you tapped."
# under this, a name read from one plant among several is a guess (21 Oct, #324 findings:
# a tapped crop read "Hyssop" at 0.55 and its heading showed no doubt)
SHARED_NAME_SURE = 0.6


def name_in_doubt(rec: AnalysisRecord) -> bool:
    """The heading says "(not sure)": a rough photo read under 0.5, or a plant tapped from a
    photo of several, or one of a mixed scene, read under 0.6."""
    obs = rec.observation
    if obs is None or not obs.species:
        return False
    conf = obs.species[0].confidence
    if rec.answer is not None and rec.answer.photo_issue and conf < 0.5:
        return True
    tapped = TAPPED_NOTE.split("{name}")[1]
    shared = several_plants(obs) or any(n.endswith(tapped) for n in rec.notes)
    return shared and conf < SHARED_NAME_SURE


def photo_hides_name(rec: AnalysisRecord) -> bool:
    """The photo itself is the trouble (blurry, dark, the plant small, hard to read), so the
    name is a guess: the heading says "Not clear: maybe mint", never the bare name. A photo
    issue is only ever set on a name read under SURE_NAME (22 Oct site walk 2: a blurred
    parsley's biggest text was "Mint (not sure)", which read as the answer)."""
    obs = rec.observation
    return bool(obs and obs.species) and rec.answer is not None and bool(rec.answer.photo_issue)


def in_proportion(panel: Panel, *, damage: bool, in_ground: bool = False) -> Panel:
    """Keeping it apart only for harm the photo shows or a problem it names; otherwise a
    look under the leaves leads (s014 mint: one insect, no damage, told to keep it away
    from the other plants). A plant in the ground cannot be moved apart: with harm shown,
    treating it leads instead (judge walk: border rosemary)."""
    if panel.primary != "isolate" or (damage and not in_ground):
        return panel
    return _led_by(panel, "treat_or_remove" if damage else "check_pests")


# the order a fallback lead is picked in when the advisors' own lead must wait: Advice.actions
# is stored sorted, so it says nothing about what they would do next
CARE_ORDER: tuple[CareAction, ...] = (
    "water",
    "dont_water",
    "shelter",
    "move_light",
    "treat_or_remove",
    "check_pests",
    "prune",
    "humidity",
    "rotate",
    "isolate",
    "feed",
    "repot",
    "change_soil",
    "mulch",
)  # fmt: skip  (never "other": it has no headline, so the advisor's words would become one)


# grown without soil: a feed there is the nutrient solution, with no season of its own
# (SE 7258, a hydroponic basil in May: "Feed it" fell back to "Leave it")
HYDROPONIC = re.compile(r"\b(?:hydroponic\w*|aquaponic\w*|kratky|deep water culture)\b", re.I)
SOILLESS = re.compile(
    r"\b(?:hydroponic\w*|aquaponic\w*|nutrient solution|kratky|deep water culture|"
    # never "growing in water-retentive compost" (#315 review)
    r"(?:grown|growing|grows) in (?:a jar of |a glass of )?water(?![-\w])|"
    r"water-grown(?![-\w]))",
    re.I,
)


def is_soilless(*texts: str) -> bool:
    """The person, the photo read or an advisor says it grows without soil."""
    return any(SOILLESS.search(t) for t in texts if t)


def in_season(panel: Panel, *, plant_key: str | None, month: int, soilless: bool = False) -> Panel:
    """A seasonal job out of its season never leads (all three advisors said "Feed it." for
    an October basil, over "best done in Jun, Jul, Aug or Sep"): what another ask led with
    leads instead, else the first in-season job the chosen advisor listed, else leaving it."""

    def waits(action: CareAction) -> bool:
        return (
            action in SEASONAL
            and consequence_for(
                action, plant_key=plant_key, month=month, answer="", views={}
            ).off_season
        )

    if plant_key is None or soilless or not waits(panel.primary):
        return panel
    # another ask's "Leave it" counts too (#315 review: feed, feed, leave it became "Water it."),
    # and wins a tie: water's words lost the "only if the soil is dry" caveat (second review)
    asked = ("leave_normal", *CARE_ORDER)
    led = Counter(
        r.advice.primary
        for r in panel.runs
        if r.advice.primary in asked and not waits(r.advice.primary)
    )
    listed = set(panel.chosen.advice.actions) - {panel.primary}
    if led:  # ties: leave it first, then the care order; never which ask answered first
        then = min(led, key=lambda a: (-led[a], asked.index(a)))
    else:
        then = next((a for a in CARE_ORDER if a in listed and not waits(a)), "leave_normal")
    return _led_by(panel, then)


def decide(
    deps: Deps,
    reading: Reading,
    told: Told | None = None,
    history: History | None = None,
    *,
    progress: Progress | None = None,
) -> AnalysisRecord:
    """The advice half: plant model, advisor x3, confidence, Answer. Runs on a copy, so the
    same Reading can be decided again with what the person told us."""
    if (late := LATE_TOLD.get()) is not None:
        LATE_TOLD.set(None)  # once: a second decide in this read keeps what it was given
        try:
            told = late(told)
        except Exception:  # noqa: BLE001 - the replies are extra: never a reason to fail
            log.exception("wait replies could not be read")
    rec = reading.rec.model_copy(deep=True)
    failures = list(reading.failures)
    tracer = StageTracer(deps.trace_store, rec.record_id)
    about = rec.model_copy(deep=True)  # the plant as read, for the trusted page's search
    obs, match, top, month = rec.observation, reading.match, reading.top, reading.month
    weather = reading.weather
    soil_feel = told.soil_feel if told else None
    rec.told = told
    indoors = obs.setting == "indoor"

    views: dict = {}
    if rec.receipt is not None:
        rec.receipt = [s for s in rec.receipt if s.stage != "twin"]  # timed again below
    if rec.environment is not None:
        try:
            with receipt.timed(rec, "twin") if rec.receipt is not None else nullcontext():
                rec.state = simulate(
                    obs, rec.environment, rec.pack, on=rec.taken_at.date(), soil_feel=soil_feel
                )
                views = compare_actions(rec.state, tender=is_tender(rec.pack))
            tested = tuple((a, v.vs_leaving_it) for a, v in views.items() if a not in BASELINES)
            if tested:
                _say(progress, TwinTested(tested))
        except Exception as e:  # noqa: BLE001 - a twin bug must not 500 the page
            log.exception("twin failed run=%s", rec.record_id)
            failures.append(StageFailure(stage="twin", message=f"{type(e).__name__}: {e}"))

    earlier = history.light_readings if history else []
    now_light = rec.light
    klass = None if indoors else light_class(earlier + ([now_light] if now_light else []))
    spot_on = deps.settings.spot_enabled
    texture = None
    if spot_on:
        klass, texture = spot_inputs(rec, told, klass, indoors)
    need = need_of(rec.pack.sun) if rec.pack else frozenset()
    plant = rec.pack.common_name if rec.pack else "the plant"
    light_text = light_block(now_light, klass, rec.pack.sun if rec.pack else "unknown", plant)
    problems = problems_for(match.key) if match.key else []
    context = render_context(
        obs=obs,
        location=rec.location,
        weather=weather,
        norm=rec.season if ADVISOR_SEES_SEASON else None,
        season_missing=reading.season_missing if ADVISOR_SEES_SEASON else None,
        pack=rec.pack,
        views=views or None,
        problems=problems,
        told=told,
        history=history.visits if history else None,
        trend=history.trend if history else None,
        light=light_text,
        problem=rec.problem,
    )
    _say(progress, "Thinking about what it needs")
    said: list[CareAction | None] = []

    def heard(run: AdviceRun | None) -> None:  # advise_panel calls this one at a time
        said.append(run.advice.primary if run else None)
        _say(progress, AdvisorReplied(tuple(said), len(PANEL_TEMPERATURES)))

    seen = _last_row(deps, rec.record_id)  # this decide's advisor calls come after it
    asked_at = time.perf_counter()
    try:
        panel = advise_panel(
            bind(deps.advise_adapter, "advise", tracer),
            PHOTO_QUESTION,
            obs,
            context=context,
            workers=deps.workers,
            note=told_note(told),
            soil_known=soil_feel is not None,
            on_reply=heard if progress else None,
        )
    except PanelError as e:
        log.exception("advise failed run=%s", rec.record_id)
        failures.append(StageFailure(stage="advise", message=str(e), raw=e.raw))
        rec.failures = failures
        return rec
    advised_ms = int((time.perf_counter() - asked_at) * 1000)

    asked = panel
    base = (
        next((x for x in rec.state.strips if x.action == "do_nothing"), None) if rec.state else None
    )
    dry_signs = obs.water_stress >= 2 or obs.soil_surface == "dry" or soil_feel == "dry"
    panel = twin_holds_water(panel, views, days=len(base.days) if base else 0, dry_signs=dry_signs)
    held_water = panel is not asked
    if held_water:
        rec.notes.append(f"{LED_NOTE} {LED_WITH['water']}; {HELD_WATER_NOTE}")
    before = panel
    panel = follow_the_twin(panel, views)
    if panel is not before:
        if held_water:  # shelter leads on a cold night, not leaving it: no note saying it does
            held_water = False
            rec.notes.pop()
        # the page says who chose it: a minority call the twin backs, not a sure advisor
        rec.notes.append(
            f"{panel.agree} of {panel.total} {BACKED_NOTE}; the 2-week forecast "
            "backs them (a cold night ahead), so that leads."
        )
    # a verified pack only: an unknown frost limit stands in at 5.0 C, which reads as tender
    # (integrator's review of #290: a hardy plant with no RHS rating told to come indoors)
    tender = rec.pack is not None and rec.pack.verified and is_tender(rec.pack)
    struggling = obs.decline >= 1 or obs.leaf_colour in ("some_yellow", "mostly_yellow")
    damage = visible_damage(obs, rec.problem)
    before = panel
    panel = tender_first(
        panel, views, tender=tender, month=month, setting=obs.setting, struggling=struggling
    )
    if panel is not before:
        rec.notes.append(
            f"{LED_NOTE} {LED_WITH[before.primary]}; a tender plant left out from "
            "October to March is protected first, so that leads."
        )
    before = panel
    # the person's own words and the read: any sign it grows without soil. The advisors'
    # words only by name ("feed with a diluted nutrient solution" is everyday liquid feed)
    soilless = is_soilless(obs.notes, told.question if told else "") or any(
        HYDROPONIC.search(r.advice.answer) for r in panel.runs
    )
    panel = in_season(panel, plant_key=match.key, month=month, soilless=soilless)
    if panel is not before:
        rec.notes.append(
            f"The advisors led with {LED_WITH[before.primary]}; for this plant that waits for "
            "its season, so the next job leads."
        )
    before = panel
    panel = in_proportion(panel, damage=damage, in_ground=obs.container == "ground")
    if panel is not before:
        rec.notes.append(
            f"{LED_NOTE} {LED_WITH['isolate']}; a plant in the ground cannot be "
            "moved apart, so treating it comes first."
            if panel.primary == "treat_or_remove"
            else f"{LED_NOTE} {LED_WITH['isolate']}; with no sign of a pest doing "
            "harm in the photo, a look under the leaves comes first."
        )
    followed = panel is not asked  # a rule of ours chose the lead: not the advisor's sureness
    if not reading.checked:
        # a trusted page for the action we advise, searched and read now it is decided
        # (round 7: a search before the advice found page introductions); kept on the
        # reading, so a refine is decided again with no new search or read. A plant we
        # have no data on is never searched: its pages could be about anything
        reading.checked = True
        checking = trusted_page.start(
            trusted_page.tavily_only(deps.search) if deps.settings.tavily_key else None,
            bind(deps.check_adapter, "trusted_page", tracer) if deps.check_adapter else None,
            (top.common_name or top.name) if top and reading.match.key else "",
            rec.problem.name if rec.problem else None,
            panel.primary,
            month,
            lambda hits: about_the_plant(hits, about),
            trusted_page.plant_state(rec, panel.primary, told),
        )
        if checking is not None:
            _say(progress, CHECKING_A_PAGE)
        reading.rec.trusted = trusted_page.finish(checking)
    others_better = any(worth_doing(v) for a, v in views.items() if a not in BASELINES)
    inputs = FactorInputs(
        action=panel.primary,
        advisor="low" if followed else panel.advisor,  # its own sureness is not the panel's
        rule_led=followed,
        agree=panel.agree,
        total=panel.total,
        repaired=panel.repaired,
        species_conf=top.confidence if top else None,
        match_how=match.how,
        photo_quality=obs.photo_quality,
        quality_note=obs.quality_note,
        # the season norms are the UK outdoor year: indoors they say nothing about the plant
        norm=None if indoors else rec.season,
        season_missing="indoors" if indoors else reading.season_missing,
        plant_key=match.key,
        month=month,
        symptoms=obs.symptoms,
        decline=obs.decline,
        view=views.get(panel.primary),
        others_better=others_better,
        model_missing="indoors" if indoors else None if views else "no_weather",
        container=obs.container,
        setting=obs.setting,
        weather_ok=weather is not None,
        weather_missing=reading.weather_missing,
        cold_nights_14=weather.cold_nights_14 if weather else 0,
        explains=weather_explains(obs, weather, match.key),
        pack_verified=rec.pack.verified,
        soil_surface=obs.soil_surface,
        has_location=rec.location is not None,
        soil_feel=soil_feel,
        history_days=history.days_since if history else None,
        light_factor=light_factor(
            panel.primary,
            now_light,
            rec.light_missing,
            klass,
            need,
            window=getattr(told, "window", None),  # Told.window: the window question
        ),
        spot_on=spot_on,
        texture=texture,
        light_known=klass is not None,
    )
    rec.answer = build_answer(
        panel=panel,
        assessment=assess(inputs),
        norm=rec.season,
        plant_key=match.key,
        month=month,
        views=views,
        told_question=told.question if told else None,
        problem=rec.problem,
        setting=obs.setting,
        seedlings=is_seedlings(obs),
        bolted=is_bolted(obs, match.key),
        soil_known=soil_feel is not None or obs.soil_surface != "not_visible",
        tender=tender,
        container=obs.container,
        roots_crowded=obs.pot_fit == "too_small",
        damage=damage,
        held_water=held_water and panel.primary == "leave_normal",
        # indoors, the month's care from our indoor table: UK months, so not for a photo
        # placed abroad; one with no place still gets it, as the app is for UK homes
        indoor_care=indoor_care_for(match.key, month)
        if indoors and (rec.location is None or in_uk(rec.location.lat, rec.location.lon))
        else None,
    )
    overrides = rule_overrides(rec.answer)
    if overrides:
        _say(progress, overrides)  # after the advisors' "treat it" (site walk 2, r5)
    # the quote decided against the action the headline shows, not the advisors': a rule
    # that changes the headline (cold, a resting herb, rule-led protect) drops it, since
    # the last gate judged the advisors' action (post-test change after round 8, review)
    shown = rec.answer.do[0].action if rec.answer.do else ""
    rec.trusted = trusted_page.quoted(
        reading.rec.trusted, trusted_page.plant_state(rec, shown, told)
    )
    rec.answer.trend = history.trend if history else None
    rec.answer.prediction = predict(rec.answer, obs)  # C2: what a later photo checks
    if rec.state is not None:
        rec.answer.assumptions = list(rec.state.assumptions)
    if rec.taken_at_source == "assumed":
        rec.answer.assumptions.append("the photo carried no date, so the date it was sent is used")
    _note_models(deps, rec, receipt.MODEL_STAGES, seen, {"advise": advised_ms})
    rec.failures = failures
    return rec


def _last_row(deps: Deps, run_id: str) -> int:
    try:
        return receipt.last_row_id(deps.trace_store.rows(run_id))
    except Exception:  # noqa: BLE001 - the receipt is extra: it never stops an answer
        log.exception("trace rows unreadable run=%s", run_id)
        return 0


def _note_models(
    deps: Deps,
    rec: AnalysisRecord,
    stages: frozenset[str],
    advise_after: int = 0,
    walls: dict[str, int] | None = None,
) -> None:
    """The model steps of `stages` onto the record's receipt, from this run's trace rows.
    The advisors only from after `advise_after`: a refine asks them again, and its answer
    is its own asks; the photo read and the trusted page ran once for every answer of it.
    A reading rebuilt from a stored answer (reading_from) has no receipt, and gets none:
    its read's steps are not known, and a part of the cost would read as the whole."""
    if rec.receipt is None:
        return
    try:
        rows = deps.trace_store.rows(rec.record_id)
        models = receipt.from_rows(rows, stages - {"advise"})
        if "advise" in stages:
            models += receipt.from_rows(rows, frozenset({"advise"}), advise_after)
        had = {s.stage for s in models}
        # a stage with no rows here (a stored answer read again after a deploy) keeps its line
        kept = [s for s in rec.receipt or [] if s.stage not in had]
        rec.receipt = receipt.assemble(kept, models, walls)
    except Exception:  # noqa: BLE001 - the receipt is extra: it never stops an answer
        log.exception("receipt failed run=%s", rec.record_id)


def analyse_with_reading(
    deps: Deps,
    image: bytes,
    mime: str,
    *,
    received: datetime,
    device: tuple[float, float] | None = None,
    place: str | None = None,
    told: Told | None = None,
    progress: Progress | None = None,
) -> tuple[AnalysisRecord, Reading | None]:
    got = read_photo(
        deps, image, mime, received=received, device=device, place=place, progress=progress
    )
    if isinstance(got, AnalysisRecord):
        return got, None
    return decide(deps, got, told, progress=progress), got


def analyse(
    deps: Deps,
    image: bytes,
    mime: str,
    *,
    received: datetime,
    device: tuple[float, float] | None = None,
    place: str | None = None,
    told: Told | None = None,
) -> AnalysisRecord:
    return analyse_with_reading(
        deps, image, mime, received=received, device=device, place=place, told=told
    )[0]
