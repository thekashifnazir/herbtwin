"""LangSmith as the lasting record of what the live site did (spec section 6, D64).

`traces.db` sits on Cloud Run's in-memory disk and goes with every deploy, so each model
call also becomes a LangSmith run: a root run per trace (a photo read, refine, chat message
or checkup), a child run per stage that calls a model, and the call itself inside it with
its model id, tokens, time and estimated cost. A later score of the advice is attached to
the photo read's root as `outcome` feedback.

Every text is redacted first (no photo, email address or coordinates). Sending happens on
one background thread; a LangSmith failure is logged, never raised. Cloud Run bills CPU
per request, so before a response ends the web layer awaits `settle`: the request waits
(at most FLUSH_S) for the sends it queued itself, and nobody waits for a minute after a
wait timed out (LangSmith slow or down), or until the queue has drained.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

from herbtwin.adapters.base import CallRecord
from herbtwin.config import Settings
from herbtwin.redact import redact, redact_value
from herbtwin.tracing import CallScope, current_request

log = logging.getLogger(__name__)

FLUSH_S = 3.0
BREAKER_S = 60.0  # after a wait timed out, nobody waits for this long
# a score's result as LangSmith feedback; not_done and not_scored_yet say nothing about
# whether the advice worked, so they send none
OUTCOME = {
    "improved": "improved",
    "no_clear_change": "no clear change",
    "worse": "worse",
    "cant_tell": "can't tell",
}


class Sink(Protocol):
    """Where runs go. A run dict holds exactly `langsmith.Client.create_run` keywords."""

    def create_run(self, run: dict) -> None: ...

    def update_run(self, run_id: uuid.UUID, fields: dict) -> None: ...

    def create_feedback(
        self, run_id: uuid.UUID, key: str, value: str, comment: str | None
    ) -> None: ...


def root_uuid(key: str) -> uuid.UUID:
    """A photo read's record id is a uuid4 hex (a stored answer's id the same, hyphenated);
    any other key gets a stable id made from it."""
    try:
        return uuid.UUID(key)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, f"herbtwin:{key}")


def _now() -> datetime:
    return datetime.now(UTC)


def _dotted(start: datetime, run_id: uuid.UUID) -> str:
    return f"{start:%Y%m%dT%H%M%S%fZ}{run_id}"


class Batch:
    """The sends one request queued: what that request waits for before it ends. Counted
    under RemoteTraces' lock."""

    def __init__(self) -> None:
        self.pending = 0
        self.waiters: list[tuple[asyncio.AbstractEventLoop, asyncio.Future]] = []


def _resolve(fut: asyncio.Future) -> None:
    if not fut.done():
        fut.set_result(None)


@dataclass
class _Run:
    id: uuid.UUID
    dotted: str
    end: datetime


@dataclass
class _Trace:
    root: _Run
    stages: dict[str, _Run] = field(default_factory=dict)


class RemoteTraces:
    """The trace store's `on_record` hook, plus outcome feedback, `settle` (a request's own
    sends) and `flush` (everything; scripts and tests).

    `background=False` sends nothing until `settle` or `flush`, on the caller's thread
    (tests use it to see that a flush happened)."""

    def __init__(
        self,
        sink: Sink,
        *,
        clock: Callable[[], datetime] = _now,
        monotonic: Callable[[], float] = time.monotonic,
        background: bool = True,
        max_pending: int = 1000,
        max_traces: int = 500,
    ) -> None:
        self._sink, self._clock, self._background = sink, clock, background
        self._mono = monotonic
        self._paused_until = 0.0  # the breaker: no waiting before this (monotonic)
        self._max_pending, self._max_traces = max_pending, max_traces
        # traces seen lately: a call made in a later request (the plant choice) joins its
        # trace instead of creating the root again
        self._traces: OrderedDict[uuid.UUID, _Trace] = OrderedDict()
        self._lock = threading.Lock()
        self._ops: queue.SimpleQueue[tuple] = queue.SimpleQueue()
        self._idle = threading.Condition()
        self._pending = 0
        self._thread: threading.Thread | None = None

    @property
    def pending(self) -> int:
        with self._idle:
            return self._pending

    @property
    def paused(self) -> bool:
        """True while waits are skipped after one timed out."""
        with self._idle:
            return self._mono() < self._paused_until

    # --- what gets sent ---

    def record(self, scope: CallScope, rec: CallRecord) -> None:
        """One model call. Never raises: a call must not fail for its trace."""
        try:
            self._record(scope, rec)
        except Exception:  # noqa: BLE001 - tracing is a record, never a reason to fail
            log.exception("could not trace a model call")

    def _record(self, scope: CallScope, rec: CallRecord) -> None:
        end = self._clock()
        start = end - timedelta(milliseconds=rec.latency_ms)
        # a new trace or stage starts when its tracer was made, not when its first call to
        # finish began: the advisor's asks run in parallel
        began = min(start, scope.started)
        root, batch = scope.root, scope.request if isinstance(scope.request, Batch) else None
        rid = root_uuid(root.id)
        with self._lock:
            trace = self._traces.get(rid)
            if trace is None:
                trace = _Trace(_Run(rid, _dotted(began, rid), end))
                self._remember(rid, trace)
                meta = redact_value(root.metadata)
                self._create(
                    batch, trace.root, None, rid, root.name, "chain", began, end,
                    metadata=meta, tags=[root.name],
                )  # fmt: skip
            else:
                self._traces.move_to_end(rid)
                self._extend(batch, trace.root, rid, end)
            stage = trace.stages.get(rec.stage)
            if stage is None:
                sid = uuid.uuid4()
                stage = _Run(sid, f"{trace.root.dotted}.{_dotted(began, sid)}", end)
                trace.stages[rec.stage] = stage
                self._create(batch, stage, rid, rid, rec.stage, "chain", began, end)
            else:
                self._extend(batch, stage, rid, end)
            cid = uuid.uuid4()
            call = _Run(cid, f"{stage.dotted}.{_dotted(start, cid)}", end)
            self._create(
                batch,
                call,
                stage.id,
                rid,
                rec.model,
                "llm",
                start,
                end,
                inputs={"prompt": redact(rec.prompt)},
                outputs={
                    "output": redact(rec.output),
                    "usage_metadata": {
                        "input_tokens": rec.input_tokens,
                        "output_tokens": rec.output_tokens,
                        "total_tokens": rec.input_tokens + rec.output_tokens,
                        "total_cost": rec.cost_usd,
                    },
                },
                metadata={
                    "ls_model_name": rec.model,
                    "ls_provider": "local" if rec.local else "nebius",
                    "stage": rec.stage,
                    "latency_ms": rec.latency_ms,
                    "cost_usd": rec.cost_usd,
                },
            )

    def _remember(self, rid: uuid.UUID, trace: _Trace) -> None:
        self._traces[rid] = trace
        while len(self._traces) > self._max_traces:
            self._traces.popitem(last=False)

    def _create(
        self,
        batch: Batch | None,
        run: _Run,
        parent: uuid.UUID | None,
        trace_id: uuid.UUID,
        name: str,
        run_type: str,
        start: datetime,
        end: datetime,
        *,
        inputs: dict | None = None,
        outputs: dict | None = None,
        metadata: dict | None = None,
        tags: list[str] | None = None,
    ) -> None:
        run_dict = {
            "id": run.id,
            "trace_id": trace_id,
            "parent_run_id": parent,
            "dotted_order": run.dotted,
            "name": name,
            "run_type": run_type,
            "inputs": inputs or {},
            "outputs": outputs,
            "start_time": start,
            "end_time": end,
            "extra": {"metadata": metadata or {}},
            "tags": tags or [],
        }
        self._put(batch, "create_run", run_dict)

    def _extend(self, batch: Batch | None, run: _Run, trace_id: uuid.UUID, end: datetime) -> None:
        """A later call in the same trace or stage: noted here only. LangSmith takes one
        update per run (a second is a 409) and refuses a stage's update without its parent
        (a 400), so the root's and stages' end times stay at their first call's end."""
        run.end = max(run.end, end)

    def feedback(self, answer_id: str, result: str, comment: str | None = None) -> None:
        """A score of the advice in an earlier answer (C2), on that photo read's trace.
        Called on the request's own thread, so the request waits for it."""
        try:
            value = OUTCOME.get(result)
            if value is None:
                return
            note = redact(comment) if comment is not None else None
            batch = current_request()
            batch = batch if isinstance(batch, Batch) else None
            self._put(batch, "create_feedback", root_uuid(answer_id), "outcome", value, note)
        except Exception:  # noqa: BLE001 - the score is stored either way
            log.exception("could not trace an outcome")

    # --- sending ---

    def _put(self, batch: Batch | None, *op) -> None:
        with self._idle:
            if self._pending >= self._max_pending:
                log.warning("trace queue full: dropped a %s", op[0])
                return
            self._pending += 1
            if batch is not None:
                batch.pending += 1
        self._ops.put((batch, *op))
        if self._background:
            self._start()

    def _start(self) -> None:
        with self._idle:
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._send_forever, name="langsmith", daemon=True
                )
                self._thread.start()

    def _send_forever(self) -> None:
        while True:
            self._send(self._ops.get())

    def _send(self, op: tuple) -> None:
        batch, name, *args = op
        try:
            getattr(self._sink, name)(*args)
        except Exception as e:  # noqa: BLE001 - LangSmith down must not touch a request
            log.warning("could not send a trace (%s): %s", name, e)
        finally:
            wake: list = []
            with self._idle:
                self._pending -= 1
                if self._pending == 0:
                    self._paused_until = 0.0  # all sent: LangSmith is keeping up again
                if batch is not None:
                    batch.pending -= 1
                    if batch.pending == 0:
                        wake, batch.waiters = batch.waiters, []
                self._idle.notify_all()
            for loop, fut in wake:
                try:
                    loop.call_soon_threadsafe(_resolve, fut)
                except RuntimeError:  # that request's loop has closed
                    pass

    async def settle(self, batch: Batch | None = None, timeout: float | None = None) -> bool:
        """Before a request's response ends: wait for the sends this request queued, at
        most `timeout` (FLUSH_S) seconds, without holding a thread. A request that queued
        nothing never waits; after a wait timed out nobody waits for BREAKER_S seconds or
        until everything pending has gone. True when the request's sends all went."""
        if not self._background:
            return self.flush()
        if batch is None:
            got = current_request()
            batch = got if isinstance(got, Batch) else None
        if batch is None:
            return True
        timeout = FLUSH_S if timeout is None else timeout
        loop = asyncio.get_running_loop()
        with self._idle:
            if batch.pending == 0:
                return True
            if self._mono() < self._paused_until:
                log.debug("LangSmith slow: not waiting for %d sends", batch.pending)
                return False
            fut = loop.create_future()
            batch.waiters.append((loop, fut))
        try:
            await asyncio.wait_for(fut, timeout)
            return True
        except TimeoutError:
            with self._idle:
                self._paused_until = self._mono() + BREAKER_S
                left = self._pending
            log.warning(
                "traces still pending after %.1f s (%d); not waiting for %.0f s", timeout,
                left, BREAKER_S,
            )  # fmt: skip
            return False

    def flush(self, timeout: float = FLUSH_S) -> bool:
        """Wait until everything pending has gone, at most `timeout` seconds (scripts and
        tests; requests use `settle`). True when it all went (or failed and was logged);
        False when time ran out."""
        if not self._background:
            while True:
                try:
                    op = self._ops.get_nowait()
                except queue.Empty:
                    return True
                self._send(op)
        deadline = time.monotonic() + timeout
        with self._idle:
            while self._pending:
                left = deadline - time.monotonic()
                if left <= 0:
                    log.warning("traces still pending after %.1f s: %d", timeout, self._pending)
                    return False
                self._idle.wait(left)
        return True


class LangSmithSink:
    """The only code that touches the SDK. The client sends synchronously (auto-batching
    off): this module's own thread is the background, so a flush means it has all gone."""

    def __init__(self, client, project: str) -> None:
        self.client, self.project = client, project
        self._session: str | None = None

    def create_run(self, run: dict) -> None:
        self.client.create_run(project_name=self.project, **run)

    def update_run(self, run_id: uuid.UUID, fields: dict) -> None:
        self.client.update_run(run_id, **fields)

    def create_feedback(self, run_id: uuid.UUID, key: str, value: str, comment: str | None) -> None:
        self.client.create_feedback(
            run_id,
            key,
            value=value,
            comment=comment,
            trace_id=run_id,
            session_id=self._project_id(),
            stop_after_attempt=1,
        )

    def _project_id(self) -> str | None:
        """Run-level feedback names the run's project by id (the SDK warns without it);
        looked up once. Without it the feedback still goes, the older way."""
        if self._session is None:
            try:
                self._session = str(self.client.read_project(project_name=self.project).id)
            except Exception as e:  # noqa: BLE001 - feedback still goes without it
                log.warning("could not look up the LangSmith project: %s", e)
        return self._session


def remote_traces_from(settings: Settings) -> RemoteTraces | None:
    """LangSmith traces when HERBTWIN_LANGSMITH_API_KEY is set, else None (off)."""
    if not settings.langsmith_api_key:
        return None
    from urllib3.util.retry import Retry

    client = _client_class()(
        api_key=settings.langsmith_api_key,
        api_url=settings.langsmith_endpoint,  # None: the SDK's default (US) host
        auto_batch_tracing=False,
        omit_traced_runtime_info=True,  # no host details in the runs
        # one short try per send: a backlog behind a slow LangSmith must drain, not grow
        timeout_ms=(2000, 3000),
        retry_config=Retry(total=0, raise_on_status=False, raise_on_redirect=False),
    )
    return RemoteTraces(LangSmithSink(client, settings.langsmith_project))


def _client_class():
    """The SDK client, made to try each request once: `create_run` and `update_run` ask
    for 3 attempts with sleeps between, which could hold the sender for ~20 s per run."""
    from langsmith import Client  # only when on: the SDK is not needed otherwise

    class OneTryClient(Client):
        def request_with_retries(self, *args, stop_after_attempt: int = 1, **kwargs):
            return super().request_with_retries(*args, stop_after_attempt=1, **kwargs)

    return OneTryClient
