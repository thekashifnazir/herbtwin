"""One sqlite row per model call. Offline, always on. LangSmith hangs off on_record (D64):
each call goes there with the trace it belongs to."""

from __future__ import annotations

import copy
import logging
import sqlite3
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import time

from herbtwin.adapters.base import CallRecord, ModelAdapter

log = logging.getLogger(__name__)

PHOTO_READ = "photo read"


@dataclass(frozen=True)
class TraceRoot:
    """One trace in LangSmith. A photo read's id is its record id (so a later score of its
    advice finds it); a refine, chat message or checkup gets a new id of its own."""

    id: str
    name: str
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CallScope:
    """Where a traced call belongs, fixed when its tracer is made: the trace; when the
    tracer was made (no call through it started earlier, so its stage starts here); and
    the request that waits for its trace to be sent (opaque here; None outside one)."""

    root: TraceRoot
    started: datetime
    request: object | None = None


_ROOT: ContextVar[TraceRoot | None] = ContextVar("trace_root", default=None)
_REQUEST: ContextVar[object | None] = ContextVar("trace_request", default=None)


def current_root() -> TraceRoot | None:
    return _ROOT.get()


def current_request() -> object | None:
    return _REQUEST.get()


@contextmanager
def request_scope(token: object) -> Iterator[object]:
    """Calls traced inside this block (tracers made here) belong to this request."""
    reset = _REQUEST.set(token)
    try:
        yield token
    finally:
        _REQUEST.reset(reset)


@contextmanager
def trace_root(name: str, **metadata: str) -> Iterator[TraceRoot]:
    """Calls traced inside this block (tracers made here) form a trace of their own."""
    root = TraceRoot(uuid.uuid4().hex, name, dict(metadata))
    token = _ROOT.set(root)
    try:
        yield root
    finally:
        _ROOT.reset(token)


def traced(name: str, metadata: dict, fn: Callable, *args, **kwargs):
    """`fn(*args, **kwargs)` inside a trace of its own: for run_in_threadpool, whose
    worker thread is where the tracers get made."""
    with trace_root(name, **metadata):
        return fn(*args, **kwargs)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS traces (
  id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, stage TEXT NOT NULL, model TEXT NOT NULL,
  prompt TEXT, output TEXT, latency_ms INTEGER, input_tokens INTEGER, output_tokens INTEGER,
  cost_usd REAL, local INTEGER DEFAULT 0, ts REAL
);
CREATE INDEX IF NOT EXISTS traces_run ON traces(run_id);
"""


class TraceStore:
    def __init__(
        self,
        path: str | Path,
        on_record: Callable[[CallScope, CallRecord], None] | None = None,
    ):
        self.path = str(path)
        self.on_record = on_record
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    def log(self, run_id: str, rec: CallRecord, scope: CallScope | None = None) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO traces(run_id, stage, model, prompt, output, latency_ms, input_tokens,"
                " output_tokens, cost_usd, local, ts) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    rec.stage,
                    rec.model,
                    rec.prompt,
                    rec.output,
                    rec.latency_ms,
                    rec.input_tokens,
                    rec.output_tokens,
                    rec.cost_usd,
                    int(rec.local),
                    time(),
                ),
            )
            rowid = int(cur.lastrowid)
        if self.on_record is not None:
            try:
                at = scope or CallScope(TraceRoot(run_id, PHOTO_READ), datetime.now(UTC))
                self.on_record(at, rec)
            except Exception:  # noqa: BLE001 - a model call never fails for its trace
                log.exception("trace hook failed run=%s", run_id)
        return rowid

    def rows(self, run_id: str) -> list[dict]:
        with self._conn() as c:
            return [
                dict(r)
                for r in c.execute("SELECT * FROM traces WHERE run_id=? ORDER BY id", (run_id,))
            ]

    def summary(self, run_id: str) -> dict:
        rows = self.rows(run_id)
        by_stage: dict[str, dict] = {}
        for r in rows:
            s = by_stage.setdefault(r["stage"], {"calls": 0, "cost_usd": 0.0, "latency_ms": 0})
            s["calls"] += 1
            s["cost_usd"] = round(s["cost_usd"] + r["cost_usd"], 6)
            s["latency_ms"] += r["latency_ms"]
        return {
            "calls": len(rows),
            "cost_usd": round(sum(r["cost_usd"] for r in rows), 6),
            "latency_ms": sum(r["latency_ms"] for r in rows),
            "by_stage": by_stage,
        }


class StageTracer:
    def __init__(self, store: TraceStore, run_id: str) -> None:
        self.store, self.run_id = store, run_id
        # fixed here, not per call: the advisor's asks run on pool threads, which do not
        # see the context of the request that bound them
        self.scope = CallScope(
            current_root() or TraceRoot(run_id, PHOTO_READ),
            datetime.now(UTC),
            current_request(),
        )

    def __call__(self, rec: CallRecord) -> None:
        self.store.log(self.run_id, rec, self.scope)


def bind(adapter: ModelAdapter, stage: str, tracer: StageTracer) -> ModelAdapter:
    """A per-run shallow copy: concurrent runs must not share stage/on_call on one adapter."""
    bound = copy.copy(adapter)
    bound.stage = stage
    bound.on_call = tracer
    return bound
