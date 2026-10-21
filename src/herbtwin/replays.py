"""The same uploaded file, place and question on the same day gets the same answer (17 Oct).

The advisor is asked three times at different temperatures, so the same photo could get a
different headline on a second upload (10 of 50 repeat runs changed, docs/reference/
nvidia-models.md). Judges re-upload the samples, so a repeat now gets a copy of the first
complete answer under its own new id: no model calls, and nothing is shared between
visitors (the chat lives on the answer id). Signed-out reads only; kept in memory, like
the answers themselves.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime

from herbtwin.pipeline import Reading
from herbtwin.schemas import AnalysisRecord, Told

MAX_ENTRIES = 200  # bounded memory: the oldest is dropped first


@dataclass(frozen=True)
class Replay:
    reading: Reading | None
    first: AnalysisRecord  # the complete photo-only answer, before any refine
    day: date

    def copy(self, record_id: str) -> tuple[AnalysisRecord, Reading | None]:
        """The answer again under a new id, so a second visitor never sees the first's
        chat or refines."""
        rec = self.first.model_copy(deep=True, update={"record_id": record_id})
        if self.reading is None:
            return rec, None
        base = self.reading.rec.model_copy(deep=True, update={"record_id": record_id})
        return rec, replace(self.reading, rec=base)


def replay_key(
    upload_sha256: str,
    device: tuple[float, float] | None,
    place: str | None,
    told: Told | None,
    day: date,
) -> str:
    """Everything that changes the answer from the person's side, and the day (the
    forecast moves daily). The place text is compared ignoring case and spaces."""
    parts = [
        upload_sha256,
        "" if device is None else f"{device[0]!r},{device[1]!r}",  # as sent, never rounded
        " ".join((place or "").lower().split()),
        "" if told is None else told.model_dump_json(exclude_none=True),
        day.isoformat(),
    ]
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


class ReplayCache:
    def __init__(self, clock: Callable[[], datetime], max_entries: int = MAX_ENTRIES) -> None:
        self._clock, self._max = clock, max_entries
        self._entries: OrderedDict[str, Replay] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Replay | None:
        with self._lock:
            hit = self._entries.get(key)
            if hit is None:
                return None
            if hit.day != self._clock().date():  # a new day: a new forecast, a fresh read
                del self._entries[key]
                return None
            return hit

    def put(self, key: str, reading: Reading | None, first: AnalysisRecord) -> None:
        """Only a complete answer is kept: a read with a failed step (no weather, say)
        is never replayed, so the next upload gets a fresh chance."""
        if first.failures or first.answer is None:
            return
        # a copy: the caller may still change its record (a sign-in note, say), and that
        # must never reach a later visitor's replay
        first = first.model_copy(deep=True)
        if reading is not None:
            reading = replace(reading, rec=reading.rec.model_copy(deep=True))
        with self._lock:
            self._entries[key] = Replay(reading, first, self._clock().date())
            self._entries.move_to_end(key)
            while len(self._entries) > self._max:
                self._entries.popitem(last=False)
