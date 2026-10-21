"""A person's plants and the answers given for them (spec section 5, D45).

HistoryStore is the seam: MemoryHistoryStore backs the offline tests; the Supabase store
(adapters/supabase_store.py) is the real one. A store is bound to one person, the way
every Supabase call runs as that person, so row-level security is the guard.
"""

from __future__ import annotations

import base64
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal, Protocol

from pydantic import BaseModel, Field, field_validator

from herbtwin.advice_context import told_lines
from herbtwin.schemas import (
    Answer,
    Aspect,
    Comparison,
    DidIt,
    Environment,
    GrowList,
    KnowledgePack,
    LightMissing,
    LightReading,
    Location,
    Observation,
    Prediction,
    ProblemSeen,
    ScoreResult,
    Spot,
    StageFailure,
    Told,
    TrustedCheck,
)
from herbtwin.seasonal import SeasonalNorm

if TYPE_CHECKING:
    from herbtwin.reminders import Reminder

log = logging.getLogger(__name__)


class HistoryError(Exception):
    """History is not available right now (Supabase unreachable or refused)."""


class Evidence(BaseModel):
    """What the photo reading found, stored so a later refine can rebuild its Reading."""

    location: Location | None
    taken_at_source: Literal["exif", "assumed"]
    environment: Environment | None
    pack: KnowledgePack | None
    season: SeasonalNorm | None
    notes: list[str]
    failures: list[StageFailure]
    season_missing: str | None
    weather_missing: str | None
    light: LightReading | None = None  # C1; absent in answers stored before it
    light_missing: LightMissing | None = None
    photo_sha256: str | None = None  # the upload's twin-bank key; absent in older answers
    problem: ProblemSeen | None = None  # the photo check's finding; absent in older answers
    trusted: TrustedCheck | None = None  # a trusted page's read sentences; absent in older ones

    @field_validator("trusted", mode="wrap")
    @classmethod
    def _page_or_none(cls, v, handler):
        """A kept page that no longer reads (the form's words or the trusted sites changed)
        drops its quote, never the whole stored answer."""
        try:
            return handler(v)
        except ValueError as e:
            log.info("stored trusted page dropped (%s)", type(e).__name__)
            return None


class Plant(BaseModel):
    id: str
    name: str
    species: str
    genus: str
    place_lat: float | None
    place_lon: float | None
    created_at: datetime


class StoredAnswer(BaseModel):
    id: str
    plant_id: str
    taken_at: datetime
    created_at: datetime
    photo_path: str | None
    observation: Observation
    evidence: Evidence
    answer: Answer | None
    told: Told | None

    @field_validator("taken_at", "created_at")
    @classmethod
    def _zoned(cls, v: datetime) -> datetime:
        return utc(v)

    @field_validator("id")
    @classmethod
    def _app_form(cls, v: str) -> str:
        """The app's answer ids are 32 hex characters; Postgres hands back hyphens."""
        try:
            return uuid.UUID(v).hex
        except ValueError:
            return v


class ChatMessage(BaseModel):
    """One message of the chat under an answer (table chat_messages)."""

    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)
    tools: list[dict] | None = None  # the tool calls behind an assistant reply
    created_at: datetime | None = None


class AdviceScore(BaseModel):
    """How the earlier answer's main action turned out on the next photo (C2, table
    advice_scores)."""

    plant_id: str
    earlier_answer_id: str
    later_answer_id: str
    prediction: Prediction
    did_it: DidIt
    result: ScoreResult
    reason: str | None = None  # why it could not tell, in plain words
    comparison: Comparison | None = None  # the four looks, when the model was asked
    scored_at: datetime

    @field_validator("earlier_answer_id", "later_answer_id")
    @classmethod
    def _app_form(cls, v: str) -> str:
        """Answer ids in the app's 32-hex form; Postgres hands back hyphens."""
        try:
            return uuid.UUID(v).hex
        except ValueError:
            return v

    @field_validator("scored_at")
    @classmethod
    def _zoned(cls, v: datetime) -> datetime:
        return utc(v)


class StoredSpot(BaseModel):
    """A signed-in person's spot answer (spot spec D70): the place rounded to about 1 km,
    the compass or 8-way reading they gave (never one reused from history), the spot card
    and the list."""

    id: str
    taken_at: datetime
    place: Location | None
    aspect: Aspect | None
    spot: Spot
    grow: GrowList | None

    @field_validator("taken_at")
    @classmethod
    def _zoned(cls, v: datetime) -> datetime:
        return utc(v)


class UserSettings(BaseModel):
    """The person's choices (C3, table user_settings). No row reads as these defaults:
    not sharing, never asked."""

    share_scored_pairs: bool = False
    asked_at: datetime | None = None  # when they last answered the sharing ask

    @field_validator("asked_at")
    @classmethod
    def _zoned(cls, v: datetime | None) -> datetime | None:
        return utc(v) if v is not None else None


class HistoryStore(Protocol):
    def list_plants(self) -> list[Plant]: ...
    def create_plant(
        self, name: str, species: str, genus: str, place: Location | None
    ) -> Plant: ...
    def rename_plant(self, plant_id: str, name: str) -> None: ...
    def delete_plant(self, plant_id: str) -> None: ...
    def add_answer(self, a: StoredAnswer) -> None: ...
    def update_answer(
        self,
        answer_id: str,
        answer: Answer | None,
        told: Told | None,
        evidence: Evidence | None = None,
    ) -> None: ...
    def get_answer(self, answer_id: str) -> StoredAnswer | None: ...
    def answers_for(self, plant_id: str) -> list[StoredAnswer]: ...
    def latest_by_plant(self) -> dict[str, StoredAnswer]: ...
    def put_photo(self, answer_id: str, jpeg: bytes, thumb: bytes) -> str: ...
    def set_photo(self, answer_id: str, path: str) -> None: ...
    def photo_url(self, path: str, *, thumb: bool = True) -> str | None: ...
    def add_chat(self, answer_id: str, msg: ChatMessage) -> None: ...
    def chat_for(self, answer_id: str) -> list[ChatMessage]: ...
    def get_photo(self, path: str) -> bytes | None: ...
    def add_score(self, s: AdviceScore) -> None: ...
    def scores_for(self, plant_id: str) -> list[AdviceScore]: ...
    def get_settings(self) -> UserSettings: ...
    def set_sharing(self, share: bool, now: datetime) -> None: ...
    def get_reminder(self, answer_id: str) -> Reminder | None: ...
    def set_reminder(self, answer_id: str, r: Reminder | None) -> None: ...  # None removes it
    def save_spot(self, s: StoredSpot) -> None: ...  # insert or replace by id
    def recent_aspect(self, place: Location, since: datetime) -> tuple[Aspect, datetime] | None: ...


def utc(dt: datetime) -> datetime:
    """A photo's EXIF time has no zone; Postgres returns zoned times. Both read as UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def photo_path(user_id: str, answer_id: str) -> str:
    return f"{user_id}/{answer_id}.jpg"


def thumb_path(path: str) -> str:
    return path.removesuffix(".jpg") + "_thumb.jpg"


@dataclass
class MemoryHistory:
    """Everyone's rows in one place; for_user gives the view one person may see."""

    plants: dict[str, tuple[str, Plant]] = field(default_factory=dict)  # id -> (owner, plant)
    answers: dict[str, tuple[str, StoredAnswer]] = field(default_factory=dict)
    photos: dict[str, bytes] = field(default_factory=dict)  # "<uid>/<file>" -> bytes
    chats: list[tuple[str, str, ChatMessage]] = field(default_factory=list)  # owner, answer
    scores: list[tuple[str, AdviceScore]] = field(default_factory=list)  # owner, score
    settings: dict[str, UserSettings] = field(default_factory=dict)  # owner -> settings
    reminders: dict[str, tuple[str, Reminder]] = field(default_factory=dict)  # answer -> owner, row
    spots: dict[str, tuple[str, StoredSpot]] = field(default_factory=dict)  # id -> owner, row

    def for_user(self, user_id: str) -> MemoryHistoryStore:
        return MemoryHistoryStore(self, user_id)


@dataclass
class MemoryHistoryStore:
    hist: MemoryHistory
    user_id: str

    def _plant(self, plant_id: str) -> Plant | None:
        owner, plant = self.hist.plants.get(plant_id, (None, None))
        return plant if owner == self.user_id else None

    def list_plants(self) -> list[Plant]:
        mine = [p for o, p in self.hist.plants.values() if o == self.user_id]
        return sorted(mine, key=lambda p: p.created_at)

    def create_plant(self, name, species, genus, place):
        p = Plant(
            id=str(uuid.uuid4()),
            name=name,
            species=species,
            genus=genus,
            place_lat=place.lat if place else None,
            place_lon=place.lon if place else None,
            created_at=datetime.now(UTC),
        )
        self.hist.plants[p.id] = (self.user_id, p)
        return p

    def rename_plant(self, plant_id, name):
        p = self._plant(plant_id)
        if p is not None:
            self.hist.plants[plant_id] = (self.user_id, p.model_copy(update={"name": name}))

    def delete_plant(self, plant_id):
        if self._plant(plant_id) is None:
            return
        for a in self.answers_for(plant_id):
            # photo paths follow the answer id, so a photo whose path was never recorded
            # on its row still goes with the plant
            path = photo_path(self.user_id, a.id)
            self.hist.photos.pop(path, None)
            self.hist.photos.pop(thumb_path(path), None)
            self.hist.chats = [c for c in self.hist.chats if c[1] != a.id]
            del self.hist.answers[a.id]
        self.hist.scores = [
            x for x in self.hist.scores if not (x[0] == self.user_id and x[1].plant_id == plant_id)
        ]
        del self.hist.plants[plant_id]

    def add_answer(self, a):
        if self._plant(a.plant_id) is None:
            raise HistoryError("no such plant")  # as the row-level check refuses it
        self.hist.answers[a.id] = (self.user_id, a)

    def update_answer(self, answer_id, answer, told, evidence=None):
        got = self.get_answer(answer_id)
        if got is not None:
            updates = {"answer": answer, "told": told}
            if evidence is not None:
                updates["evidence"] = evidence
            new = got.model_copy(update=updates)
            self.hist.answers[answer_id] = (self.user_id, new)

    def get_answer(self, answer_id):
        owner, a = self.hist.answers.get(answer_id, (None, None))
        return a if owner == self.user_id else None

    def set_photo(self, answer_id, path):
        got = self.get_answer(answer_id)
        if got is not None:
            self.hist.answers[answer_id] = (
                self.user_id,
                got.model_copy(update={"photo_path": path}),
            )

    def answers_for(self, plant_id):
        mine = [
            a for o, a in self.hist.answers.values() if o == self.user_id and a.plant_id == plant_id
        ]
        return sorted(mine, key=lambda a: a.taken_at, reverse=True)

    def latest_by_plant(self):
        out: dict[str, StoredAnswer] = {}
        for p in self.list_plants():
            got = self.answers_for(p.id)
            if got:
                out[p.id] = got[0]
        return out

    def put_photo(self, answer_id, jpeg, thumb):
        path = photo_path(self.user_id, answer_id)
        self.hist.photos[path] = jpeg
        self.hist.photos[thumb_path(path)] = thumb
        return path

    def photo_url(self, path, *, thumb=True):
        if not path.startswith(f"{self.user_id}/"):
            return None
        data = self.hist.photos.get(thumb_path(path) if thumb else path)
        return f"data:image/jpeg;base64,{base64.b64encode(data).decode()}" if data else None

    def add_chat(self, answer_id, msg):
        if self.get_answer(answer_id) is None:
            raise HistoryError("no such answer")  # as the row-level check refuses it
        stamped = msg.model_copy(update={"created_at": msg.created_at or datetime.now(UTC)})
        self.hist.chats.append((self.user_id, answer_id, stamped))

    def chat_for(self, answer_id):
        return [m for o, aid, m in self.hist.chats if o == self.user_id and aid == answer_id]

    def get_photo(self, path):
        if not path.startswith(f"{self.user_id}/"):
            return None
        return self.hist.photos.get(path)

    def add_score(self, s):
        for aid in (s.earlier_answer_id, s.later_answer_id):
            got = self.get_answer(aid)
            if got is None or got.plant_id != s.plant_id:
                raise HistoryError("no such answer")  # as the row-level check refuses it
        for _owner, x in self.hist.scores:
            if (x.earlier_answer_id, x.later_answer_id) == (s.earlier_answer_id, s.later_answer_id):
                raise HistoryError("already scored")  # the table's unique pair
        self.hist.scores.append((self.user_id, s))

    def scores_for(self, plant_id):
        mine = [s for o, s in self.hist.scores if o == self.user_id and s.plant_id == plant_id]
        return sorted(mine, key=lambda s: s.scored_at, reverse=True)

    def get_settings(self):
        return self.hist.settings.get(self.user_id, UserSettings())

    def set_sharing(self, share, now):
        self.hist.settings[self.user_id] = UserSettings(share_scored_pairs=share, asked_at=now)

    def get_reminder(self, answer_id):
        owner, r = self.hist.reminders.get(answer_id, (None, None))
        return r if owner == self.user_id else None

    def set_reminder(self, answer_id, r):
        if r is None:
            got = self.get_reminder(answer_id)
            if got is not None and got.sent_at is None:  # as the delete policy allows
                del self.hist.reminders[answer_id]
            return
        got = self.get_answer(answer_id)
        if got is None or got.plant_id != r.plant_id:
            raise HistoryError("no such answer")  # as the row-level check refuses it
        self.hist.reminders[answer_id] = (
            self.user_id,
            r.model_copy(update={"user_id": self.user_id}),
        )

    def save_spot(self, s):
        owner, _ = self.hist.spots.get(s.id, (self.user_id, None))
        if owner != self.user_id:
            raise HistoryError("not your spot")  # as the row-level check refuses it
        self.hist.spots[s.id] = (self.user_id, s)

    def recent_aspect(self, place, since):
        mine = [
            s
            for owner, s in self.hist.spots.values()
            if owner == self.user_id
            and s.aspect is not None
            and s.place is not None
            and (s.place.lat, s.place.lon) == (place.lat, place.lon)
            and s.taken_at >= utc(since)
        ]
        if not mine:
            return None
        last = max(mine, key=lambda s: s.taken_at)
        return last.aspect, last.taken_at


MATCH_DAYS = 60  # a plant is offered if it had a visit this recently (spec section 5)
HISTORY_DAYS = 60  # visits the advisor sees
CHANGED_DAYS = 30  # "anything changed?" compares with a visit this recent (spec section 4)
UNSURE = 0.7  # below this species confidence, match on genus instead
_GREENER = {"green": 0, "some_yellow": 1, "mostly_yellow": 2}


def genus_of(species: str) -> str:
    return species.strip().split(" ")[0].casefold() if species.strip() else ""


def _same_place(plant: Plant, place: Location | None) -> bool:
    if place is None:
        return plant.place_lat is None and plant.place_lon is None
    return plant.place_lat == place.lat and plant.place_lon == place.lon


def candidates(
    plants: list[Plant],
    latest: dict[str, StoredAnswer],
    *,
    species: str,
    genus: str,
    unsure: bool,
    place: Location | None,
    now: datetime,
) -> list[Plant]:
    """The person's plants this photo could be (spec section 5): same species (genus when
    the species is unsure), same rounded place, a visit in the last 60 days."""
    out = []
    for p in plants:
        last = latest.get(p.id)
        if last is None or utc(now) - last.taken_at > timedelta(days=MATCH_DAYS):
            continue
        same = (p.genus == genus and genus != "") if unsure else p.species == species.casefold()
        if same and _same_place(p, place):
            out.append((last.taken_at, p))
    return [p for _, p in sorted(out, key=lambda x: x[0], reverse=True)]


@dataclass(frozen=True)
class Visit:
    taken_at: datetime
    water_stress: int
    decline: int
    leaf_colour: str
    advice: str
    told: str
    scored: str = ""  # C2: how the advice before this visit turned out, when asked


def _told_text(told: Told | None) -> str:
    """What the person told us at that visit, in YOU TOLD US's wording, without their
    typed question (it was answered then; it is not repeated into later prompts)."""
    return "; ".join(told_lines(told.model_copy(update={"question": None}))) if told else ""


def recent_visits(
    answers: list[StoredAnswer],
    now: datetime,
    *,
    days: int = HISTORY_DAYS,
    limit: int = 3,
    lines: dict[str, str] | None = None,
) -> list[Visit]:
    now = utc(now)
    recent = [a for a in answers if timedelta(0) <= now - a.taken_at <= timedelta(days=days)]
    recent.sort(key=lambda a: a.taken_at, reverse=True)
    return [
        Visit(
            taken_at=a.taken_at,
            water_stress=a.observation.water_stress,
            decline=a.observation.decline,
            leaf_colour=a.observation.leaf_colour,
            advice=a.answer.headline if a.answer else "",
            told=_told_text(a.told),
            scored=(lines or {}).get(a.id, ""),
        )
        for a in recent[:limit]
    ]


def trend_line(
    obs: Observation, last: StoredAnswer, problem: ProblemSeen | None = None
) -> str | None:
    """Now against the last visit, from stored readings only (no second image call).
    problem is this photo's check finding: a pest or disease that came or went is a change
    even when droop, brown and colour read the same (19 Oct walk: "no change" between a
    healthy and a mildewed basil)."""
    since = f"since {last.taken_at.day} {last.taken_at:%b}"
    was = last.observation
    had = last.evidence.problem
    parts = []
    # only a finding counts: no finding can mean the second look never ran, so a problem
    # that "went" is never claimed
    if problem is not None and (had is None or had.name != problem.name):
        parts.append(f"{'signs of' if problem.sure else 'possible'} {problem.name}, new {since}")
    if obs.water_stress != was.water_stress:
        parts.append(
            f"droop {'worse' if obs.water_stress > was.water_stress else 'better'} {since}"
        )
    if obs.decline != was.decline:
        parts.append(f"{'more' if obs.decline > was.decline else 'less'} dead or brown {since}")
    a, b = _GREENER.get(obs.leaf_colour), _GREENER.get(was.leaf_colour)
    if a is not None and b is not None and a != b:
        parts.append(f"leaves {'greener' if a < b else 'yellower'} {since}")
    if not parts and obs.fine_leave_it != was.fine_leave_it:
        # the read's overall call moved with nothing above to say why (a sign no check named)
        parts.append(f"looks {'healthier' if obs.fine_leave_it else 'less healthy'} {since}")
    return "; ".join(parts) if parts else f"no change {since}"


def last_decline(answers: list[StoredAnswer], now: datetime) -> int | None:
    now = utc(now)
    recent = [
        a for a in answers if timedelta(0) <= now - a.taken_at <= timedelta(days=CHANGED_DAYS)
    ]
    return max(recent, key=lambda a: a.taken_at).observation.decline if recent else None


def as_jpeg(image: bytes) -> bytes:
    """Photos are stored as JPEG whatever was uploaded (a PNG is converted)."""
    from io import BytesIO

    from PIL import Image

    if image.startswith(b"\xff\xd8\xff"):
        return image
    with Image.open(BytesIO(image)) as img:
        out = BytesIO()
        img.convert("RGB").save(out, "JPEG", quality=92)
        return out.getvalue()


def make_thumbnail(jpeg: bytes, size: int = 320) -> bytes:
    """A small JPEG for the chooser and the plant page (the photo is already stripped)."""
    from io import BytesIO

    from PIL import Image

    with Image.open(BytesIO(jpeg)) as img:
        small = img.convert("RGB")
        small.thumbnail((size, size))
        out = BytesIO()
        small.save(out, "JPEG", quality=80)
        return out.getvalue()
