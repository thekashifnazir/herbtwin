"""Signed-out answers kept in server memory for an hour, so refine works without an
account (spec section 4). B3's MemoryHistoryStore can take this over."""

from __future__ import annotations

import hmac
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from herbtwin.history import ChatMessage
from herbtwin.pipeline import Reading
from herbtwin.schemas import AnalysisRecord

TTL = timedelta(hours=1)
MAX_ENTRIES = 500  # memory stays bounded: the oldest answer is dropped first


@dataclass
class Entry:
    reading: Reading | None  # None: the run stopped early (not a plant); no refine
    first_headline: str | None  # the photo-only answer, for "what changed"
    at: datetime
    latest: AnalysisRecord  # the answer as it stands, after any refine: the chat's subject
    owner: str | None = None  # the signed-in person's user id; None when signed out
    last_decline: int | None = None  # days since the plant last declined, for the asks
    chat: list[ChatMessage] = field(default_factory=list)
    claim: str | None = None  # signed out: the key of the browser that got it (web/claims.py)


class AnswerCache:
    def __init__(
        self,
        clock: Callable[[], datetime],
        ttl: timedelta = TTL,
        max_entries: int = MAX_ENTRIES,
    ) -> None:
        self._clock, self._ttl, self._max = clock, ttl, max_entries
        self._entries: OrderedDict[str, Entry] = OrderedDict()
        self._lock = threading.Lock()

    def put(
        self,
        reading: Reading | None,
        first: AnalysisRecord,
        owner: str | None = None,
        last_decline: int | None = None,
        claim: str | None = None,
    ) -> None:
        headline = first.answer.headline if first.answer else None
        with self._lock:
            self._entries[first.record_id] = Entry(
                reading, headline, self._clock(), first, owner, last_decline, claim=claim
            )
            while len(self._entries) > self._max:
                self._entries.popitem(last=False)

    def get(self, answer_id: str) -> Entry | None:
        with self._lock:
            entry = self._entries.get(answer_id)
            if entry is None:
                return None
            if self._clock() - entry.at > self._ttl:
                del self._entries[answer_id]
                return None
            return entry

    def get_for(self, answer_id: str, owner: str | None) -> Entry | None:
        """The entry only for the person it was made for (None: signed out), so an answer
        id that leaks never hands one person's answer to another."""
        entry = self.get(answer_id)
        return entry if entry is not None and entry.owner == owner else None

    def claim(self, answer_id: str, key: str, owner: str) -> bool:
        """Keep a signed-out answer for `owner`, once: under the lock, only when it is unowned
        and was made for the browser holding `key`. Its chat, first headline and hour stay.
        False when it is gone, already kept, or not this browser's."""
        with self._lock:
            entry = self._entries.get(answer_id)
            if (
                entry is None
                or entry.owner is not None
                or entry.claim is None
                or not hmac.compare_digest(entry.claim.encode(), key.encode())
            ):
                return False
            entry.owner = owner
            return True

    def unclaim(self, answer_id: str, owner: str) -> None:
        """Undo a claim whose store write failed, so it can be tried again."""
        with self._lock:
            entry = self._entries.get(answer_id)
            if entry is not None and entry.owner == owner and entry.claim is not None:
                entry.owner = None

    def set_latest(self, answer_id: str, rec: AnalysisRecord) -> None:
        with self._lock:
            entry = self._entries.get(answer_id)
            if entry is not None:
                entry.latest = rec

    def set_reading(self, answer_id: str, reading: Reading) -> None:
        with self._lock:
            entry = self._entries.get(answer_id)
            if entry is not None:
                entry.reading = reading

    def add_chat(self, answer_id: str, msg: ChatMessage) -> bool:
        entry = self.get(answer_id)  # drops it if the hour is up
        if entry is None:
            return False
        with self._lock:
            entry.chat.append(msg)
        return True
