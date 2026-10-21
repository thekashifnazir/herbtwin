"""The quick questions asked on the wait page (21 Oct, Kash: "use the wait"). Replies that
come in before the advisor starts go into this answer; replies after that are kept for the
reveal, where "See your answer" checks the advice again with them (a refine). Never waited
on: skipping is fine, and the answer page asks the same questions again.

In memory, like the answer cache: one instance runs the site, and a wait lasts minutes."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Literal

from herbtwin.schemas import Told

TTL_S = 30 * 60.0  # a wait, its answer and a slow reveal; then the replies are dropped
MAX_WAITS = 2000

# into this answer / on reveal / under the answer (it asks which plant first) / unknown
# "kept": "not sure" after the advice started, with nothing left to check again: the answer
# already used the earlier reply
Counted = Literal["now", "later", "below", "kept", "gone"]


@dataclass
class Wait:
    owner: str | None  # the signed-in person's user id; None when signed out
    base: Told | None  # what came with the upload (its question)
    replies: Told | None = None  # every reply so far, the newest winning per question
    taken: Told | None = None  # what went into the answer, once the advisor started
    started: bool = False  # the advisor has started: a new reply counts on reveal
    elsewhere: bool = False  # the read asks which plant first: a new reply is asked again
    target: str | None = None  # where the read landed
    applied: bool = False  # the late replies have had their refine
    at: float = 0.0


def joined(base: Told | None, extra: Told | None) -> Told | None:
    """`base` with `extra`'s answers on top; None when both are empty."""
    if extra is None:
        return base
    merged = {
        **(base.model_dump(exclude_none=True) if base else {}),
        **extra.model_dump(exclude_none=True),
    }
    told = Told.model_validate(merged)
    return None if told.is_empty() else told


class Waits:
    """Bounded and thread-safe: the oldest wait is dropped first."""

    def __init__(self, ttl_s: float = TTL_S, max_entries: int = MAX_WAITS, clock=time.monotonic):
        self._ttl, self._max, self._clock = ttl_s, max_entries, clock
        self._items: OrderedDict[str, Wait] = OrderedDict()
        self._lock = threading.Lock()

    def start(self, wait_id: str, owner: str | None, base: Told | None) -> None:
        with self._lock:
            self._items[wait_id] = Wait(owner, base, at=self._clock())
            while len(self._items) > self._max:
                self._items.popitem(last=False)

    def _get(self, wait_id: str, owner: str | None) -> Wait | None:
        w = self._items.get(wait_id)
        if w is None or w.owner != owner:
            return None
        if self._clock() - w.at > self._ttl:
            del self._items[wait_id]
            return None
        return w

    def reply(
        self, wait_id: str, owner: str | None, told: Told, cleared: frozenset[str] = frozenset()
    ) -> Counted:
        """Keep a reply. "now" while the advisor has not started, else "later". `cleared`:
        questions answered "not sure" since, so an earlier answer to them no longer counts."""
        with self._lock:
            w = self._get(wait_id, owner)
            if w is None:
                return "gone"
            w.replies = joined(w.replies, told)
            if cleared and w.replies is not None:
                kept = w.replies.model_dump(exclude_none=True, exclude=set(cleared))
                w.replies = Told.model_validate(kept) if kept else None
            used = w.taken is not None and any(getattr(w.taken, f) for f in cleared)
            if cleared and used and joined(w.base, w.replies) is None:
                # the answer used the earlier reply, and a refine needs something to say
                return "kept"
            if w.elsewhere:
                return "below"
            return "later" if w.started or w.target is not None else "now"

    def take(self, wait_id: str, told: Told | None, answering: bool = True) -> Told | None:
        """The advisor is starting (pipeline.LATE_TOLD): `told` with the replies so far on
        top. On the read's own thread, so no owner check: the id came from that read. Not
        `answering`: the photo asks which plant first, and its answer comes from that page,
        so a reply after this is asked again under the answer, never refined here."""
        with self._lock:
            w = self._items.get(wait_id)
            if w is None:
                return told
            w.started, w.elsewhere = True, not answering
            w.taken = w.replies
            return joined(told, w.replies)

    def finish(self, wait_id: str, target: str) -> None:
        with self._lock:
            if (w := self._items.get(wait_id)) is not None:
                w.target = target

    def late(self, wait_id: str, owner: str | None) -> tuple[str | None, Told | None]:
        """Where the read landed, and the whole told to refine with when a reply came after
        the advisor started (None when there is nothing new). Marks the replies applied, so
        a second tap never refines twice."""
        with self._lock:
            w = self._get(wait_id, owner)
            if w is None:
                return None, None
            if w.applied or w.elsewhere or w.target is None or w.replies == w.taken:
                return w.target, None
            w.applied = True
            return w.target, joined(w.base, w.replies)
