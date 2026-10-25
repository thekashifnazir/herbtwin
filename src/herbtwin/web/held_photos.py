"""The photo a plant answer was read from, held for an hour so "Add photos for a surer
answer" can read it again with one or two more (21 Oct, Kash: "not an option in the results
screen to ask us for more photos"). Only the copy the photo model was sent is held: metadata
stripped (no GPS, no date) and at most 1600 px, in memory, never on disk, for an hour
(the answer itself stays 24 hours on the live site, without its photo), newest kept within
a byte cap. Signed in or out, the same rule: the offer and the route both need the held
copy (Kash chose this, 21 Oct).
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

HOLD_FOR = timedelta(hours=1)  # privacy.html: "can no longer be used after an hour"
KEEP_BYTES = 64 * 1024 * 1024  # a model copy is about 0.2 to 0.5 MB: room for over a hundred


@dataclass(frozen=True)
class Held:
    data: bytes
    mime: str
    at: datetime


class HeldPhotos:
    def __init__(
        self, clock: Callable[[], datetime], ttl: timedelta = HOLD_FOR, max_bytes: int = KEEP_BYTES
    ) -> None:
        self._clock, self._ttl, self._max = clock, ttl, max_bytes
        self._held: OrderedDict[str, Held] = OrderedDict()
        self._lock = threading.Lock()

    def _sweep(self, now: datetime) -> None:  # under the lock; oldest first, so stop early
        while self._held and now - next(iter(self._held.values())).at > self._ttl:
            self._held.popitem(last=False)

    def put(self, answer_id: str, data: bytes, mime: str) -> None:
        with self._lock:
            now = self._clock()
            self._sweep(now)  # gone after its hour even if nobody asks for it again
            self._held.pop(answer_id, None)  # held again: it goes to the newest end
            self._held[answer_id] = Held(data, mime, now)
            while len(self._held) > 1 and sum(len(h.data) for h in self._held.values()) > self._max:
                self._held.popitem(last=False)

    def get(self, answer_id: str) -> Held | None:
        with self._lock:
            self._sweep(self._clock())
            return self._held.get(answer_id)
