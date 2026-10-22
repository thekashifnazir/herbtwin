"""FastAPI over the pipeline: a form, a result page, a JSON endpoint, and refine (spec
section 4): the questions under an answer re-run the advisor on the same photo reading."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import get_args

from fastapi import FastAPI, Form, HTTPException, Request, Response, UploadFile
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile as StarletteUploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from herbtwin import local_help, reminders
from herbtwin.answer import (
    NO_CURE_HEADLINE,
    NO_CURE_NEXT,
    NO_CURE_THANKS,
    TRAY_CHECK,
    advisor_lines,
    by_part,
    dont_if_dry,
    is_question,
    reply_to,
    top_doubt,
    watch_list,
)
from herbtwin.answer_cache import AnswerCache
from herbtwin.asks import questions_for
from herbtwin.auth import EXPIRED_LINK, AuthError, valid_email
from herbtwin.chat import LIMIT, MAX_CHARS, ChatError, clean_message, starters
from herbtwin.chat import sources_from as chat_sources
from herbtwin.compass import tap_from_sensor
from herbtwin.config import Settings, load_settings, parse_coordinate
from herbtwin.consequences import NO_DATA
from herbtwin.history import HistoryError
from herbtwin.light import light_said
from herbtwin.local_help import local_help_from
from herbtwin.mail import Mailer, MailError, mailer_from
from herbtwin.note_facts import echo as told_echo
from herbtwin.note_facts import note_facts
from herbtwin.pipeline import (
    LATE_TOLD,
    Deps,
    Reading,
    as_told,
    build_deps,
    changes_read,
    decide,
    how_led,
    name_in_doubt,
    read_photo,
    reading_from,
    trusted_check_on,
)
from herbtwin.plantbook import plantbook_on
from herbtwin.receipt import model_map
from herbtwin.replays import ReplayCache, replay_key
from herbtwin.reported import reported_from, subject_of
from herbtwin.schemas import (
    CHANGED_TEXT,
    LAST_WATERED_TEXT,
    MAX_QUESTION,
    SOIL_FEEL_TEXT,
    SPOT_SETTINGS,
    SQUEEZE_TEXT,
    AnalysisRecord,
    DidIt,
    HeadingTap,
    PotSize,
    Told,
)
from herbtwin.scoring import score_lines
from herbtwin.shops import DailyCap, shops_from
from herbtwin.sightings import sightings_from
from herbtwin.species import display_name, name_parts
from herbtwin.spot import (
    SpotTold,
    credits,
    medium_text,
    read_spot_photo,
    record_of,
    soil_colour_words,
    spot_from_reading,
    spot_from_record,
    view_spot,
)
from herbtwin.spot_questions import COMPASS_FIRST
from herbtwin.stages.advise import advisors_said
from herbtwin.stages.problem import signs, slugs_seen
from herbtwin.stages.trusted_page import read_more
from herbtwin.sun_arc import sun_arc
from herbtwin.tracing import trace_root, traced
from herbtwin.twin_bank import figure as twin_figure
from herbtwin.twin_chart import twin_chart
from herbtwin.usage import SupabaseUsage, UsageError, UsageStore, Verdict, uk_day, visitor_key
from herbtwin.voice import UNAVAILABLE as VOICE_UNAVAILABLE
from herbtwin.voice import Spoken, SpokenCache, VoiceError, persona_for, speak, voice_basis
from herbtwin.web import (
    checkup,
    claims,
    followup,
    judge,
    nav,
    remember,
    reminding,
    spotting,
    style,
    tapping,
    waiting,
)
from herbtwin.web.accounts import (
    ACCESS,
    Accounts,
    Person,
    accounts_from,
    clear_session,
    current_person,
    delete_account,
    finish_delete,
    set_session,
)
from herbtwin.web.edge import EdgeGuard, visitor_ip
from herbtwin.web.head import HeadAsGet
from herbtwin.web.held_photos import HeldPhotos
from herbtwin.web.progress import (
    HEAD,
    SIGNED_OUT_HEAD,
    SPOT_HEAD,
    asks_card,
    progress_response,
)
from herbtwin.web.traces import FlushTraces
from herbtwin.where import GeocodeError, for_model, in_uk, sample_files, strip_metadata

log = logging.getLogger(__name__)

MAX_BYTES = 12 * 1024 * 1024
# of the same plant: the main photo and up to two closer looks. They go to the photo model
# in one call, so they count as one photo read; each extra adds only its image tokens
MAX_PHOTOS = 3
TOO_MANY_PHOTOS = f"Send at most {MAX_PHOTOS} photos of the same plant."
# all the photos together: Cloud Run refuses an HTTP/1 body over 32 MiB with its own bare
# 413, so ours says it first, with the way back (the home page shrinks the extras too)
MAX_TOTAL_BYTES = 28 * 1024 * 1024
TOO_BIG_TOGETHER = "These photos are too big together (over 28 MB). Remove one and try again."
# "About this spot" ids come from the answer's id, so a repeat click reuses its spot
ABOUT_SPOT = uuid.uuid5(uuid.NAMESPACE_URL, "herbtwin:about-this-spot")
STILL_READING = "Still reading your photo, this page refreshes."
MAX_PLACE = 100


def _is_answer_id(answer_id: str) -> bool:
    """Answer ids are uuids; anything else is a stale or mistyped link, never a lookup
    (Supabase refuses a non-uuid with an error that would read as "history down")."""
    try:
        uuid.UUID(answer_id)
    except ValueError:
        return False
    return True


class _Static(StaticFiles):
    """Everything under /static is cached a month by the phone, not re-checked on every page.
    Only the fonts are fetched today (the stylesheet is inlined); a changed file gets a new
    name."""

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=2592000"
        return response


TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
TEMPLATES.env.globals["plant_name"] = display_name
TEMPLATES.env.globals["plant_parts"] = name_parts  # the answer page: the big name, the Latin
TEMPLATES.env.globals["how_led"] = how_led  # rule notes go in How we worked it out
TEMPLATES.env.globals["name_in_doubt"] = name_in_doubt  # "(not sure)" in the heading
TEMPLATES.env.globals["top_doubt"] = top_doubt  # "Mostly: …" beside How sure we are
TEMPLATES.env.globals["light_said"] = light_said  # the light we measured, on the band
TEMPLATES.env.globals["advisors_said"] = advisors_said  # who advised, in plain words
TEMPLATES.env.globals["advisor_lines"] = advisor_lines  # what each said, checked
TEMPLATES.env.globals["read_more"] = read_more  # the page Tavily found
TEMPLATES.env.globals["model_map"] = model_map  # each step's model, time and cost
TEMPLATES.env.globals["soil_colour_words"] = soil_colour_words  # no Munsell codes on the page
TEMPLATES.env.globals["no_cure_headline"] = NO_CURE_HEADLINE  # Compare says why it is empty
TEMPLATES.env.globals["no_cure_next"] = NO_CURE_NEXT  # What next under "Remove it"
TEMPLATES.env.globals["no_cure_thanks"] = NO_CURE_THANKS  # its "I did it" thanks
TEMPLATES.env.globals["dont_if_dry"] = dont_if_dry  # the Don't card with the soil unknown
TEMPLATES.env.globals["tray_check"] = TRAY_CHECK  # under "Bring it indoors" for a pot
TEMPLATES.env.globals["sample_files"] = sample_files  # home: a picked sample is set in London
TEMPLATES.env.globals["twin_chart"] = twin_chart  # Compare's 14-day line
TEMPLATES.env.globals["sun_arc"] = sun_arc  # the spot's clear-day sun over the year
TEMPLATES.env.globals["starters"] = starters  # "Ask about this plant": 3 to tap
TEMPLATES.env.globals["watch_list"] = watch_list  # Keep an eye on, one sign a line
TEMPLATES.env.globals["by_part"] = by_part  # See it by part: the plan sorted, nothing new
TEMPLATES.env.globals["chat_sources"] = chat_sources  # a kept reply's links, after a reload
TEMPLATES.env.globals["reply_to"] = reply_to  # "You asked: …" and the advisor's reply
TEMPLATES.env.globals["is_question"] = is_question  # "You asked" or "You said"
TEMPLATES.env.globals["note_facts"] = note_facts  # the chips follow their note
TEMPLATES.env.globals["told_echo"] = told_echo  # "You told us: in a pot, sunny"
TEMPLATES.env.globals["no_data"] = NO_DATA  # an "if you do" line that says nothing: hidden
TEMPLATES.env.globals["site_css"] = Markup(style.CSS)
TEMPLATES.env.globals["mark"] = Markup(style.MARK)
TEMPLATES.env.globals["has_session"] = nav.has_session  # the 404's "My plants" button
TEMPLATES.env.globals["nav_for_page"] = nav.site_nav  # `site_nav` in _nav.html
# signing in could not keep the answer it started from (claims.py)
NOT_KEPT = (
    "You're signed in. That answer could not be kept here: open the sign-in link on the "
    "device you used, or send the photo again."
)
NOT_KEPT_ACTION = "Continue"
# signed in, looking at a signed-out answer another browser made: where it can be kept
KEEP_ELSEWHERE = (
    "This answer was made in another browser, so it can be kept only there: open it on the "
    "device you used, or send the photo again."
)
NOT_KEPT_EXPIRED = (
    "You're signed in. That answer's hour was up, so it could not be kept: send the photo "
    "again and it will be."
)
EXPIRED = "This answer has expired; upload the photo again."
TAP_EXPIRED = "This photo has expired; upload it again."
# "Add photos for a surer answer" (21 Oct): the first photo is held for the answer's hour
MORE_PHOTOS_GONE = "The first photo has expired; upload all the photos again."
MORE_PHOTOS_NONE = "Choose 1 or 2 more photos of the same plant."
TAP_AGAIN = "Tap on the plant you mean, or use the whole photo."
NOT_FOUND = "We can't find that page. Check a plant from the menu above, or send a photo to see what you can grow."
BAD_LINK = "This link doesn't work. Unticking the box under the answer also stops the reminder."
UNSUBSCRIBED = "Done: no reminder for this answer."
ALREADY_OFF = "This reminder is already off."
# reminders not set up on this server: there is no reminder for the link to stop
NO_REMINDERS = "Reminder emails are off on this site, so there is nothing to stop."
UNSUBSCRIBE_DOWN = "We can't stop the reminder right now. Please try the link again later."
BUSY_DAY = "The garden's had a busy day. Try again tomorrow."
OUT_OF_BUDGET = "herbtwin has used its budget for model calls, so photo reads are paused for now."
REFINE_LIMIT = 5  # refines per answer: each runs the advisor three times
REFINE_LIMIT_TEXT = (
    f"This answer has been refined {REFINE_LIMIT} times, the most it can be. "
    "Upload the photo again to start afresh."
)
NOTHING_TO_REFINE = "Nothing to refine with: pick an answer or type a question."
PLACE_NOT_FOUND = "We couldn't find that place. Try a UK town or postcode."
MAIL_RETRY = timedelta(minutes=1)  # a failing Resend is retried at most this often
HEALTH_TTL_S = 30.0  # /health is public: the usage store is asked at most this often
CHOICES = {
    "soil_feel": SOIL_FEEL_TEXT,
    "last_watered": LAST_WATERED_TEXT,
    "changed": CHANGED_TEXT,
    "squeeze": SQUEEZE_TEXT,
}


class ChatIn(BaseModel):
    message: str = Field(max_length=4 * MAX_CHARS)  # a coarse cap; clean_message says why


def _sniff(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    raise HTTPException(400, "Upload a JPEG or PNG photo.")


async def _read_photo(photo: UploadFile) -> tuple[bytes, str]:
    data = await photo.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(400, "Photo is over 12 MB; resize it and try again.")
    if not data:
        raise HTTPException(400, "No photo received.")
    return data, _sniff(data)


async def _read_more(request: Request, main: bytes) -> list[tuple[bytes, str]]:
    """The other photos of the same plant ("more"), each checked as the main photo is. An
    empty field (sent by a form with nothing picked) is no photo; more than MAX_PHOTOS in
    all, or more than MAX_TOTAL_BYTES together with `main`, is refused before any is read."""
    form = await request.form()  # already parsed for the route's own fields
    files = [f for f in form.getlist("more") if isinstance(f, StarletteUploadFile) and f.filename]
    if len(files) > MAX_PHOTOS - 1:
        raise HTTPException(400, TOO_MANY_PHOTOS)
    if len(main) + sum(f.size or 0 for f in files) > MAX_TOTAL_BYTES:
        raise HTTPException(400, TOO_BIG_TOGETHER)
    more = [await _read_photo(f) for f in files]
    if len(main) + sum(len(data) for data, _ in more) > MAX_TOTAL_BYTES:  # no size given
        raise HTTPException(400, TOO_BIG_TOGETHER)
    return more


def _photos_key(data: bytes, more: list[tuple[bytes, str]]) -> str:
    """The raw uploads' hash for the repeat-photo shortcut: one photo's as it always was,
    so a main photo sent again with new closer looks is never the same answer."""
    key = hashlib.sha256(data).hexdigest()
    if not more:
        return key
    keys = [key, *(hashlib.sha256(extra).hexdigest() for extra, _ in more)]
    return hashlib.sha256(" ".join(keys).encode()).hexdigest()


# a short heading over the sentence (17 Oct walk); a status not listed keeps the sentence as
# the heading itself, so "Not found" never gets the wrong title (a page can pass its own)
OWN_HEADINGS = {EXPIRED: "Not here any more", NOT_FOUND: "Page not found"}
MESSAGE_HEADINGS = {
    400: "That didn't work",
    409: "That didn't work",
    429: "That's the limit for today",
    500: "Something went wrong",
    502: "Something is down",
    503: "Something is down",
}


DEVICE_REFUSED = "Could not read that location. Try again, or type a place instead."
COMPASS_REFUSED = "Could not use that compass reading. Pick a direction and try again."
TOLD_WORDS = {  # Told's fields as the page names them
    "soil_feel": "how the soil feels",
    "last_watered": "when it was last watered",
    "changed": "what changed",
    "question": "your question",
    "place": "the place",
    "squeeze": "the squeeze test",
    "heading": "the direction",
    "setting": "indoors or outdoors",
}


def _refusal(e: Exception) -> str:
    """What a refused form says in the log: the exception's kind and, for pydantic, the
    fields and error kinds. Never the values: they are the person's own words and place."""
    if isinstance(e, ValidationError):
        return f"{type(e).__name__} " + ", ".join(
            f"{'.'.join(map(str, err['loc'])) or '-'}:{err['type']}" for err in e.errors()
        )
    return type(e).__name__


def _device(lat: str | None, lon: str | None) -> tuple[float, float] | None:
    """The browser's location (the one-tap step of the chain), both or neither."""
    lat, lon = (lat or "").strip(), (lon or "").strip()
    if not lat and not lon:
        return None
    if not lat or not lon:
        raise HTTPException(400, "Send both latitude and longitude, or neither.")
    try:
        return parse_coordinate(lat, "lat", "lat"), parse_coordinate(lon, "lon", "lon")
    except ValueError as e:
        # our words, not the parser's: it repeats what was sent
        log.info("device location refused: %s", _refusal(e))
        raise HTTPException(400, DEVICE_REFUSED) from e


def _place(place: str | None) -> str | None:
    place = (place or "").strip()
    if len(place) > MAX_PLACE:
        raise HTTPException(400, f"Place name is over {MAX_PLACE} characters.")
    return place or None


def _told(**fields) -> Told:
    """Form fields to Told: an empty field is not given. Bad input is a 400 here."""
    given = {
        k: v for k, v in fields.items() if v is not None and (not isinstance(v, str) or v.strip())
    }
    try:
        return Told(**given)
    except ValidationError as e:
        # which of our fields, in our words: pydantic's own wording never reaches the page
        log.info("answer refused: %s", _refusal(e))
        bad = {str(err["loc"][0]) for err in e.errors() if err["loc"]}
        what = " and ".join(sorted(TOLD_WORDS.get(f, "one of the answers") for f in bad))
        raise HTTPException(
            400, f"Could not use {what or 'that answer'}. Check it and try again."
        ) from e


def _number(form: Mapping, name: str) -> float | None:
    raw = str(form.get(name) or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        raise HTTPException(400, f"Could not use that reading: {name} is not a number.") from None


def _heading(form: Mapping) -> HeadingTap | None:
    """The compass question's answer from a form (spot spec section 4): an 8-way tap
    (`direction`), a heading carried from an earlier refine (`heading`, `pitch`,
    `accuracy`), or the raw angles of a fresh tap (`sensor`, `alpha`, `beta`, `gamma`,
    `webkit_heading`, `webkit_accuracy`), worked out by herbtwin.compass. Bad input is a
    400; nothing given is None."""
    direction, sensor = (
        str(form.get("direction") or "").strip(),
        str(form.get("sensor") or "").strip(),
    )
    try:
        if direction:
            return HeadingTap(direction=direction)
        if str(form.get("heading") or "").strip():
            return HeadingTap(
                heading=_number(form, "heading"),
                pitch=_number(form, "pitch"),
                accuracy=_number(form, "accuracy"),
            )
        if sensor:
            h, p, acc = tap_from_sensor(
                sensor,
                *(
                    _number(form, k)
                    for k in ("alpha", "beta", "gamma", "webkit_heading", "webkit_accuracy")
                ),
            )
            return HeadingTap(heading=h, pitch=p, accuracy=acc)
    except ValidationError as e:
        # our words, not pydantic's
        log.info("compass reading refused: %s", _refusal(e))
        raise HTTPException(400, COMPASS_REFUSED) from e
    except ValueError as e:
        # herbtwin.compass's own plain sentences, never the input
        log.info("compass reading refused: %s", _refusal(e))
        raise HTTPException(400, f"Could not use that compass reading: {e}") from e
    return None


# the advisor models the answer page can name, keyed by the configured id, so the page
# names only what is really running
MODEL_NAMES = {
    "nvidia/nemotron-3-super-120b-a12b": "NVIDIA Nemotron 3 Super",
    "nvidia/Nemotron-3-Ultra-550b-a55b": "NVIDIA Nemotron 3 Ultra",
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B": "NVIDIA Nemotron 3 Nano",
}


def _advised_by(settings: Settings) -> str | None:
    """The advisor's name for "Decided by … on Nebius Token Factory": only when the advice
    really ran there, and only a model we can name."""
    return MODEL_NAMES.get(settings.advise_model) if settings.backend == "tokenfactory" else None


def _link_kind(kind: str) -> str:
    return kind if kind in ("email", "magiclink", "signup") else "email"


def _wants_page(request: Request) -> bool:
    """A person's browser, not the JSON API or a client that asks for JSON alone."""
    accept = request.headers.get("accept", "")
    wants_json = "application/json" in accept and "text/html" not in accept
    return not wants_json and not request.url.path.startswith("/api/")


_UNDER_ANSWER = re.compile(r"/answers/([0-9a-f]{32})/[\w-]+")
_UNDER_SPOT = re.compile(r"/spots/([0-9a-f]{32})/[\w-]+")
_UNDER_PLANT = re.compile(r"/plants/[^/]+/[\w-]+")


def _parent(path: str) -> str:
    """The page a form address belongs to: its answer, its spot, My plants, or home."""
    if m := _UNDER_ANSWER.fullmatch(path):
        return f"/answers/{m.group(1)}"
    if m := _UNDER_SPOT.fullmatch(path):
        return f"/spots/{m.group(1)}"
    if _UNDER_PLANT.fullmatch(path):
        return "/plants"
    return "/"


def _way_back(path: str) -> tuple[str, str]:
    """Where a failed form sends the person, and the button's words."""
    if path in ("/analyse", "/spots"):
        return "/", "Choose another photo"
    return _parent(path), "Back"


def _same_site(request: Request, site_url: str | None) -> bool:
    """True unless the browser says the form came from another origin. Browsers send
    Origin (or Referer) on a form POST; a request with neither is a script, not a page."""
    own = {str(request.base_url).rstrip("/")} | ({site_url.rstrip("/")} if site_url else set())
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/") in own
    referer = request.headers.get("referer")
    if referer:
        return any(referer == o or referer.startswith(o + "/") for o in own)
    return True


def _with_cookies(page, holder: Response):
    """Copy cookies a sign-in check set (a refresh, or a sign-out) onto the real response."""
    for c in holder.headers.getlist("set-cookie"):
        page.headers.append("set-cookie", c)
    return page


class RefineCounts:
    """Refines per answer, in memory (one instance runs the site). Bounded like the answer
    cache: the oldest answer's count is dropped first."""

    def __init__(self, limit: int = REFINE_LIMIT, max_entries: int = 2000) -> None:
        self.limit, self._max = limit, max_entries
        self._counts: OrderedDict[str, int] = OrderedDict()
        self._lock = threading.Lock()

    def take(self, answer_id: str) -> bool:
        """Count a refine; False once this answer has had its refines."""
        with self._lock:
            n = self._counts.get(answer_id, 0)
            if n >= self.limit:
                return False
            self._counts[answer_id] = n + 1
            self._counts.move_to_end(answer_id)
            while len(self._counts) > self._max:
                self._counts.popitem(last=False)
            return True

    def give_back(self, answer_id: str) -> None:
        """Return a slot taken for a refine that did not run (the budget refused it)."""
        with self._lock:
            n = self._counts.get(answer_id, 0)
            if n > 0:
                self._counts[answer_id] = n - 1


def _reminder_admin_from(settings: Settings) -> reminders.ReminderAdmin | None:
    """The unsubscribe page's way to turn a reminder off: the secret key, live only."""
    if not (settings.reminder_secret and settings.supabase_url and settings.supabase_secret_key):
        return None
    import httpx

    from herbtwin.adapters.reminder_admin import SupabaseReminderAdmin

    return SupabaseReminderAdmin(
        settings.supabase_url, settings.supabase_secret_key, httpx.Client(timeout=5)
    )


def _usage_from(settings: Settings) -> UsageStore | None:
    """The live counters: only with caps switched on and the Supabase secret key, so local
    runs never write to the hosted counters."""
    if not settings.caps_enabled:
        return None
    if not (settings.supabase_url and settings.supabase_secret_key):
        log.warning("HERBTWIN_CAPS_ENABLED is on without the Supabase URL and secret key: no caps")
        return None
    return SupabaseUsage(settings.supabase_url, settings.supabase_secret_key)


def create_app(
    deps: Deps | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    accounts: Accounts | None = None,
    usage: UsageStore | None = None,
    mail: Mailer | None = None,
    site_url: str | None = None,
    reminder_admin: reminders.ReminderAdmin | None = None,
) -> FastAPI:
    """The app. Tests pass `deps` and with it everything else (accounts, usage, mail and
    `site_url`, the site's own address); without `deps` all of it comes from settings."""
    app = FastAPI(title="herbtwin")
    if deps is None:
        settings = load_settings()
        app.state.deps = build_deps(settings)
        app.state.accounts = accounts if accounts is not None else accounts_from(settings)
        app.state.site_url = settings.site_url
        app.state.usage = usage if usage is not None else _usage_from(settings)
        app.state.mail = mail if mail is not None else mailer_from(settings)
        app.state.reminder_admin = (
            reminder_admin if reminder_admin is not None else _reminder_admin_from(settings)
        )
    else:
        # tests pass deps: accounts only from the caller, never from .env
        app.state.deps, app.state.accounts, app.state.site_url = deps, accounts, site_url
        settings = deps.settings
        app.state.usage, app.state.mail = usage, mail  # likewise only from the caller
        app.state.reminder_admin = reminder_admin
    app.add_middleware(EdgeGuard, secret=settings.edge_secret)
    style.know_font_types()
    app.mount("/static", _Static(directory=style.STATIC), name="static")
    app.add_middleware(FlushTraces, traces=lambda: app.state.deps.traces)
    app.add_middleware(HeadAsGet)  # outermost: a HEAD is a GET with no body
    edge, judge_code = settings.edge_secret, settings.judge_code
    secure = (app.state.site_url or "").startswith("https://")
    judge_tries = judge.Attempts()
    refines = RefineCounts()
    health: dict = {"at": None, "usage": "off"}
    mail_tried: dict = {"at": None}
    mail_lock = threading.Lock()
    app.state.answers = AnswerCache(clock)
    app.state.replays = ReplayCache(clock)  # the same photo today: the same answer
    app.state.held = HeldPhotos(clock)  # a signed-out answer's photo, for more photos
    app.state.voices = SpokenCache()
    voicing: set[str] = set()  # answers whose voice is being made now
    voicing_lock = threading.Lock()
    app.state.pending = remember.PendingChoices()
    app.state.spots = spotting.SpotCache(clock)
    app.state.taps = tapping.TapStore(clock)
    # the Tavily extras under the plan, one daily ceiling for both; None: off
    extras_cap = DailyCap(settings.shop_daily_searches)
    # app.state.deps, never deps: deps is None in production, set only by tests (21 Oct crash)
    http = app.state.deps.http
    app.state.shops = shops_from(settings, http, extras_cap)  # "Shops we found for this"
    app.state.local_help = local_help_from(settings, http, extras_cap)  # "Gardeners near"
    # "Seen recently in the UK": GBIF's UK records of the plant's pests, and news headlines
    # about them from Tavily when it is on
    app.state.sightings = sightings_from(settings, http)
    app.state.reported = reported_from(settings, http, extras_cap)
    app.state.waits = waiting.Waits()  # the wait page's quick questions

    def need_accounts() -> Accounts:
        if app.state.accounts is None:
            raise HTTPException(404)
        return app.state.accounts

    def message(
        request: Request,
        text: str,
        status: int = 200,
        back: str | None = None,
        back_text: str = "Back",
        signed_in: bool | None = None,
        heading: str | None = None,
    ):
        """A one-line page. The nav is on every page, so the button shows only where it goes
        somewhere the nav doesn't (`back`). `signed_in` overrides the nav's session hint, for a
        page sent while the session cookies are being cleared."""
        # an expired answer and a missing page are 404s, but each has its own heading
        heading = heading or OWN_HEADINGS.get(text) or MESSAGE_HEADINGS.get(status)
        context: dict = {"message": text, "back": back, "back_text": back_text, "heading": heading}
        # the read caps and the budget stop (22 Oct walk: a dead end): the judges' code lifts
        # both, and the day's cap says when it lifts by itself
        if text in (BUSY_DAY, OUT_OF_BUDGET):
            context["capped"] = "day" if text == BUSY_DAY else "budget"
        if signed_in is not None:
            context["signed_in"] = signed_in
        return TEMPLATES.TemplateResponse(request, "message.html", context, status_code=status)

    @app.exception_handler(StarletteHTTPException)
    async def not_found_page(request: Request, exc: StarletteHTTPException):
        """Asking for a page we don't have gets a page with the menu, not
        `{"detail": "Not Found"}`: a browser, and curl too (Accept */*). Only a client that
        asks for JSON alone, the JSON API, and every other error keep FastAPI's reply."""
        if not _wants_page(request):
            return await http_exception_handler(request, exc)
        if exc.status_code == 404 and exc.detail == "Not Found":
            return message(request, NOT_FOUND, 404)
        # a form address opened as a page (a refresh, a bookmark, the back button): its page
        if exc.status_code == 405 and request.method in ("GET", "HEAD"):
            return RedirectResponse(_parent(request.url.path), status_code=303)
        if exc.status_code in (400, 413):  # a bad or too-big upload: say so, and a way back
            back, label = _way_back(request.url.path)
            return message(request, str(exc.detail), exc.status_code, back, label)
        return await http_exception_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def missing_field_page(request: Request, exc: RequestValidationError):
        """A form sent without what it needs (no photo, no script) gets a page, not
        FastAPI's validation dump; the JSON API keeps the dump."""
        if not _wants_page(request):
            return await request_validation_exception_handler(request, exc)
        back, label = _way_back(request.url.path)
        photo = any("photo" in (e.get("loc") or ()) for e in exc.errors())
        said = "Choose a photo first." if photo else "Something the form needs was missing."
        return message(request, said, 422, back, label)

    def visitor(request: Request) -> str:
        """Who is asking, as stored: a keyed hash of the visitor's IP, never the IP."""
        return visitor_key(visitor_ip(request, edge), edge)

    def warn_budget(v: Verdict) -> None:
        """Email once at 80%: marked only after a mail went, so a failure is retried, at most
        once a minute (each try can hold a request for the mail's timeout)."""
        budget = settings.limits.budget_usd
        if app.state.mail is None:
            log.warning(
                "live budget: %.2f of %.2f USD spent; no mail configured", v.spent_usd, budget
            )
            return
        text = (
            f"herbtwin's live site has spent about ${v.spent_usd:.2f} of its ${budget:.2f} "
            "budget for model calls. At 100% photo reads, refines and chat stop for everyone "
            "without the judges' code."
        )
        with mail_lock:
            now = clock()
            if mail_tried["at"] is not None and now - mail_tried["at"] < MAIL_RETRY:
                return
            mail_tried["at"] = now
        try:
            app.state.mail("herbtwin has used 80% of its live budget", text)
        except MailError:
            log.exception("could not send the budget warning; trying again in a minute")
            return
        try:
            app.state.usage.mark_warned()
        except UsageError:
            log.exception("budget warning sent but not marked; it may be sent again")

    def spend(what: str, call: Callable[[UsageStore], Verdict]) -> str | None:
        """Count a model call against the caps and the budget (D59, D60): None to go ahead,
        else why not. No store, no caps; a store that cannot answer lets the call through.
        Blocking: runs on a worker thread."""
        store = app.state.usage
        if store is None:
            return None
        try:
            v = call(store)
        except UsageError:
            log.exception("usage store unavailable; allowing the %s", what)
            return None
        if v.warn:
            warn_budget(v)
        if v.allowed:
            return None
        return OUT_OF_BUDGET if v.reason == "budget" else BUSY_DAY

    async def photo_refusal(request: Request) -> str | None:
        """A photo read: once the upload is known to be a photo, before the stream starts."""
        day, who_, j = uk_day(clock()), visitor(request), judge.is_judge(request, judge_code)
        return await run_in_threadpool(
            spend,
            "photo read",
            lambda store: store.count_read(day, who_, settings.limits, judge=j),
        )

    def charge_hook(request: Request, what: str, cost: float):
        """For a refine or a chat message: run just before the model call, once the answer
        is found and the input and per-answer limits are fine, so a request that never
        reaches the model is never charged. Raises 429 when the budget is spent."""
        j = judge.is_judge(request, judge_code)

        def hook() -> None:
            refused = spend(what, lambda store: store.charge(cost, settings.limits, judge=j))
            if refused:
                raise HTTPException(429, refused)

        return hook

    def refine_hook(request: Request, answer_id: str):
        """The refine limit, then the budget. The slot is taken first (so two refines at
        once cannot both have the last one) and given back if the budget refuses."""
        charge = charge_hook(request, "refine", settings.limits.refine_cost_usd)

        def hook() -> None:
            if not refines.take(answer_id):
                raise HTTPException(429, REFINE_LIMIT_TEXT)
            try:
                charge()
            except HTTPException:
                refines.give_back(answer_id)
                raise

        return hook

    def usage_health() -> str:
        """ "off" with no usage store, "ok" when it answers, "down" when it does not (then the
        caps are silently off, so the deploy refuses to call a release live)."""
        store = app.state.usage
        if store is None:
            return "off"
        now = time.monotonic()
        if health["at"] is not None and now - health["at"] < HEALTH_TTL_S:
            return health["usage"]
        try:
            store.ping()
            state = "ok"
        except UsageError:
            log.exception("usage store down: photo-read caps and the budget are not enforced")
            state = "down"
        health.update(at=now, usage=state)
        return state

    async def who(request: Request):
        holder = HTMLResponse("")
        person = await run_in_threadpool(current_person, request, holder, app.state.accounts)
        return person, holder

    def run(
        data: bytes,
        mime: str,
        device,
        place,
        told: Told | None,
        progress=None,
        claim=None,
        *,
        first: Reading | None = None,
        offer_tap: bool = False,
        tapped: bool = False,
        more: list[tuple[bytes, str]] | None = None,
    ) -> AnalysisRecord | remember.Tap:
        """Read and answer a signed-out upload. `first` is a read already made ("Use the
        whole photo"); with `offer_tap`, a photo of different plants asks which first.
        `more`: the other photos of the same plant, read with this one."""
        more = more or []
        # a repeat of the same photo, place and question today gets the first answer again
        # under a new id (replays.py): the advisor's three asks could change the headline
        # the raw upload, EXIF and all: the read takes place, date and light from the
        # photo's own metadata, so two files that only look alike must never share an answer
        key = replay_key(_photos_key(data, more), device, place, told, clock().date())
        hit = app.state.replays.get(key) if first is None else None
        if hit is not None:
            rec, reading = hit.copy(uuid.uuid4().hex)
            if progress is not None:
                progress("Same photo as earlier today: showing the same answer")
            app.state.answers.put(reading, rec, claim=claim)
            if reading is not None:  # a plant answer, as below
                hold(rec.record_id, data, mime)
            return rec
        got = first or read_photo(
            app.state.deps, data, mime, received=clock(), device=device, place=place,
            progress=progress, tapped=tapped, more=more,
        )  # fmt: skip
        if isinstance(got, AnalysisRecord):
            rec, reading = got, None
        elif offer_tap and tapping.wants_tap(got.rec.observation, data):
            return remember.Tap(got)
        else:
            rec, reading = decide(app.state.deps, got, told, progress=progress), got
        app.state.answers.put(reading, rec, claim=claim)  # kept even without a reading: shown by id
        if reading is not None:  # a plant answer: more photos can be added for an hour
            hold(rec.record_id, data, mime)
        # the whole of a mixed photo: the next upload is asked again; an answer that took
        # the wait page's replies is not what the same photo alone would get
        if first is None and rec.told == told:
            app.state.replays.put(key, reading, rec)
        return rec

    def hold(answer_id: str, data: bytes, mime: str) -> None:
        """Hold the copy of the photo the model was sent (held_photos.py), never the upload."""
        try:
            app.state.held.put(answer_id, *for_model(strip_metadata(data, mime), mime))
        except ValueError:
            log.exception("could not hold the photo of %s", answer_id)

    def landed(person: Person, got, photo: tuple[bytes, str] | None = None) -> str:
        """Where a signed-in read goes next: the chooser, or its answer. With `photo`, the
        upload read: held for more photos, as a signed-out answer's is (run)."""
        if photo is not None and getattr(got, "reading", None) is not None:
            hold(got.reading.rec.record_id, *photo)
        if isinstance(got, remember.Choose):
            rid = got.reading.rec.record_id
            app.state.answers.put(got.reading, got.reading.rec, person.user_id)
            app.state.pending.put(rid, replace(got.pending, found=tuple(got.found)))
            return f"/answers/{rid}/plant"
        app.state.answers.put(got.reading, got.rec, person.user_id, got.last_decline)
        return f"/answers/{got.rec.record_id}"

    def wait_for_tap(reading: Reading, data, mime, device, place, told, claim, person) -> str:
        """Keep the photo for its tap and send the person to the tap page (tapping.py)."""
        tap_id = app.state.taps.put(
            tapping.TapWait(
                data, mime, reading, device, place, told, claim,
                person.user_id if person else None, tapping.share_of(data),
                tapping.least_share_of(data),
            )
        )  # fmt: skip
        return f"/taps/{tap_id}"

    def _bed_record(answer_id: str, person: Person | None) -> AnalysisRecord | None:
        """A bare bed's record: it stopped after the read, so there is no Reading."""
        entry = app.state.answers.get_for(answer_id, person.user_id if person else None)
        rec = entry.latest if entry else None
        obs = rec.observation if rec else None
        return rec if obs is not None and obs.bare_bed else None

    def cached(answer_id: str, person: Person | None = None):
        owner = person.user_id if person else None
        entry = app.state.answers.get_for(answer_id, owner)
        if entry is None or entry.reading is None:  # nothing to refine without a reading
            return None
        return entry.reading, entry.first_headline

    def refine(
        answer_id: str,
        told: Told,
        person: Person | None = None,
        before_model: Callable[[], None] = lambda: None,
    ) -> tuple[AnalysisRecord, int | None]:
        with trace_root("refine", answer_id=answer_id):  # its own trace, not the read's
            try:
                return refine_traced(answer_id, told, person, before_model)
            except GeocodeError as e:
                log.info("refine place lookup failed: %s", e)
                raise HTTPException(400, PLACE_NOT_FOUND) from None

    def refine_traced(
        answer_id: str,
        told: Told,
        person: Person | None,
        before_model: Callable[[], None],
    ) -> tuple[AnalysisRecord, int | None]:
        if told.is_empty():
            raise HTTPException(400, NOTHING_TO_REFINE)
        if person is not None:
            got = remember.refine_stored(
                app.state.deps,
                person,
                answer_id,
                told,
                lambda aid: cached(aid, person),
                before_model,
                lambda aid, reading: app.state.answers.set_reading(aid, reading),
            )
            if got is None:
                raise HTTPException(404, EXPIRED)
            app.state.answers.set_latest(answer_id, got[0])  # the chat's subject
            return got
        hit = cached(answer_id)
        if hit is None:
            raise HTTPException(404, EXPIRED)
        reading, first = hit
        if changes_read(told):  # the place, the switch, or where their note says it grows
            reading = as_told(app.state.deps, reading, told)
            app.state.answers.set_reading(answer_id, reading)
        before_model()
        rec = decide(app.state.deps, reading, told)
        rec.refined_from = first
        app.state.answers.set_latest(answer_id, rec)
        return rec, None

    def page(
        request: Request,
        rec: AnalysisRecord,
        last: int | None = None,
        chat=None,
        check=None,
        reminder=None,
        signed_in: bool = False,
        keep: str | None = None,  # signed out and this browser's own: "Sign in to keep this plant"
        kept: bool = False,  # just kept from signed out: offer the tab's photo copy
        keep_as: str | None = None,  # signed in, this browser's own and unkept: the account
        keep_elsewhere: bool = False,  # signed in, unkept, but made on another browser
        reminder_saved: bool = False,  # just saved without a script: "Tell us more" opens
    ):
        failed = {f.stage: f for f in rec.failures}
        # a slug photo with no plant: our signs and source instead of a dead end
        seen = rec.observation is not None and slugs_seen(rec.observation)
        slugs = signs()["slugs and snails"] if seen else None
        asks = (
            questions_for(rec.answer, rec.observation, last, spot=settings.spot_enabled)
            if rec.answer and rec.observation
            else []
        )
        return TEMPLATES.TemplateResponse(
            request,
            "result.html",
            {
                "rec": rec,
                "failed": failed,
                "asks": asks,
                "choices": CHOICES,
                "max_question": MAX_QUESTION,
                "chat": chat or [],
                "max_chat": MAX_CHARS,
                "check": check,
                "reminder": reminder,
                "twin": twin_figure(rec),
                "compass_first": COMPASS_FIRST,
                "spot_on": settings.spot_enabled,
                "slugs": slugs,
                # who decided it, named only when it really ran on Token Factory (#272 review)
                "advised_by": _advised_by(settings),
                # _extras_slot.html: shop links, local help, or both
                "extras_on": app.state.shops is not None or app.state.local_help is not None,
                # _reported_slot.html: UK records of this plant's pests (GBIF), and news
                # headlines about them (Tavily)
                "reported_on": app.state.sightings is not None or app.state.reported is not None,
                "signed_in": signed_in,
                "accounts": app.state.accounts is not None,
                "keep": keep,
                "kept": kept,
                "keep_as": keep_as,
                "keep_elsewhere": KEEP_ELSEWHERE if keep_elsewhere else None,
                "reminder_saved": reminder_saved,
                "voice": settings.voice_on,
                # "Add photos for a surer answer" (_more_photos.html): a plant answer whose
                # first photo is still held (its hour, signed in or out)
                "more_photos_on": rec.answer is not None
                and app.state.held.get(rec.record_id) is not None,
            },
        )

    @app.get("/health")
    @app.get("/healthz")  # local only: Cloud Run's front end answers /healthz itself
    def healthz() -> dict:
        return {"ok": True, "usage": usage_health()}

    @app.get("/grow", include_in_schema=False)
    def grow_page():
        """The old "What can I grow here?" tab: one photo box now takes a plant or a bed (a
        bed photo is offered the spot answer), so old links land on it."""
        return RedirectResponse("/", status_code=302)  # not 301: browsers would keep it

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        person, holder = await who(request)
        ask_sharing = False
        if person is not None:
            try:
                got = await run_in_threadpool(person.store.get_settings)
                ask_sharing = got.asked_at is None
            except HistoryError:
                log.warning("could not read the sharing choice; not asking this visit")
        page = TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {
                "accounts": app.state.accounts is not None,
                "person": person,
                "ask_sharing": ask_sharing,
                "spot_on": settings.spot_enabled,
                "plantbook_on": plantbook_on(settings),
                "sightings_on": settings.sightings,  # the GBIF credit
                "voice_on": settings.voice_on,
                "tavily_on": settings.tavily_key is not None,  # the same switch search reads
                "check_on": trusted_check_on(settings),
            },
        )
        return _with_cookies(page, holder)

    @app.get("/favicon.svg", include_in_schema=False)
    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(
            style.FAVICON,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @app.get("/robots.txt", include_in_schema=False)
    def robots():
        return PlainTextResponse(style.ROBOTS)

    @app.get("/privacy", response_class=HTMLResponse)
    def privacy(request: Request):
        return TEMPLATES.TemplateResponse(
            request,
            "privacy.html",
            {"voice_on": settings.voice_on, "sightings_on": settings.sightings},
        )

    @app.get("/credits", include_in_schema=False)
    def credits_page():
        """The credits are About's last section now (21 Oct, Kash): an old link lands there."""
        return RedirectResponse("/about#credits", status_code=301)

    @app.get("/about", response_class=HTMLResponse)
    def about(request: Request):
        """What herbtwin is, how it works, the models and what each does, how it was tested,
        what didn't work and what isn't done, then every credit with its licence (the
        footer links here from every page)."""
        return TEMPLATES.TemplateResponse(
            request,
            "about.html",
            {
                "spot_on": settings.spot_enabled,
                "plantbook_on": plantbook_on(settings),
                "sightings_on": settings.sightings,  # the GBIF credit
                "voice_on": settings.voice_on,
                "tavily_on": settings.tavily_key is not None,
                "check_on": trusted_check_on(settings),
            },
        )

    def judge_context(**state: bool) -> dict:
        """The judge page's state, and whether its bed sample can go to the spot answer."""
        return {**state, "spot_on": settings.spot_enabled}

    @app.get("/judge", response_class=HTMLResponse)
    def judge_page(request: Request):
        if not judge_code:
            raise HTTPException(404)
        return TEMPLATES.TemplateResponse(request, "judge.html", judge_context())

    @app.post("/judge", response_class=HTMLResponse)
    def judge_sign_in(request: Request, code: str = Form("")):
        if not judge_code:
            raise HTTPException(404)
        right = judge.right_code(code, judge_code)
        # only a wrong code uses a try (judges share one venue Wi-Fi IP); a blocked visitor
        # is refused whatever they typed, so the 11th guess learns nothing
        if not judge_tries.allow(uk_day(clock()), visitor(request), count=not right):
            return TEMPLATES.TemplateResponse(
                request, "judge.html", judge_context(blocked=True), status_code=429
            )
        if not right:
            return TEMPLATES.TemplateResponse(
                request, "judge.html", judge_context(wrong=True), status_code=400
            )
        done = TEMPLATES.TemplateResponse(request, "judge.html", judge_context(done=True))
        judge.set_judge(done, judge_code, secure)
        return done

    @app.get("/auth/sign-in", response_class=HTMLResponse)
    def sign_in_page(request: Request, next: str | None = None):  # noqa: A002 - the URL's own name
        acc = need_accounts()
        page = TEMPLATES.TemplateResponse(request, "sign_in.html")
        # where to come back to after the email round trip: an answer's path only
        claims.keep_next(
            request, page, next, settings.reminder_secret, acc.secure, app.state.site_url
        )
        return page

    @app.post("/auth/sign-in", response_class=HTMLResponse)
    async def sign_in(request: Request, email: str = Form("")):
        acc = need_accounts()
        try:
            address = valid_email(email)
        except ValueError as e:
            return message(request, str(e), 400, "/auth/sign-in", "Try again")
        try:
            await run_in_threadpool(acc.auth.send_link, address)
        except AuthError as e:
            return message(request, str(e), 503, "/auth/sign-in", "Try again")
        # a short H1, the address under it (19 Oct walk); from an answer, how to keep it:
        # the link brings you back to it, and the Keep button there adds it (#254)
        sent = f"We sent a sign-in link to {address}."
        if claims.has_next(request, settings.reminder_secret):
            sent += " Open it on this device, then tap Keep on the answer to add it to My plants."
        return message(request, sent, heading="Check your email")

    @app.get("/auth/callback", response_class=HTMLResponse)
    async def callback_page(
        request: Request, token_hash: str = "", type: str = "email", error: str = ""
    ):
        """Opening the emailed link only shows a button: mail scanners open links before
        the person does, and only the button's POST spends the one-time token."""
        need_accounts()
        if error or not token_hash:
            return message(request, EXPIRED_LINK, 400, "/auth/sign-in", "Send a new link")
        return TEMPLATES.TemplateResponse(
            request, "sign_in_confirm.html", {"token_hash": token_hash, "kind": _link_kind(type)}
        )

    @app.post("/auth/callback", response_class=HTMLResponse)
    async def callback(request: Request, token_hash: str = Form(""), type: str = Form("email")):
        acc = need_accounts()
        if not _same_site(request, app.state.site_url):
            # a sign-in posted from another site would sign this browser into someone else's
            # account (login forgery)
            return message(request, "That sign-in did not come from this site.", 403)
        if not token_hash:
            return message(request, EXPIRED_LINK, 400, "/auth/sign-in", "Send a new link")
        try:
            s = await run_in_threadpool(acc.auth.verify, token_hash, _link_kind(type))
        except AuthError as e:
            status = 400 if e.expired else 503
            return message(request, str(e), status, "/auth/sign-in", "Send a new link")
        r = RedirectResponse("/", status_code=303)
        # back to the answer the sign-in started from; keeping it is a separate, explicit tap
        back = claims.take_next(request, r, settings.reminder_secret)
        if back is not None:
            r.headers["location"] = back
        set_session(r, s, acc.secure)
        return r

    @app.post("/auth/sign-out")
    async def sign_out(request: Request):
        acc = need_accounts()
        token = request.cookies.get(ACCESS)
        if token:
            await run_in_threadpool(acc.auth.sign_out, token)
        r = RedirectResponse("/", status_code=303)
        clear_session(r)
        claims.forget(r)
        return r

    @app.get("/plants", response_class=HTMLResponse)
    async def plants_page(request: Request):
        need_accounts()
        person, holder = await who(request)
        if person is None:
            return _with_cookies(RedirectResponse("/auth/sign-in", status_code=303), holder)

        def load():
            rows = []
            for p in person.store.list_plants():
                visits = person.store.answers_for(p.id)[:5]
                path = visits[0].photo_path if visits else None
                lines = score_lines(person.store.scores_for(p.id))
                box = latest_box(visits[0].id) if visits else None
                rows.append((p, visits, person.store.photo_url(path) if path else None, lines, box))
            # newest first, as the page says: by each plant's latest photo; none yet, last
            rows.sort(key=lambda r: (bool(r[1]), r[1][0].taken_at if r[1] else r[0].created_at))
            rows.reverse()
            return rows

        def latest_box(answer_id: str):
            # the "email me" box for the newest visit; the plants still show without it
            try:
                return reminding.box_for(person, answer_id, settings.reminder_secret)
            except HistoryError:
                log.exception("could not read the reminder for the plants page")
                return None

        def sharing_choice():
            try:
                return person.store.get_settings()
            except HistoryError:
                # the plants still show; only the sharing switch waits for next time
                log.exception("could not read the sharing choice for the plants page")
                return None

        try:
            rows = await run_in_threadpool(load)
        except HistoryError:
            log.exception("could not load the plants page")
            return message(request, remember.HISTORY_DOWN, 503)
        sharing = await run_in_threadpool(sharing_choice)
        return _with_cookies(
            TEMPLATES.TemplateResponse(
                request, "plants.html", {"plants": rows, "sharing": sharing, "person": person}
            ),
            holder,
        )

    @app.post("/plants/{plant_id}/rename", response_class=HTMLResponse)
    async def rename_plant(request: Request, plant_id: str, name: str = Form("")):
        need_accounts()
        person, holder = await who(request)
        if person is None:
            return RedirectResponse("/auth/sign-in", status_code=303)
        name = " ".join(name.split())
        if not 1 <= len(name) <= 60:
            return message(
                request, "A plant name is 1 to 60 characters.", 400, "/plants", "Back to my plants"
            )
        try:
            await run_in_threadpool(person.store.rename_plant, plant_id, name)
        except HistoryError:
            log.exception("could not rename the plant")
            return message(request, remember.HISTORY_DOWN, 503, "/plants", "Back to my plants")
        return _with_cookies(RedirectResponse("/plants", status_code=303), holder)

    @app.post("/plants/{plant_id}/delete", response_class=HTMLResponse)
    async def delete_plant(request: Request, plant_id: str):
        need_accounts()
        person, holder = await who(request)
        if person is None:
            return RedirectResponse("/auth/sign-in", status_code=303)
        try:
            await run_in_threadpool(person.store.delete_plant, plant_id)
        except HistoryError:
            log.exception("could not delete the plant")
            return message(request, remember.HISTORY_DOWN, 503, "/plants", "Back to my plants")
        return _with_cookies(RedirectResponse("/plants", status_code=303), holder)

    @app.post("/account/sharing", response_class=HTMLResponse)
    async def sharing(request: Request, share: str = Form(""), back: str = Form("/")):
        need_accounts()
        if not _same_site(request, app.state.site_url):
            # a forged form would opt someone in to sharing without their say
            return message(request, "That change did not come from this site.", 403)
        back_to = back if back in ("/", "/plants") else "/"
        # a button back to My plants only: the nav already leads home
        again = ("/plants", "Back to my plants") if back_to == "/plants" else (None, "Back")
        person, holder = await who(request)
        if person is None:
            return _with_cookies(RedirectResponse("/auth/sign-in", status_code=303), holder)
        if share not in ("yes", "no"):
            return message(request, "Choose yes or no.", 400, *again)
        try:
            await run_in_threadpool(person.store.set_sharing, share == "yes", clock())
        except HistoryError:
            log.exception("could not save the sharing choice")
            return message(request, remember.HISTORY_DOWN, 503, *again)
        if request.headers.get("x-herbtwin-fetch") == "1":  # the home page's script: saved
            return _with_cookies(Response(status_code=204), holder)
        return _with_cookies(RedirectResponse(back_to, status_code=303), holder)

    @app.get("/account/delete", response_class=HTMLResponse)
    async def account_delete_page(request: Request):
        need_accounts()
        # signed out there is no account to delete: sign in first, as /plants does (19 Oct walk)
        person, holder = await who(request)
        if person is None:
            return _with_cookies(RedirectResponse("/auth/sign-in", status_code=303), holder)
        return _with_cookies(TEMPLATES.TemplateResponse(request, "delete_account.html"), holder)

    @app.post("/account/delete", response_class=HTMLResponse)
    async def account_delete(request: Request, confirm: str = Form("")):
        acc = need_accounts()
        if confirm.strip().casefold() != "delete":
            # one tap must never lose everything: the word is typed on the confirm page
            return message(request, "Type delete to confirm.", 400, "/account/delete", "Try again")
        person, _ = await who(request)
        if person is None:
            # a retry after the account went: the session no longer resolves, but the
            # token still names the account, so confirm it is gone and sweep again
            token = request.cookies.get(ACCESS)
            sub = acc.auth.token_subject(token) if token else None
            if sub is None:
                return RedirectResponse("/auth/sign-in", status_code=303)
            try:
                gone = await run_in_threadpool(finish_delete, acc, sub)
            except (AuthError, HistoryError) as e:
                log.exception("account delete retry failed")
                return message(request, str(e), 503)
            if not gone:
                return RedirectResponse("/auth/sign-in", status_code=303)
            done = message(
                request,
                "Your account was already deleted; everything in it is gone.",
                signed_in=False,
            )
            clear_session(done)
            return done
        try:
            await run_in_threadpool(delete_account, acc, person.user_id)
        except (AuthError, HistoryError) as e:
            log.exception("account delete failed")
            return message(request, str(e), 503, "/plants", "Back to my plants")
        done = message(request, "Your account and everything in it are deleted.", signed_in=False)
        clear_session(done)
        return done

    @app.post("/analyse", response_class=HTMLResponse)
    async def analyse_page(
        request: Request,
        photo: UploadFile,
        lat: str | None = Form(None),
        lon: str | None = Form(None),
        place: str | None = Form(None),
        question: str | None = Form(None),
    ):
        device, where, told = _device(lat, lon), _place(place), _told(question=question)
        data, mime = await _read_photo(photo)  # a bad upload never uses a slot
        more = await _read_more(request, data)  # all the photos are one read: one slot
        refused = await photo_refusal(request)
        if refused:
            return message(request, refused, 429)
        told_or_none = None if told.is_empty() else told
        person, holder = await who(request)
        history_down = getattr(request.state, "history_down", False)

        # signed out: this browser's key, so signing in from the answer can keep it (claims.py)
        key = (
            claims.give_key(request, holder, settings.reminder_secret, app.state.accounts.secure)
            if person is None and app.state.accounts is not None and settings.reminder_secret
            else None
        )

        owner = person.user_id if person is not None else None
        wait_id = uuid.uuid4().hex  # unguessable: it unlocks the replies to this wait
        app.state.waits.start(wait_id, owner, told_or_none)

        def work(progress: Callable[[str], None]) -> str:
            """The read, with the wait page's replies (waiting.py)."""

            def late(told: Told | None) -> Told | None:
                got = app.state.waits.take(wait_id, told)
                if got != told:
                    progress("Using what you told us")
                return got

            LATE_TOLD.set(late)  # this read's own context (progress.stream copies it)

            def asks_first() -> Told | None:  # several plants or the chooser: replies so far
                return app.state.waits.take(wait_id, told_or_none, answering=False)

            target = read(progress, asks_first)
            app.state.waits.finish(wait_id, target)
            return target

        def read(progress: Callable[[str], None], told_now: Callable[[], Told | None]) -> str:
            """The read itself, on the progress page's thread; returns the next page. A
            photo of several plants asks which first, with the replies so far."""
            if person is None:
                rec = run(
                    data, mime, device, where, told_or_none, progress, claim=key, offer_tap=True,
                    more=more,
                )  # fmt: skip
                if isinstance(rec, remember.Tap):  # different plants: which one? (tapping.py)
                    return wait_for_tap(
                        rec.reading, data, mime, device, where, told_now(), key, None
                    )
                if history_down:
                    rec.notes.append(remember.HISTORY_DOWN)
                return f"/answers/{rec.record_id}"
            got = remember.start(
                app.state.deps,
                person,
                data,
                mime,
                received=clock(),
                device=device,
                place=where,
                told=told_or_none,
                progress=progress,
                offer_tap=True,
                more=more,
            )
            if isinstance(got, remember.Tap):
                return wait_for_tap(
                    got.reading, data, mime, device, where, told_now(), None, person
                )
            if isinstance(got, remember.Choose):  # which plant: decided after, with the replies
                got = replace(got, pending=replace(got.pending, told=told_now()))
            return landed(person, got, (data, mime))

        traces = app.state.deps.traces
        settle = traces.settle if traces is not None else None
        head = SIGNED_OUT_HEAD if person is None else HEAD
        asks = asks_card(wait_id)
        return _with_cookies(
            progress_response(work, settle, asks, head=head, advisor=_advised_by(settings)),
            holder,
        )

    @app.post("/waits/{wait_id}/told")
    async def wait_told(
        request: Request,
        wait_id: str,
        soil_feel: str | None = Form(None),
        last_watered: str | None = Form(None),
    ):
        """A quick question answered on the wait page (by fetch): into this answer while the
        advisor has not started, else kept for the reveal."""
        if not _is_answer_id(wait_id) or not _same_site(request, app.state.site_url):
            return JSONResponse({"counted": "gone"}, status_code=404)
        # "not sure" on either (here, on the wait page) sends no reading for it, and an
        # earlier reply to it no longer counts: the advice is never told "not sure" (21 Oct)
        asked = {"soil_feel": soil_feel, "last_watered": last_watered}
        cleared = frozenset(q for q, v in asked.items() if v == "not_sure")
        told = _told(**{q: None if q in cleared else v for q, v in asked.items()})
        if told.is_empty() and not cleared:
            return JSONResponse({"counted": "gone"}, status_code=400)
        person, holder = await who(request)
        owner = person.user_id if person is not None else None
        counted = app.state.waits.reply(wait_id, owner, told, cleared)
        return _with_cookies(JSONResponse({"counted": counted}), holder)

    @app.post("/waits/{wait_id}/see")
    async def wait_see(request: Request, wait_id: str):
        """ "See your answer" after a reply came too late for the advice: check the advice
        again with it (a refine, with its limit and budget), then the page opens it."""
        if not _is_answer_id(wait_id) or not _same_site(request, app.state.site_url):
            return JSONResponse({"go": None}, status_code=404)
        person, holder = await who(request)
        owner = person.user_id if person is not None else None
        target, told = app.state.waits.late(wait_id, owner)
        if target is None:
            return JSONResponse({"go": None}, status_code=404)
        answer = re.fullmatch(r"/answers/([0-9a-f]{32})", target)
        if told is not None and answer:
            try:
                await run_in_threadpool(
                    refine, answer[1], told, person, refine_hook(request, answer[1])
                )
            except HTTPException as e:  # the limit, the budget, or a read with no plant
                log.info("wait replies not applied: %s", e.detail)
        return _with_cookies(JSONResponse({"go": target}), holder)

    async def extras_record(request: Request, answer_id: str):
        """The answer an after-load fragment is for, as its owner may see it (the answer
        cache, then a signed-in person's store), and the cookie holder for the reply."""
        person, holder = await who(request)
        owner = person.user_id if person is not None else None
        entry = app.state.answers.get_for(answer_id, owner) or (
            app.state.answers.get_for(answer_id, None) if person is not None else None
        )
        rec = entry.latest if entry is not None else None
        if rec is None and person is not None:
            try:
                stored = await run_in_threadpool(person.store.get_answer, answer_id)
            except HistoryError:
                log.info("%s: stored answer unavailable", request.url.path.rsplit("/", 1)[-1])
                stored = None
            rec = followup._record(stored) if stored is not None else None
        return rec, holder

    @app.get("/answers/{answer_id}/reported", response_class=HTMLResponse)
    async def answer_reported(request: Request, answer_id: str):
        """Seen recently in the UK (_reported_slot.html loads this after the page opens): UK
        records of the identified plant's pests and diseases from GBIF, and up to two news
        headlines about them from Tavily. 204, and the slot stays hidden, when off, when no
        plant was identified, when nothing is found, or when anything fails."""
        seen, finder = app.state.sightings, app.state.reported
        if (seen is None and finder is None) or not _is_answer_id(answer_id):
            return Response(status_code=204)
        rec, holder = await extras_record(request, answer_id)
        loc = rec.location if rec is not None else None
        if rec is None or rec.answer is None or (loc and not in_uk(loc.lat, loc.lon)):
            return _with_cookies(Response(status_code=204), holder)  # UK sources: UK only
        if rec.answer.photo_issue:  # a rough read: the plant is a guess, so are its pests
            return _with_cookies(Response(status_code=204), holder)
        subject = subject_of(rec)
        if subject is None:  # no plant we know: nothing to ask about
            return _with_cookies(Response(status_code=204), holder)

        def sightings_of() -> list:
            return seen.seen(subject.problems) if seen is not None else []

        def news_of() -> list:
            return finder.reports(subject) if finder is not None else []

        async def ask(fn, label: str) -> list:
            try:
                return await run_in_threadpool(fn)  # within its own TIMEOUT_S
            except Exception:  # noqa: BLE001 - extra only: never an error on the page
                log.exception("seen recently: %s broke", label)
                return []

        sightings, reports = await asyncio.gather(
            ask(sightings_of, "sightings"), ask(news_of, "news")
        )
        if not sightings and not reports:
            return _with_cookies(Response(status_code=204), holder)
        shown = TEMPLATES.TemplateResponse(
            request, "_reported.html", {"sightings": sightings, "reports": reports}
        )
        return _with_cookies(shown, holder)

    @app.get("/answers/{answer_id}/extras", response_class=HTMLResponse)
    async def answer_extras(request: Request, answer_id: str):
        """The Tavily extras under the plan (_extras_slot.html loads this after the page
        opens): shop links for the answer's actions, and gardeners near a typed UK town.
        204, and nothing shows, when there is nothing to show or anything fails."""
        finder, local = app.state.shops, app.state.local_help
        if (finder is None and local is None) or not _is_answer_id(answer_id):
            return Response(status_code=204)
        rec, holder = await extras_record(request, answer_id)
        loc = rec.location if rec is not None else None
        if rec is None or rec.answer is None or (loc and not in_uk(loc.lat, loc.lon)):
            return _with_cookies(Response(status_code=204), holder)  # UK only
        # the town the person typed: for the garden centres link, and for local help when on
        typed_town = local_help.town_of(loc)
        town = typed_town if local is not None else None
        outdoor = rec.observation is not None and rec.observation.setting == "outdoor"

        async def shop_links():
            if finder is None:
                return []
            actions = [c.action for c in rec.answer.do]
            return await run_in_threadpool(finder.links, actions, "UK", outdoor)

        async def near():
            if town is None:
                return []
            return await run_in_threadpool(local.links, town)  # within local_help.TIMEOUT_S

        links, helpers = await asyncio.gather(shop_links(), near())
        if not links and not helpers:
            return _with_cookies(Response(status_code=204), holder)
        shown = TEMPLATES.TemplateResponse(
            request,
            "_extras.html",
            {
                "links": links,
                "paid": any(x.paid for x in links),
                # something to buy and a typed town: garden centres near it first, a map
                # search the person opens; nothing is sent until they tap it (21 Oct, Kash)
                "centres": local_help.centres_near(typed_town) if links and typed_town else None,
                "centres_town": typed_town,
                "town": town,
                "helpers": helpers,
                "rhs_hiring": local_help.RHS_HIRING,
            },
        )
        return _with_cookies(shown, holder)

    @app.get("/answers/{answer_id}", response_class=HTMLResponse)
    async def answer_page(request: Request, answer_id: str):
        """An answer by id: the streamed upload page jumps here, and a reload costs nothing.
        Signed in: the account's own answers only, from the cache or else stored history.
        Signed out: the unguessable id is the key, as for refine."""
        if not _is_answer_id(answer_id):
            return message(request, EXPIRED, 404, "/", "Check a plant")
        person, holder = await who(request)
        entry = app.state.answers.get_for(answer_id, person.user_id if person else None)
        if entry is None and person is not None:
            # read while sign-in was down, so kept as signed out: the id already shows it
            entry = app.state.answers.get_for(answer_id, None)
        if entry is not None:
            rec, last = entry.latest, entry.last_decline
        elif person is not None:
            try:
                stored = await run_in_threadpool(person.store.get_answer, answer_id)
            except HistoryError:
                log.exception("could not read the stored answer")
                return message(request, remember.HISTORY_DOWN, 503)
            if stored is None:
                return message(request, EXPIRED, 404, "/", "Check a plant")
            rec, last = followup._record(stored), None
        elif getattr(request.state, "history_down", False):
            # sign-in failed since the read: the answer may well be the person's own
            return message(request, remember.HISTORY_DOWN, 503)
        else:
            return message(request, EXPIRED, 404, "/", "Check a plant")
        chat = await run_in_threadpool(followup.chat_so_far, person, answer_id, app.state.answers)
        check = await run_in_threadpool(checkup.checkup_for, person, answer_id)
        box = await reminder_box(person, answer_id)
        mine = claims.browser_key(request, settings.reminder_secret)
        keep = (
            f"/auth/sign-in?next=/answers/{answer_id}"
            if person is None and claims.can_claim(entry, mine)
            else None
        )
        kept = (
            person is not None
            and request.query_params.get("kept") == "1"
            and entry is not None
            and entry.owner == person.user_id
        )
        # signed in on an unkept signed-out answer: keep it by an explicit tap naming the
        # account, or say why this browser cannot (claims.py)
        unkept = person is not None and entry is not None and entry.owner is None
        keep_as = person.email if unkept and claims.can_claim(entry, mine) else None
        elsewhere = unkept and keep_as is None and entry is not None and entry.claim is not None
        # a flag, never echoed: only this one value means the reminder box was just saved
        saved = request.query_params.get("saved") == "reminder"
        shown = page(
            request,
            rec,
            last,
            chat,
            check,
            box,
            person is not None,
            keep,
            kept,
            keep_as,
            elsewhere,
            reminder_saved=saved,
        )
        # the Keep button names the account: never inside another site's frame
        shown.headers["X-Frame-Options"] = "DENY"
        shown.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        return _with_cookies(shown, holder)

    @app.post("/answers/{answer_id}/keep", response_class=HTMLResponse)
    async def keep_answer(request: Request, answer_id: str):
        """ "Keep this in My plants": a signed-out answer this browser got, kept once, as it
        was shown (claims.py). A new plant, or "which plant is it?" first."""
        if not _is_answer_id(answer_id) or not _same_site(request, app.state.site_url):
            raise HTTPException(403, "That did not come from this site.")
        person, holder = await who(request)
        if person is None:
            return _with_cookies(
                RedirectResponse(f"/auth/sign-in?next=/answers/{answer_id}", status_code=303),
                holder,
            )
        key = claims.browser_key(request, settings.reminder_secret)
        entry = app.state.answers.get(answer_id)
        back = f"/answers/{answer_id}"
        if entry is None:
            return message(request, NOT_KEPT_EXPIRED, 404, "/", "Check a plant", signed_in=True)
        if entry.owner == person.user_id:
            return _with_cookies(RedirectResponse(back, status_code=303), holder)
        if key is None or not claims.can_claim(entry, key) or entry.reading is None:
            return message(request, NOT_KEPT, 409, back, NOT_KEPT_ACTION, signed_in=True)
        reading, rec = entry.reading, entry.latest
        try:
            found = await run_in_threadpool(remember.likely_plants, person, reading, clock())
        except HistoryError:
            log.exception("could not read the plants to keep run=%s", answer_id)
            return message(request, remember.HISTORY_DOWN, 503, back, "Back", signed_in=True)
        if found:
            pending = remember.Pending(person.user_id, None, rec.told, tuple(found), claimed=True)
            app.state.pending.put(answer_id, pending)
            return _with_cookies(RedirectResponse(f"{back}/plant", status_code=303), holder)
        if not app.state.answers.claim(answer_id, key, person.user_id):  # lost a race
            return message(request, NOT_KEPT, 409, back, NOT_KEPT_ACTION, signed_in=True)
        try:
            chat = list(entry.chat)  # the signed-out chat so far goes with it
            await run_in_threadpool(remember.keep_new, person, reading, rec, clock(), chat)
        except HistoryError:
            log.exception("could not keep the answer run=%s", answer_id)
            app.state.answers.unclaim(answer_id, person.user_id)  # try again from the answer
            return message(request, remember.HISTORY_DOWN, 503, back, "Back", signed_in=True)
        return _with_cookies(RedirectResponse(f"{back}?kept=1", status_code=303), holder)

    @app.post("/answers/{answer_id}/photo")
    async def add_kept_photo(request: Request, answer_id: str, photo: UploadFile):
        """ "Add your photo to this plant?": the tab's own copy, sent only by that click, to an
        answer kept from signed out (claims.py). Signed-out photos are never kept otherwise."""
        if not _is_answer_id(answer_id) or not _same_site(request, app.state.site_url):
            raise HTTPException(403, "That did not come from this site.")
        person, holder = await who(request)
        if person is None:
            raise HTTPException(401, "Sign in first.")
        data, mime = await _read_photo(photo)
        try:
            added = await run_in_threadpool(remember.add_photo, person, answer_id, data, mime)
        except ValueError as e:
            raise HTTPException(400, "That photo could not be read.") from e
        except HistoryError as e:
            log.exception("could not add the kept photo run=%s", answer_id)
            raise HTTPException(503, remember.HISTORY_DOWN) from e
        if not added:
            raise HTTPException(404, "No answer of yours here that is waiting for its photo.")
        return _with_cookies(Response(status_code=204), holder)

    async def choose_kept(request, answer_id, plant_id, person, holder, pending):
        """ "Which plant is it?" for an answer kept from signed out: stored as it was shown,
        on the chosen plant, never decided again; claimed atomically just before the write."""
        back = f"/answers/{answer_id}"
        if not _same_site(request, app.state.site_url):
            raise HTTPException(403, "That did not come from this site.")
        key = claims.browser_key(request, settings.reminder_secret)
        entry = app.state.answers.get(answer_id)
        if pending.user_id != person.user_id or entry is None or entry.reading is None:
            return message(request, NOT_KEPT_EXPIRED, 404, "/", "Check a plant", signed_in=True)
        if key is None or not claims.can_claim(entry, key):
            return message(request, NOT_KEPT, 409, back, NOT_KEPT_ACTION, signed_in=True)
        if plant_id != "new" and plant_id not in {p.id for p, _, _ in pending.found}:
            return message(request, "No such plant.", 404, f"{back}/plant", "Choose again")
        if app.state.pending.take(answer_id) is None or not app.state.answers.claim(
            answer_id, key, person.user_id
        ):  # a second tap, or another tab, got there first
            return message(request, NOT_KEPT, 409, back, NOT_KEPT_ACTION, signed_in=True)
        reading, rec, chat = entry.reading, entry.latest, list(entry.chat)

        def store() -> None:
            if plant_id == "new":
                remember.keep_new(person, reading, rec, clock(), chat)
            else:
                remember.keep_for_plant(person, reading, rec, plant_id, clock(), chat)

        try:
            await run_in_threadpool(store)
        except HistoryError:
            log.exception("could not keep the answer on a plant run=%s", answer_id)
            app.state.answers.unclaim(answer_id, person.user_id)
            app.state.pending.put(answer_id, pending)  # the choice can be made again
            return message(request, remember.HISTORY_DOWN, 503, f"{back}/plant", "Try again")
        return _with_cookies(RedirectResponse(f"{back}?kept=1", status_code=303), holder)

    @app.get("/answers/{answer_id}/plant", response_class=HTMLResponse)
    async def plant_choice_page(request: Request, answer_id: str):
        """ "Which plant is this?" for a streamed upload. Shown, not used up: the POST to
        the same address makes the choice."""
        person, holder = await who(request)
        pending = app.state.pending.get(answer_id)
        if (
            person is None
            or pending is None
            or pending.user_id != person.user_id
            or not (
                claims.can_claim(
                    app.state.answers.get(answer_id),
                    claims.browser_key(request, settings.reminder_secret),
                )
                if pending.claimed
                else cached(answer_id, person) is not None
            )
        ):
            return message(request, EXPIRED, 404, "/", "Check a plant")
        # this photo and what it was read as, in the answer's own words (judge pre-walk, 19 Oct)
        entry = app.state.answers.get(answer_id)
        reading = entry.reading if entry else None
        photo = None
        if pending.photo:
            try:
                photo = await run_in_threadpool(person.store.photo_url, pending.photo)
            except HistoryError:
                log.exception("chooser photo unavailable")
        choose = TEMPLATES.TemplateResponse(
            request,
            "choose_plant.html",
            {
                "rid": answer_id,
                "found": pending.found,
                "person": person,
                "photo": photo,
                "top": reading.top if reading else None,
            },
        )
        return _with_cookies(choose, holder)

    @app.post("/answers/{answer_id}/plant", response_class=HTMLResponse)
    async def choose_plant(request: Request, answer_id: str, plant_id: str = Form("")):
        person, holder = await who(request)
        pending = app.state.pending.get(answer_id)
        if person is not None and pending is not None and pending.claimed:
            return await choose_kept(request, answer_id, plant_id, person, holder, pending)
        hit = cached(answer_id, person)
        if person is None or hit is None or pending is None or pending.user_id != person.user_id:
            return message(request, EXPIRED, 404, "/", "Check a plant")
        if app.state.pending.take(answer_id) is None:  # a second tap lost the race
            return message(request, EXPIRED, 404, "/", "Check a plant")
        reading = hit[0]

        def go() -> remember.Answered:
            if plant_id == "new":
                pid = remember.new_plant(person, reading)
            elif plant_id in {p.id for p in person.store.list_plants()}:
                pid = plant_id
            else:
                raise HTTPException(404, "No such plant.")
            return remember.answer_for_plant(app.state.deps, person, reading, pid, pending, clock())

        try:
            got = await run_in_threadpool(go)
        except HTTPException as e:
            app.state.pending.put(answer_id, pending)  # not someone's plant: they may pick again
            return message(request, str(e.detail), e.status_code)
        except HistoryError:
            log.exception("history unavailable at choose")
            rec = await run_in_threadpool(decide, app.state.deps, reading, pending.told)
            rec.notes.append(remember.HISTORY_DOWN)
            got = remember.Answered(rec, reading, None)
        app.state.answers.put(reading, got.rec, person.user_id, got.last_decline)
        # post, then redirect, then get: a refresh shows the answer, never "resubmit the form?"
        answer = RedirectResponse(f"/answers/{got.rec.record_id}", status_code=303)
        return _with_cookies(answer, holder)

    def tap_for(request: Request, person: Person | None, tap_id: str):
        wait = app.state.taps.get(tap_id)
        key = claims.browser_key(request, settings.reminder_secret)
        return wait if wait and wait.belongs_to(person.user_id if person else None, key) else None

    @app.get("/taps/{tap_id}", response_class=HTMLResponse)
    async def tap_page(request: Request, tap_id: str):
        """ "Tap the plant you mean": a photo of different plants (tapping.py)."""
        person, holder = await who(request)
        wait = tap_for(request, person, tap_id)
        if wait is None:
            return message(request, TAP_EXPIRED, 404, "/", "Check a plant")
        page = TEMPLATES.TemplateResponse(
            request,
            "tap_plant.html",
            {"tap_id": tap_id, "share": wait.share, "least": wait.least, "person": person},
        )
        return _with_cookies(page, holder)

    @app.get("/taps/{tap_id}/photo")
    async def tap_photo(request: Request, tap_id: str):
        person, _ = await who(request)
        wait = tap_for(request, person, tap_id)
        if wait is None:
            raise HTTPException(404, "No such photo.")
        body = await run_in_threadpool(tapping.shown_photo, wait.raw)
        return Response(body, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.post("/taps/{tap_id}", response_class=HTMLResponse)
    async def tap_choice(
        request: Request,
        tap_id: str,
        fx: str = Form(""),
        fy: str = Form(""),
        fs: str = Form(""),
        x: str = Form(""),
        y: str = Form(""),
        w: str = Form(""),
        h: str = Form(""),
        whole: str = Form(""),
    ):
        person, holder = await who(request)
        if tap_for(request, person, tap_id) is None:
            return message(request, TAP_EXPIRED, 404, "/", "Check a plant")
        cut: Callable[[bytes], bytes] | None = None
        if not whole:
            # the box: its top-left corner (x, y) and its width and height (w, h) as shares
            # of the photo. A page loaded before the box had edges sends a square instead:
            # its centre (fx, fy), and its side (fs) as a share of the short side, or no fs
            # from a page older still
            try:
                if x or y or w or h:
                    rect = (float(x), float(y), float(w), float(h))
                    ok = tapping.good_rect(*rect)
                    cut = partial(tapping.crop_rect_at, x=rect[0], y=rect[1], w=rect[2], h=rect[3])
                else:
                    sq = (float(fx), float(fy), float(fs) if fs else tapping.CROP_SHARE)
                    ok = all(0 <= v <= 1 for v in sq[:2]) and tapping.good_share(sq[2])  # NaN fails
                    cut = partial(tapping.crop_at, fx=sq[0], fy=sq[1], share=sq[2])
            except ValueError:
                ok = False
            if not ok:
                return message(request, TAP_AGAIN, 400, f"/taps/{tap_id}", "Back to the photo")
        wait = app.state.taps.take(tap_id)  # once: a second tap lost the race
        if wait is None:
            return message(request, TAP_EXPIRED, 404, "/", "Check a plant")
        if cut is not None:
            refused = await photo_refusal(request)  # the crop is read again: a paid read
            if refused:
                app.state.taps.restore(tap_id, wait)  # not used: it may be tapped later
                return message(request, refused, 429)
        data, mime, first = wait.raw, wait.mime, wait.reading
        if cut is not None:
            try:
                data = await run_in_threadpool(cut, wait.raw)
            except ValueError:
                log.info("tap refused for %s", tap_id, exc_info=True)
                app.state.taps.restore(tap_id, wait)  # they may tap again
                return message(request, TAP_AGAIN, 400, f"/taps/{tap_id}", "Back to the photo")
            # the crop alone is read again: the closer looks showed the whole photo's plant
            mime, first = "image/jpeg", None

        def work(progress: Callable[[str], None]) -> str:
            if person is None:
                rec = run(
                    data,
                    mime,
                    wait.device,
                    wait.place,
                    wait.told,
                    progress,
                    claim=wait.claim,
                    first=first,
                    tapped=cut is not None,
                )
                if getattr(request.state, "history_down", False):
                    rec.notes.append(remember.HISTORY_DOWN)  # offer_tap is off: never asked twice
                return f"/answers/{rec.record_id}"
            got = remember.start(
                app.state.deps, person, data, mime, received=clock(), device=wait.device,
                place=wait.place, told=wait.told, progress=progress, reading=first,
                tapped=cut is not None,
            )  # fmt: skip
            return landed(person, got, (data, mime))

        traces = app.state.deps.traces
        settle = traces.settle if traces is not None else None
        head = SIGNED_OUT_HEAD if person is None else HEAD
        return _with_cookies(
            progress_response(work, settle, head=head, advisor=_advised_by(settings)), holder
        )

    @app.post("/api/analyse")
    async def analyse_api(
        request: Request,
        photo: UploadFile,
        lat: str | None = Form(None),
        lon: str | None = Form(None),
        place: str | None = Form(None),
        question: str | None = Form(None),
    ):
        device, where, told = _device(lat, lon), _place(place), _told(question=question)
        data, mime = await _read_photo(photo)
        more = await _read_more(request, data)
        refused = await photo_refusal(request)
        if refused:
            return JSONResponse({"detail": refused}, status_code=429)
        rec = await run_in_threadpool(
            partial(run, more=more), data, mime, device, where, None if told.is_empty() else told
        )
        return JSONResponse(rec.model_dump(mode="json"))

    @app.post("/answers/{answer_id}/refine", response_class=HTMLResponse)
    async def refine_page(
        request: Request,
        answer_id: str,
        soil_feel: str | None = Form(None),
        last_watered: str | None = Form(None),
        changed: str | None = Form(None),
        question: str | None = Form(None),
        place: str | None = Form(None),
        squeeze: str | None = Form(None),
        setting: str | None = Form(None),  # "Wrong? Switch": indoor or outdoor
    ):
        try:
            spot = {}
            if settings.spot_enabled:  # off: the spot fields are ignored, as before S5
                spot = {"squeeze": squeeze, "heading": _heading(await request.form())}
            told = _told(
                soil_feel=soil_feel,
                last_watered=last_watered,
                changed=changed,
                question=question,
                place=place,
                setting=setting,
                **spot,
            )
            person, holder = await who(request)
            rec, last = await run_in_threadpool(
                refine, answer_id, told, person, refine_hook(request, answer_id)
            )
            chat = await run_in_threadpool(
                followup.chat_so_far, person, answer_id, app.state.answers
            )
            check = await run_in_threadpool(checkup.checkup_for, person, answer_id)
        except HTTPException as e:
            # a form post gets a page back, never the JSON error body
            if e.status_code == 404:
                return message(request, str(e.detail), 404, "/", "Check a plant")
            return message(
                request,
                str(e.detail),
                e.status_code,
                f"/answers/{answer_id}",
                "Go back to the answer",
            )
        box = await reminder_box(person, answer_id)
        return _with_cookies(page(request, rec, last, chat, check, box, person is not None), holder)

    @app.post("/answers/{answer_id}/photos", response_class=HTMLResponse)
    async def more_photos_page(
        request: Request,
        answer_id: str,
        soil_feel: str | None = Form(None),
        last_watered: str | None = Form(None),
        changed: str | None = Form(None),
        question: str | None = Form(None),
        squeeze: str | None = Form(None),
        setting: str | None = Form(None),
    ):
        """ "Add photos for a surer answer": the first photo and 1 or 2 more of the same plant,
        read again together in one call (one photo read for the visitor cap), then a fresh
        answer at a new id; the first answer stays as it was."""
        back = f"/answers/{answer_id}"
        if not _is_answer_id(answer_id):
            return message(request, EXPIRED, 404, "/", "Check a plant")
        person, holder = await who(request)
        entry = app.state.answers.get_for(answer_id, person.user_id if person else None)
        if entry is None and person is not None:  # read while sign-in was down (answer_page)
            entry = app.state.answers.get_for(answer_id, None)
        first_rec = entry.latest if entry is not None else None
        plant_id = None  # signed in: the plant the first answer is kept on, if it is kept
        if person is not None:
            try:
                stored = await run_in_threadpool(person.store.get_answer, answer_id)
            except HistoryError:
                log.exception("stored answer unavailable for more photos")
                stored = None  # the fresh answer then asks which plant, as an upload does
            if stored is not None:
                plant_id = stored.plant_id
                first_rec = first_rec or reading_from(stored).rec
        # only an answer this visitor can open, and only while its first photo is held
        held = app.state.held.get(answer_id) if first_rec is not None else None
        if held is None:
            return message(request, MORE_PHOTOS_GONE, 404, "/", "Check a plant")
        main, mime = held.data, held.mime
        try:
            more = await _read_more(request, main)
            if not more:
                raise HTTPException(400, MORE_PHOTOS_NONE)
            spot = {"squeeze": squeeze, "heading": _heading(await request.form())}
            told = _told(
                soil_feel=soil_feel,
                last_watered=last_watered,
                changed=changed,
                question=question,
                setting=setting,
                **(spot if settings.spot_enabled else {}),
            )
        except HTTPException as e:  # a form post gets a page back, never the JSON error body
            return message(request, str(e.detail), e.status_code, back, "Go back to the answer")
        refused = await photo_refusal(request)  # every check first: a bad post uses no read
        if refused:
            return message(request, refused, 429, back, "Go back to the answer")
        told_or_none = None if told.is_empty() else told
        claim = entry.claim if entry is not None else None

        def work(progress: Callable[[str], None]) -> str:
            got = read_photo(
                app.state.deps, main, mime, received=clock(), progress=progress, more=more,
                same_as=first_rec,
            )  # fmt: skip
            if person is None:
                rec = run(main, mime, None, None, told_or_none, progress, claim=claim, first=got)
                return f"/answers/{rec.record_id}"
            if plant_id:
                done = remember.surer(
                    app.state.deps, person, got, plant_id, main, told_or_none, clock(),
                    progress=progress,
                )  # fmt: skip
            elif isinstance(got, AnalysisRecord):  # stopped early: never read a second time
                done = remember.Answered(got, None, None)
            else:  # not kept on a plant (yet): which plant is this, as an upload asks
                done = remember.start(
                    app.state.deps, person, main, mime, received=clock(), device=None,
                    place=None, told=told_or_none, progress=progress, reading=got,
                )  # fmt: skip
            return landed(person, done, (main, mime))

        traces = app.state.deps.traces
        settle = traces.settle if traces is not None else None
        head = SIGNED_OUT_HEAD if person is None else HEAD
        return _with_cookies(progress_response(work, settle, head=head), holder)

    @app.post("/answers/{answer_id}/did-it", response_class=HTMLResponse)
    async def did_it_page(request: Request, answer_id: str, did_it: str = Form("")):
        person, holder = await who(request)
        if person is None or did_it not in get_args(DidIt) or not _is_answer_id(answer_id):
            return message(request, EXPIRED, 404, "/", "Check a plant")
        try:
            check = await run_in_threadpool(
                traced,
                "checkup",
                {"answer_id": answer_id},
                checkup.record,
                app.state.deps,
                person,
                answer_id,
                did_it,
                clock(),
            )
            stored = await run_in_threadpool(person.store.get_answer, answer_id)
        except HistoryError:
            log.exception("could not record the checkup")
            # another server process may have stored this pair first (the unique pair
            # refuses the second row): show the stored result rather than an outage
            check = await run_in_threadpool(checkup.checkup_for, person, answer_id)
            stored = await run_in_threadpool(followup._stored, person, answer_id)
            if check is None or check.line is None or stored is None:
                return message(request, remember.HISTORY_DOWN, 503)
        if stored is None:
            return message(request, EXPIRED, 404, "/", "Check a plant")
        chat = await run_in_threadpool(followup.chat_so_far, person, answer_id, app.state.answers)
        rec = followup._record(stored)
        box = await reminder_box(person, answer_id)
        return _with_cookies(page(request, rec, None, chat, check, box, person is not None), holder)

    async def reminder_box(person, answer_id: str):
        """The "email me" box, or None: no box is better than no answer page."""
        try:
            return await run_in_threadpool(
                reminding.box_for, person, answer_id, settings.reminder_secret
            )
        except HistoryError:
            log.exception("could not read the reminder")
            return None

    @app.post("/answers/{answer_id}/reminder", response_class=HTMLResponse)
    async def reminder_set(
        request: Request, answer_id: str, on: str = Form(""), back: str = Form("")
    ):
        person, holder = await who(request)
        if person is None or not settings.reminder_secret or not _is_answer_id(answer_id):
            return message(request, EXPIRED, 404, "/", "Check a plant")
        try:
            offered = await run_in_threadpool(reminding.set_box, person, answer_id, bool(on))
        except HistoryError:
            log.exception("could not save the reminder")
            return message(request, remember.HISTORY_DOWN, 503)
        if not offered:
            return message(request, EXPIRED, 404, "/", "Check a plant")
        if request.headers.get("x-herbtwin-fetch") == "1":  # the page's own script: saved
            return _with_cookies(Response(status_code=204), holder)
        # back at the answer, the "Tell us more" fold the box sits in is opened by the page
        # on this flag, then the #refine jump lands on it (21 Oct: it folds to one line now,
        # and would shut over the box just ticked)
        back_to = "/plants" if back == "/plants" else f"/answers/{answer_id}?saved=reminder#refine"
        return _with_cookies(RedirectResponse(back_to, status_code=303), holder)

    def unsubscribe_link(a: str, t: str) -> bool:
        return _is_answer_id(a) and reminders.valid(a, t, settings.reminder_secret or "")

    @app.get("/reminders/unsubscribe", response_class=HTMLResponse)
    def unsubscribe_ask(request: Request, a: str = "", t: str = ""):
        """Opening the link only asks: mail scanners open links, a person presses Stop."""
        if not settings.reminder_secret:
            return message(request, NO_REMINDERS, 404)
        if not unsubscribe_link(a, t):
            return message(request, BAD_LINK, 400)
        return TEMPLATES.TemplateResponse(request, "unsubscribe.html", {"a": a, "t": t})

    @app.post("/reminders/unsubscribe", response_class=HTMLResponse)
    async def unsubscribe(request: Request):
        """The Stop button, and mail clients' one-click unsubscribe (RFC 8058), which posts
        to the link itself with the answer and token in the address."""
        if not settings.reminder_secret:
            return message(request, NO_REMINDERS, 404)
        form = await request.form()
        a = request.query_params.get("a") or str(form.get("a") or "")
        t = request.query_params.get("t") or str(form.get("t") or "")
        if not unsubscribe_link(a, t):
            return message(request, BAD_LINK, 400)
        admin = app.state.reminder_admin
        if admin is None:
            return message(request, UNSUBSCRIBE_DOWN, 503)
        try:
            turned = await run_in_threadpool(admin.turn_off, a, "unsubscribed", clock())
        except reminders.AdminError:
            log.exception("could not turn the reminder off")
            return message(request, UNSUBSCRIBE_DOWN, 503)
        return message(request, UNSUBSCRIBED if turned else ALREADY_OFF)

    def need_spot() -> None:
        if not settings.spot_enabled:
            raise HTTPException(404)

    def owner_of(person: Person | None) -> str | None:
        return person.user_id if person else None

    def spot_answers(form: Mapping, squeeze: str | None) -> SpotTold:
        """The spot questions' answers from a form; bad input is a 400."""
        setting = str(form.get("setting") or "").strip() or None
        size = str(form.get("pot_size") or "").strip() or None
        if setting is not None and setting not in SPOT_SETTINGS:
            raise HTTPException(400, "Pick a setting from the list.")
        if size is not None and size not in get_args(PotSize):
            raise HTTPException(400, "Pick a pot size from the list.")
        return SpotTold(
            told=_told(squeeze=squeeze, heading=_heading(form)),
            setting=setting,  # type: ignore[arg-type]
            pot_size=size,  # type: ignore[arg-type]
        )

    def spot_page(request: Request, entry: spotting.SpotEntry, person: Person | None):
        """Decide (code only), keep it for a signed-in person, and render."""
        view = view_spot(entry.run, entry.answers)
        spotting.remember_spot(person, entry.run, entry.answers, view.spot, view.grow)
        taken = entry.run.taken_at
        notes, lead = spotting.split_lead(view.spot.notes)
        return TEMPLATES.TemplateResponse(
            request,
            "spot.html",
            {
                "run": entry.run,
                "spot": view.spot,
                # the backup photo model misreads pots as open ground: ask before trusting it
                "check_setting": entry.run.read_by_backup
                and entry.answers.setting is None
                and entry.run.read.setting != "unknown",
                "grow": view.grow,
                "groups": spotting.groups(view.grow, view.more),
                "notes": notes,
                "lead_note": lead,
                "medium": medium_text(view.spot),
                "month": f"{taken:%B}",
                "month_number": taken.month,
                # a reused direction is named only where the direction counts
                "history": spotting.history_note(entry.run)
                if view.spot.direction_matters
                else None,
                "squeeze_choices": SQUEEZE_TEXT,
                "compass_first": COMPASS_FIRST,
                "attributions": credits(view.spot, view.grow),
                "person": person,
                "accounts": app.state.accounts is not None,
            },
        )

    @app.post("/spots", response_class=HTMLResponse)
    async def spot_upload(
        request: Request,
        photo: UploadFile,
        lat: str | None = Form(None),
        lon: str | None = Form(None),
        place: str | None = Form(None),
    ):
        """ "What can I grow here?" (D67): the direction card fills the wait."""
        need_spot()
        device, where = _device(lat, lon), _place(place)
        data, mime = await _read_photo(photo)  # a bad upload never uses a slot
        refused = await photo_refusal(request)
        if refused:
            return message(request, refused, 429)
        person, holder = await who(request)
        owner, rid = owner_of(person), uuid.uuid4().hex
        app.state.spots.start(rid, owner)

        def work(progress: Callable[[str], None]) -> str:
            try:
                run = read_spot_photo(
                    app.state.deps, data, mime, received=clock(), device=device, place=where,
                    record_id=rid, progress=progress,
                )  # fmt: skip
                spotting.reuse_aspect(person, run, clock())
            except Exception:
                app.state.spots.drop(rid)  # no endless "still reading" for a no-script answer
                raise
            app.state.spots.finish(run, owner)
            return f"/spots/{rid}"

        traces = app.state.deps.traces
        extra = TEMPLATES.get_template("_spot_wait.html").render(
            rid=rid, compass_first=COMPASS_FIRST
        )
        settle = traces.settle if traces is not None else None
        return _with_cookies(progress_response(work, settle, extra, SPOT_HEAD, retry="/"), holder)

    @app.post("/spots/{spot_id}/told", response_class=HTMLResponse)
    async def spot_told(request: Request, spot_id: str, squeeze: str | None = Form(None)):
        """An answer to a spot question or a chip correction: the code reruns, no call."""
        need_spot()
        person, holder = await who(request)
        try:
            new = spot_answers(await request.form(), squeeze)
        except HTTPException as e:
            return message(request, str(e.detail), e.status_code, f"/spots/{spot_id}")
        if app.state.spots.answer(spot_id, owner_of(person), new) is None:
            return message(request, EXPIRED, 404, "/", "Check a plant")
        if request.headers.get("x-herbtwin-fetch") == "1":
            return Response(status_code=204)
        return _with_cookies(RedirectResponse(f"/spots/{spot_id}", status_code=303), holder)

    @app.get("/spots/{spot_id}", response_class=HTMLResponse)
    async def spot_answer(request: Request, spot_id: str):
        need_spot()
        person, holder = await who(request)
        entry = app.state.spots.get(spot_id, owner_of(person))
        if entry is None:
            return message(request, EXPIRED, 404, "/", "Check a plant")
        if entry.run is None:  # answered without script before the read ended
            still = TEMPLATES.TemplateResponse(
                request,
                "message.html",
                {"message": STILL_READING, "refresh": 3, "heading": "One moment"},
            )
            return _with_cookies(still, holder)
        page = await run_in_threadpool(spot_page, request, entry, person)
        return _with_cookies(page, holder)

    @app.get("/answers/{answer_id}/spot", response_class=HTMLResponse)
    async def about_this_spot(request: Request, answer_id: str):
        """From a plant answer: its place and reading, no new vision call."""
        need_spot()
        if not _is_answer_id(answer_id):
            return message(request, EXPIRED, 404, "/", "Check a plant")
        person, holder = await who(request)
        hit = cached(answer_id, person)
        reading = hit[0] if hit else None
        bed = _bed_record(answer_id, person) if reading is None else None
        if reading is None and bed is None and person is not None:
            try:
                stored = await run_in_threadpool(person.store.get_answer, answer_id)
            except HistoryError:
                log.exception("could not read the stored answer for its spot")
                return message(request, remember.HISTORY_DOWN, 503)
            reading = reading_from(stored) if stored else None
        if reading is None and bed is None:
            return message(request, EXPIRED, 404, "/", "Check a plant")

        rid = uuid.uuid5(ABOUT_SPOT, answer_id).hex
        to = _with_cookies(RedirectResponse(f"/spots/{rid}", status_code=303), holder)
        kept = app.state.spots.get(rid, owner_of(person))
        if kept is not None and kept.run is not None:
            return to  # a repeat click: the same spot, its answers kept

        def from_reading():
            if reading is None:
                run = spot_from_record(app.state.deps, bed, record_id=rid)
            else:
                run = spot_from_reading(app.state.deps, reading, record_id=rid)
            spotting.reuse_aspect(person, run, clock())
            return run

        run = await run_in_threadpool(from_reading)
        app.state.spots.finish(run, owner_of(person))
        return to

    @app.post("/api/spots")
    async def spot_api(
        request: Request,
        photo: UploadFile,
        lat: str | None = Form(None),
        lon: str | None = Form(None),
        place: str | None = Form(None),
        squeeze: str | None = Form(None),
    ):
        need_spot()
        device, where = _device(lat, lon), _place(place)
        answers = spot_answers(await request.form(), squeeze)
        data, mime = await _read_photo(photo)
        refused = await photo_refusal(request)
        if refused:
            return JSONResponse({"detail": refused}, status_code=429)
        run = await run_in_threadpool(
            read_spot_photo,
            app.state.deps,
            data,
            mime,
            received=clock(),
            device=device,
            place=where,
        )
        # not kept in the spot cache: an API caller gets no page to come back to
        view = await run_in_threadpool(view_spot, run, answers)
        told = None if answers.told.is_empty() else answers.told
        return JSONResponse(record_of(run, view.spot, view.grow, told).model_dump(mode="json"))

    @app.post("/api/answers/{answer_id}/refine")
    async def refine_api(request: Request, answer_id: str, told: Told):
        if not settings.spot_enabled:  # the spot answers count only once S6 ships them
            told = told.model_copy(update={"squeeze": None, "heading": None})
        rec, _ = await run_in_threadpool(
            refine, answer_id, told, None, refine_hook(request, answer_id)
        )
        return JSONResponse(rec.model_dump(mode="json"))

    @app.post("/api/answers/{answer_id}/chat")
    async def chat_api(request: Request, answer_id: str, body: ChatIn):
        if not _same_site(request, app.state.site_url):
            raise HTTPException(403, "That message did not come from this site.")
        try:
            text = clean_message(body.message)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        charge = charge_hook(request, "chat message", settings.limits.chat_cost_usd)
        person, holder = await who(request)
        try:
            turn = await run_in_threadpool(
                traced,
                "chat",
                {"answer_id": answer_id},
                followup.chat_turn,
                app.state.deps,
                person,
                answer_id,
                text,
                app.state.answers,
                charge,
            )
        except followup.Expired:
            raise HTTPException(404, EXPIRED) from None
        except followup.AtLimit:
            raise HTTPException(429, LIMIT) from None
        except ChatError as e:
            raise HTTPException(503, str(e)) from e
        out = JSONResponse(
            {
                "reply": turn.reply.text,
                "sources": turn.reply.sources,
                "fact": turn.reply.fact,  # told, not asked: the page may keep it in the box
                "left": turn.left,
                "note": turn.note,
            }
        )
        return _with_cookies(out, holder)

    @app.post("/api/answers/{answer_id}/voice")
    async def voice_api(request: Request, answer_id: str):
        """The plant reads its answer aloud. Made once per answer as it stands, then the
        audio is kept, so a replay costs nothing. On a voice failure the words still come
        back with a 503, so the browser can speak them itself."""
        key = settings.elevenlabs_api_key
        if key is None or not settings.voice_on:  # switched off (21 Oct): no voice at all
            raise HTTPException(404, "Not Found")
        if not _same_site(request, app.state.site_url):
            raise HTTPException(403, "That request did not come from this site.")
        person, holder = await who(request)
        owner = person.user_id if person else None
        try:
            rec = await run_in_threadpool(followup.answer_for, person, answer_id, app.state.answers)
        except followup.Expired:
            raise HTTPException(404, EXPIRED) from None
        if rec.answer is None:
            raise HTTPException(404, "This answer has nothing to read out.")
        basis = voice_basis(rec)
        spoken = app.state.voices.get(answer_id, basis, owner)
        if spoken is None:
            with voicing_lock:
                if answer_id in voicing:  # a second press or tab while the first is made
                    raise HTTPException(429, "Its voice is on the way. Try again in a moment.")
                voicing.add(answer_id)
            try:
                charge_hook(request, "voice", settings.limits.voice_cost_usd)()
                text = await run_in_threadpool(
                    traced,
                    "voice",
                    {"answer_id": answer_id},
                    followup.voice_line,
                    app.state.deps,
                    rec,
                )
                try:
                    audio = await run_in_threadpool(
                        speak, text, persona_for(rec).voice_id, api_key=key
                    )
                except VoiceError:
                    audio = b""  # kept, so a retry is not charged again: the browser reads it
                spoken = Spoken(basis, owner, text, audio)
                app.state.voices.put(answer_id, spoken)
            finally:
                with voicing_lock:
                    voicing.discard(answer_id)
        if not spoken.audio:
            body = {"detail": VOICE_UNAVAILABLE, "text": spoken.text}
            return _with_cookies(JSONResponse(body, status_code=503), holder)
        out = JSONResponse({"text": spoken.text, "audio": f"/api/answers/{answer_id}/voice.mp3"})
        return _with_cookies(out, holder)

    @app.get("/api/answers/{answer_id}/voice.mp3")
    async def voice_audio(request: Request, answer_id: str):
        person, _ = await who(request)
        spoken = app.state.voices.get(answer_id, None, person.user_id if person else None)
        if spoken is None or not spoken.audio:
            raise HTTPException(404, "Not Found")
        return Response(
            spoken.audio,
            media_type="audio/mpeg",
            headers={"Cache-Control": "private, max-age=3600"},
        )

    return app
