"""The signed-in path (spec section 5): store the photo, ask which plant it is when one of
the person's plants could be it, answer with that plant's history, keep the answer.

History never blocks an answer: any HistoryError is logged, the page says "History is
not available right now", and the answer is given as for a signed-out person.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from herbtwin.history import (
    UNSURE,
    HistoryError,
    Plant,
    StoredAnswer,
    as_jpeg,
    candidates,
    genus_of,
    last_decline,
    make_thumbnail,
)
from herbtwin.pipeline import (
    Deps,
    Progress,
    Reading,
    as_told,
    decide,
    evidence_of,
    history_for,
    read_photo,
    reading_from,
)
from herbtwin.schemas import AnalysisRecord, Told
from herbtwin.stages.research import normalise_species
from herbtwin.web import reminding
from herbtwin.web.accounts import Person
from herbtwin.web.tapping import wants_tap
from herbtwin.where import strip_metadata

log = logging.getLogger(__name__)
HISTORY_DOWN = "History is not available right now."
MAX_PENDING = 500


@dataclass(frozen=True)
class Answered:
    rec: AnalysisRecord
    reading: Reading | None
    last_decline: int | None


@dataclass(frozen=True)
class Pending:
    """A photo waiting for "which plant is this?"."""

    user_id: str
    photo: str | None
    told: Told | None
    found: tuple[tuple[Plant, StoredAnswer, str | None], ...] = ()  # what to offer, for the page
    claimed: bool = False  # a signed-out answer being kept: stored as it is, never decided again


@dataclass(frozen=True)
class Choose:
    reading: Reading
    found: list[tuple[Plant, StoredAnswer, str | None]]  # plant, its latest visit, thumbnail
    pending: Pending


@dataclass(frozen=True)
class Tap:
    """Different plants in the photo: ask which before keeping anything (tapping.py)."""

    reading: Reading


class PendingChoices:
    """Bounded and thread-safe, like the answer cache; entries live until chosen or pushed out."""

    def __init__(self, max_entries: int = MAX_PENDING) -> None:
        self._max, self._items, self._lock = max_entries, OrderedDict(), threading.Lock()

    def put(self, answer_id: str, p: Pending) -> None:
        with self._lock:
            self._items[answer_id] = p
            while len(self._items) > self._max:
                self._items.popitem(last=False)

    def get(self, answer_id: str) -> Pending | None:
        with self._lock:
            return self._items.get(answer_id)

    def take(self, answer_id: str) -> Pending | None:
        """Hand the entry out once: a second tap racing the first gets None."""
        with self._lock:
            return self._items.pop(answer_id, None)

    def pop(self, answer_id: str) -> None:
        with self._lock:
            self._items.pop(answer_id, None)


def _who_it_is(reading: Reading) -> tuple[str, str, bool]:
    """(species, genus, unsure) of the photo's top candidate, lower case."""
    top = reading.top
    # the matched key, else the normalised Latin name: the photo reader names a plant in
    # either bracket order ("Sage (Salvia officinalis)", "Salvia officinalis (sage)")
    name = reading.match.key or (normalise_species(top.name) if top else "")
    species = name.casefold()
    unsure = top is None or top.confidence < UNSURE or reading.match.how == "genus"
    return species, genus_of(species), unsure


def plant_name(reading: Reading) -> str:
    top = reading.top
    name = (top.common_name or top.name).strip() if top else ""
    return (name[:1].upper() + name[1:])[:60] if name else "Plant"


def new_plant(person: Person, reading: Reading) -> str:
    species, genus, _ = _who_it_is(reading)
    return person.store.create_plant(plant_name(reading), species, genus, reading.rec.location).id


def _stored(reading: Reading, rec: AnalysisRecord, plant_id: str, photo, now) -> StoredAnswer:
    return StoredAnswer(
        id=rec.record_id,
        plant_id=plant_id,
        taken_at=rec.taken_at,
        created_at=now,
        photo_path=photo,
        observation=rec.observation,
        evidence=evidence_of(reading),
        answer=rec.answer,
        told=rec.told,
    )


KEPT_AS = "Kept in My plants as {name}."


def _store(person: Person, reading: Reading, rec: AnalysisRecord, plant_id: str, photo, now):
    try:
        person.store.add_answer(_stored(reading, rec, plant_id, photo, now))
        # said once it is kept (judge pre-walk, 19 Oct: no word after a choice that it was),
        # by the plant's own name, which can differ from this read's ("Basil", "Sweet basil")
        name = next((p.name for p in person.store.list_plants() if p.id == plant_id), None)
    except HistoryError:
        log.exception("could not store the answer run=%s", rec.record_id)
        rec.notes.append(HISTORY_DOWN)
        return
    if name:
        rec.notes.append(KEPT_AS.format(name=name))


def answer_for_plant(
    deps: Deps,
    person: Person,
    reading: Reading,
    plant_id: str,
    pending: Pending,
    now: datetime,
    *,
    progress: Progress | None = None,
) -> Answered:
    """Decide with the plant's history and keep the answer."""
    try:
        past = person.store.answers_for(plant_id)
        scores = person.store.scores_for(plant_id)
    except HistoryError:
        log.exception("could not read the plant's history")
        rec = decide(deps, reading, pending.told, progress=progress)
        rec.notes.append(HISTORY_DOWN)
        return Answered(rec, reading, None)
    taken = reading.rec.taken_at
    history = (
        history_for(past, reading.rec.observation, taken, scores, reading.rec.problem)
        if past
        else None
    )
    rec = decide(deps, reading, pending.told, history, progress=progress)
    _store(person, reading, rec, plant_id, pending.photo, now)
    return Answered(rec, reading, last_decline(past, taken))


def start(
    deps: Deps,
    person: Person,
    data: bytes,
    mime: str,
    *,
    received: datetime,
    device: tuple[float, float] | None,
    place: str | None,
    told: Told | None,
    progress: Progress | None = None,
    reading: Reading | None = None,
    offer_tap: bool = False,
    tapped: bool = False,
    more: Sequence[tuple[bytes, str]] = (),
) -> Answered | Choose | Tap:
    """Read the photo (unless its read is given: "Use the whole photo"), keep it, and either
    answer now or ask which plant it is. With `offer_tap`, a photo of different plants asks
    which one first, and nothing is kept until it is answered. `more`: the other photos of
    the same plant, read with it; only the main photo is kept."""
    got = reading or read_photo(
        deps, data, mime, received=received, device=device, place=place, progress=progress,
        tapped=tapped, more=more,
    )  # fmt: skip
    if isinstance(got, AnalysisRecord):
        return Answered(got, None, None)
    reading = got
    if offer_tap and wants_tap(reading.rec.observation, data):
        return Tap(reading)
    try:
        clean = as_jpeg(strip_metadata(data, mime))
        photo = person.store.put_photo(reading.rec.record_id, clean, make_thumbnail(clean))
        plants, latest = person.store.list_plants(), person.store.latest_by_plant()
    except (HistoryError, ValueError):
        log.exception("history unavailable at upload run=%s", reading.rec.record_id)
        rec = decide(deps, reading, told, progress=progress)
        rec.notes.append(HISTORY_DOWN)
        return Answered(rec, reading, None)
    species, genus, unsure = _who_it_is(reading)
    found = candidates(
        plants,
        latest,
        species=species,
        genus=genus,
        unsure=unsure,
        place=reading.rec.location,
        now=received,
    )
    pending = Pending(person.user_id, photo, told)
    if found:
        thumbs = [(p, latest[p.id], _thumb(person, latest[p.id].photo_path)) for p in found]
        return Choose(reading, thumbs, pending)
    try:
        plant_id = new_plant(person, reading)
    except HistoryError:
        log.exception("could not create the plant")
        rec = decide(deps, reading, told, progress=progress)
        rec.notes.append(HISTORY_DOWN)
        return Answered(rec, reading, None)
    return answer_for_plant(deps, person, reading, plant_id, pending, received, progress=progress)


def surer(
    deps: Deps,
    person: Person,
    got: AnalysisRecord | Reading,
    plant_id: str,
    photo: bytes,
    told: Told | None,
    now: datetime,
    *,
    progress: Progress | None = None,
) -> Answered:
    """ "Add photos for a surer answer", signed in: the plant is known, so no "which plant is
    this?"; the fresh answer joins it with the first photo (held, metadata gone)."""
    if isinstance(got, AnalysisRecord):
        return Answered(got, None, None)
    try:
        clean = as_jpeg(photo)  # stored as JPEG whatever it was held as (a small PNG stays one)
        path = person.store.put_photo(got.rec.record_id, clean, make_thumbnail(clean))
    except (HistoryError, ValueError):
        log.exception("history unavailable for more photos run=%s", got.rec.record_id)
        rec = decide(deps, got, told, progress=progress)
        rec.notes.append(HISTORY_DOWN)
        return Answered(rec, got, None)
    pending = Pending(person.user_id, path, told)
    return answer_for_plant(deps, person, got, plant_id, pending, now, progress=progress)


def keep_for_plant(
    person: Person, reading: Reading, rec: AnalysisRecord, plant_id: str, now, chat=()
):
    """A claimed answer stored on a plant exactly as it was shown: no model call, no new
    words; the record only gains its owner and its plant, and keeps its chat so far."""
    person.store.add_answer(_stored(reading, rec, plant_id, None, now))  # HistoryError rises
    try:  # the answer is kept: its chat follows if it can, never a reason to keep it twice
        for msg in chat:
            person.store.add_chat(rec.record_id, msg)
    except HistoryError:
        log.exception("could not copy the chat to the kept answer run=%s", rec.record_id)
    return Answered(rec, reading, None)


def add_photo(person: Person, answer_id: str, data: bytes, mime: str) -> bool:
    """The tab's own copy, added to a kept answer only when the person asks: False when the
    answer is not theirs or already has a photo. HistoryError and ValueError rise."""
    stored = person.store.get_answer(answer_id)
    if stored is None or stored.photo_path:
        return False
    clean = as_jpeg(strip_metadata(data, mime))
    path = person.store.put_photo(answer_id, clean, make_thumbnail(clean))
    person.store.set_photo(answer_id, path)
    return True


def likely_plants(
    person: Person, reading: Reading, now: datetime
) -> list[tuple[Plant, StoredAnswer, str | None]]:
    """The person's plants this answer could be, as the signed-in upload asks: none means
    a new plant."""
    plants, latest = person.store.list_plants(), person.store.latest_by_plant()
    species, genus, unsure = _who_it_is(reading)
    found = candidates(
        plants,
        latest,
        species=species,
        genus=genus,
        unsure=unsure,
        place=reading.rec.location,
        now=now,
    )
    return [(p, latest[p.id], _thumb(person, latest[p.id].photo_path)) for p in found]


def keep_new(
    person: Person, reading: Reading, rec: AnalysisRecord, now: datetime, chat=()
) -> Answered:
    """A kept answer on a new plant, never decided again; no empty plant left behind when the
    answer cannot be stored (HistoryError rises, so the claim can be undone and retried)."""
    plant_id = new_plant(person, reading)
    try:
        return keep_for_plant(person, reading, rec, plant_id, now, chat)
    except HistoryError:
        try:
            person.store.delete_plant(plant_id)
        except HistoryError:
            log.exception("could not remove the empty plant %s", plant_id)
        raise


def _thumb(person: Person, path: str | None) -> str | None:
    return person.store.photo_url(path) if path else None


def refine_stored(
    deps: Deps,
    person: Person,
    answer_id: str,
    told: Told,
    cached: Callable[[str], tuple[Reading, str | None] | None],
    before_model: Callable[[], None] = lambda: None,
    set_reading: Callable[[str, Reading], None] | None = None,
) -> tuple[AnalysisRecord, int | None] | None:
    """Refine a signed-in person's answer: the cached reading when there is one, else the
    stored row's; with the plant's other visits as history; the new answer is kept.
    None when the answer is neither cached nor stored for this person. `before_model` runs
    just before the advisor does (it may raise to refuse)."""
    try:
        stored = person.store.get_answer(answer_id)
    except HistoryError:
        log.exception("could not read the stored answer")
        stored = None
    hit = cached(answer_id)
    if hit is None and stored is None:
        return None
    if hit is not None:
        reading, first = hit
    else:
        reading, first = reading_from(stored), stored.answer.headline if stored.answer else None
    if told.place or told.setting:
        reading = as_told(deps, reading, told)
        if set_reading is not None:
            set_reading(answer_id, reading)
    history, last, note = None, None, None
    if stored is not None:
        try:
            past = [a for a in person.store.answers_for(stored.plant_id) if a.id != stored.id]
            scores = person.store.scores_for(stored.plant_id)
            taken = reading.rec.taken_at
            history = (
                history_for(past, reading.rec.observation, taken, scores, reading.rec.problem)
                if past
                else None
            )
            last = last_decline(past, taken)
        except HistoryError:
            log.exception("could not read the plant's history")
            note = HISTORY_DOWN
    before_model()
    rec = decide(deps, reading, told, history)
    rec.refined_from = first
    if stored is not None:
        try:
            person.store.update_answer(
                stored.id,
                rec.answer,
                told,
                evidence_of(reading) if told.place or told.setting else None,
            )
            reminding.replan(person, stored.id)
        except HistoryError:
            log.exception("could not keep the refined answer")
            note = HISTORY_DOWN
    if note:
        rec.notes.append(note)
    return rec, last
