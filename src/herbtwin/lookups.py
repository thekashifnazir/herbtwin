"""Slow outside lookups behind a cache, for the cards that load after the answer page opens
(Seen recently in the UK: sightings.py and reported.py). Each key is fetched once at a time
on a small pool; the page waits a few seconds at most, and a lookup still running when it
gives up fills the cache for the next page. A failure is kept for a short while, so an
outage costs one call per key per few minutes, never one per page."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Hashable, Iterable
from concurrent.futures import Future, ThreadPoolExecutor, wait

log = logging.getLogger(__name__)

FAILED_TTL_S = 300.0  # a failed lookup: asked again in 5 minutes


class Lookups[K: Hashable, V]:
    """fetch(key) -> value, or raises (kept as a failure for FAILED_TTL_S). ttl(value) says
    how long a value holds, in seconds (None: for as long as the key is asked)."""

    def __init__(
        self,
        name: str,
        fetch: Callable[[K], V],
        ttl: Callable[[V], float | None],
        clock: Callable[[], float] | None = None,
        workers: int = 4,
        expected: tuple[type[Exception], ...] = (),
    ):
        self._name, self._fetch, self._ttl = name, fetch, ttl
        self._expected = expected  # an outage or an odd reply: logged in a line
        self._clock = clock or time.monotonic
        # key -> (when, the value or None on a failure, how long it holds)
        self._cache: dict[K, tuple[float, V | None, float | None]] = {}
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix=name)
        self._running: dict[K, Future] = {}

    def cached(self, key: K) -> tuple[bool, V | None]:
        """(True, the value or None for a kept failure) while a lookup holds; else (False, None)."""
        with self._lock:
            got = self._cache.get(key)
        if got is None or (got[2] is not None and self._clock() - got[0] >= got[2]):
            return False, None
        return True, got[1]

    def get_many(self, keys: Iterable[K], timeout: float) -> dict[K, V]:
        """Each key's value, waiting at most `timeout` for the ones not cached; a key that
        failed, or is still being fetched, is left out."""
        out: dict[K, V] = {}
        jobs: dict[K, Future] = {}
        for key in dict.fromkeys(keys):
            held, value = self.cached(key)
            if held:
                if value is not None:
                    out[key] = value
                continue
            with self._lock:  # one lookup per key at a time: a hang must not stack calls
                job = self._running.get(key)
                if job is None:
                    job = self._pool.submit(self._run, key)
                    self._running[key] = job
                    job.add_done_callback(lambda _, k=key: self._done(k))
            jobs[key] = job
        if jobs:
            done, slow = wait(jobs.values(), timeout=timeout)
            if slow:
                log.info("%s: %d lookups slower than %.0f s", self._name, len(slow), timeout)
            for key, job in jobs.items():
                if job in done and job.result() is not None:
                    out[key] = job.result()
        return out

    def _done(self, key: K) -> None:
        with self._lock:
            self._running.pop(key, None)

    def _run(self, key: K) -> V | None:
        try:
            value = self._fetch(key)
        except self._expected as e:
            log.info("%s lookup failed: %s: %s", self._name, type(e).__name__, e)
            self._keep(key, None, FAILED_TTL_S)
            return None
        except Exception:  # noqa: BLE001 - these cards are extra: never a page error
            log.exception("%s lookup broke", self._name)
            self._keep(key, None, FAILED_TTL_S)
            return None
        self._keep(key, value, self._ttl(value))
        return value

    def _keep(self, key: K, value: V | None, ttl: float | None) -> None:
        now = self._clock()
        with self._lock:
            # what has run out goes, so a key per day or month never piles up
            for k in [k for k, (t, _, life) in self._cache.items() if life and now - t >= life]:
                del self._cache[k]
            self._cache[key] = (now, value, ttl)
