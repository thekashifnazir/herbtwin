import asyncio
import base64
import inspect
import json
import threading
import time
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from langsmith import Client

from herbtwin.adapters.base import CallRecord
from herbtwin.config import load_settings
from herbtwin.pipeline import build_deps
from herbtwin.remote_traces import (
    BREAKER_S,
    Batch,
    LangSmithSink,
    RemoteTraces,
    remote_traces_from,
    root_uuid,
)
from herbtwin.tracing import PHOTO_READ, CallScope, TraceRoot
from tests.fakes import FakeSink

NOW = datetime(2026, 10, 12, 9, tzinfo=UTC)
REC = CallRecord(
    model="m1",
    stage="observe",
    prompt="p",
    output="o",
    latency_ms=1500,
    input_tokens=10,
    output_tokens=5,
    cost_usd=0.001,
    local=False,
)
RID = uuid.uuid4().hex
PIXELS = base64.b64encode(bytes(range(256)) * 4).decode()


EARLY = NOW - timedelta(seconds=10)  # when the tracer was made


def _at(root: TraceRoot, started: datetime = EARLY, request=None) -> CallScope:
    return CallScope(root, started, request)


def _offline(sink, **kw) -> RemoteTraces:
    return RemoteTraces(sink, clock=lambda: NOW, background=False, **kw)


def test_a_photo_read_is_one_trace_with_a_run_per_stage():
    sink = FakeSink()
    t = _offline(sink)
    root = _at(TraceRoot(RID, PHOTO_READ))
    t.record(root, REC)
    for _ in range(3):
        t.record(root, replace(REC, stage="advise", model="m2"))
    assert sink.runs == [] and t.pending == 7  # nothing goes until a flush (background off)
    assert t.flush() and t.pending == 0
    [top] = sink.roots()
    assert top["id"] == uuid.UUID(RID) and top["name"] == PHOTO_READ
    assert top["run_type"] == "chain" and top["trace_id"] == uuid.UUID(RID)
    stages = {r["name"]: r for r in sink.under(uuid.UUID(RID))}
    assert set(stages) == {"observe", "advise"}
    calls = [r for r in sink.runs if r["run_type"] == "llm"]
    assert [c["parent_run_id"] for c in calls] == [stages["observe"]["id"]] + [
        stages["advise"]["id"]
    ] * 3
    first = calls[0]
    assert first["name"] == "m1" and first["trace_id"] == uuid.UUID(RID)
    assert first["inputs"] == {"prompt": "p"} and first["outputs"]["output"] == "o"
    assert first["outputs"]["usage_metadata"] == {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "total_cost": 0.001,
    }
    meta = first["extra"]["metadata"]
    assert meta["ls_model_name"] == "m1" and meta["ls_provider"] == "nebius"
    assert meta["latency_ms"] == 1500 and meta["cost_usd"] == 0.001
    assert first["end_time"] - first["start_time"] == timedelta(milliseconds=1500)
    assert first["dotted_order"].startswith(stages["observe"]["dotted_order"] + ".")
    assert stages["observe"]["dotted_order"].startswith(top["dotted_order"] + ".")
    # later calls are new child runs: nothing is re-created or patched (LangSmith takes one
    # update per run and refuses a stage's without its parent; 12 Oct live logs)
    assert sink.updates == []


def test_a_later_call_joins_the_trace_it_belongs_to():
    sink = FakeSink()
    t = _offline(sink)
    t.record(_at(TraceRoot(RID, PHOTO_READ)), REC)
    t.flush()
    t.record(_at(TraceRoot(RID, PHOTO_READ)), replace(REC, stage="advise"))  # the plant choice
    t.flush()
    assert len(sink.roots()) == 1 and len(sink.under(uuid.UUID(RID))) == 2


def test_nothing_private_reaches_the_sink():
    sink = FakeSink()
    t = _offline(sink)
    prompt = (
        f'[{{"type": "image_url", "url": "data:image/png;base64,{PIXELS}"}}] '
        'mail kash@example.com at 51.5072, -0.1276 {"lat": 51.5, "lon": -0.12}'
    )
    rec = replace(REC, prompt=prompt, output="ok kash@example.com 51.507, -0.128")
    t.record(_at(TraceRoot(RID, "chat", {"note": "kash@example.com"})), rec)
    t.feedback(RID, "worse", "seen at lat 51.5 by kash@example.com")
    t.flush()
    assert sink.runs and sink.feedback
    sent = json.dumps([sink.runs, sink.updates, sink.feedback], default=str)
    for leak in (PIXELS[:40], "base64,", "kash@example.com", "51.5", "0.12"):
        assert leak not in sent, leak


def test_a_failing_sink_is_logged_and_never_raised(caplog):
    sink = FakeSink(down=True)
    t = _offline(sink)
    t.record(_at(TraceRoot(RID, PHOTO_READ)), REC)
    t.feedback(RID, "improved")
    assert t.flush() and t.pending == 0
    assert "could not send a trace" in caplog.text
    sink.down = False
    t.record(_at(TraceRoot(RID, PHOTO_READ)), REC)
    t.flush()
    assert sink.runs  # the next one still goes


class _Stuck(FakeSink):
    def __init__(self):
        super().__init__()
        self.release = threading.Event()

    def create_run(self, run):
        self.release.wait(5)
        super().create_run(run)


def test_sending_is_in_the_background_and_flush_gives_up_on_time(caplog):
    sink = _Stuck()
    t = RemoteTraces(sink)
    started = time.monotonic()
    t.record(_at(TraceRoot(RID, PHOTO_READ)), REC)
    assert time.monotonic() - started < 0.5  # the call never waits for LangSmith
    assert t.flush(timeout=0.1) is False
    assert time.monotonic() - started < 1.0
    assert "traces still pending" in caplog.text
    sink.release.set()
    assert t.flush(timeout=5) is True and len(sink.runs) == 3


def test_too_many_pending_are_dropped_with_a_warning(caplog):
    sink = FakeSink()
    t = _offline(sink, max_pending=4)
    t.record(_at(TraceRoot(RID, PHOTO_READ)), REC)  # three runs
    t.record(_at(TraceRoot(RID, PHOTO_READ)), REC)  # a fourth run
    t.record(_at(TraceRoot(RID, PHOTO_READ)), REC)  # a fifth: dropped
    assert t.pending == 4 and "dropped" in caplog.text


def test_old_traces_are_forgotten():
    sink = FakeSink()
    t = _offline(sink, max_traces=1)
    first, second = uuid.uuid4().hex, uuid.uuid4().hex
    t.record(_at(TraceRoot(first, PHOTO_READ)), REC)
    t.record(_at(TraceRoot(second, PHOTO_READ)), REC)
    t.record(_at(TraceRoot(second, PHOTO_READ)), REC)
    t.flush()
    assert [r["id"] for r in sink.roots()] == [uuid.UUID(first), uuid.UUID(second)]


def test_outcome_feedback_goes_to_the_earlier_reads_root():
    sink = FakeSink()
    t = _offline(sink)
    stored = str(uuid.UUID(RID))  # the stored answer id comes back hyphenated
    for result in ("improved", "no_clear_change", "worse", "cant_tell", "not_done"):
        t.feedback(stored, result, "r")
    t.feedback(stored, "not_scored_yet")
    t.flush()
    assert sink.feedback == [
        (uuid.UUID(RID), "outcome", "improved", "r"),
        (uuid.UUID(RID), "outcome", "no clear change", "r"),
        (uuid.UUID(RID), "outcome", "worse", "r"),
        (uuid.UUID(RID), "outcome", "can't tell", "r"),
    ]


def test_a_key_that_is_not_a_uuid_still_gets_a_stable_id():
    assert root_uuid("case-3") == root_uuid("case-3") != root_uuid("case-4")
    assert root_uuid(RID) == uuid.UUID(RID)


def test_the_hook_never_raises(caplog):
    t = _offline(FakeSink())
    t.record(_at(TraceRoot(RID, PHOTO_READ)), "not a record")  # type: ignore[arg-type]
    t.feedback(RID, "improved", 42)  # type: ignore[arg-type]
    assert "could not trace" in caplog.text


def test_a_stage_starts_when_its_tracer_was_made():
    # the advisor's asks run in parallel: the first to finish need not have started first
    sink = FakeSink()
    t = _offline(sink)
    at = _at(TraceRoot(RID, PHOTO_READ), started=NOW - timedelta(seconds=5))
    t.record(at, replace(REC, stage="advise", latency_ms=1000))  # ends first
    t.record(at, replace(REC, stage="advise", latency_ms=4000))  # started earlier
    t.flush()
    [top] = sink.roots()
    [stage] = sink.under(top["id"])
    calls = sink.under(stage["id"])
    assert top["start_time"] == stage["start_time"] == NOW - timedelta(seconds=5)
    assert all(stage["start_time"] <= c["start_time"] for c in calls)
    assert (
        stage["dotted_order"]
        .split(".")[-1]
        .startswith(f"{NOW - timedelta(seconds=5):%Y%m%dT%H%M%S%fZ}")
    )


def test_a_call_that_started_before_its_tracer_still_starts_its_stage():
    sink = FakeSink()
    t = _offline(sink)
    t.record(_at(TraceRoot(RID, PHOTO_READ), started=NOW), REC)  # clocks a little apart
    t.flush()
    assert sink.roots()[0]["start_time"] == NOW - timedelta(milliseconds=1500)


def test_a_request_waits_only_for_its_own_traces():
    sink = _Stuck()
    t = RemoteTraces(sink)
    mine, other = Batch(), Batch()
    t.record(_at(TraceRoot(RID, PHOTO_READ), request=other), REC)  # stuck in the sender

    async def go():
        began = time.monotonic()
        assert await t.settle(mine) is True  # queued nothing: no wait at all
        quick = time.monotonic() - began
        t.record(_at(TraceRoot(uuid.uuid4().hex, PHOTO_READ), request=mine), REC)
        began = time.monotonic()
        ok = await t.settle(mine, timeout=0.1)
        return quick, ok, time.monotonic() - began

    try:
        quick, ok, waited = asyncio.run(go())
        assert quick < 0.05 and ok is False and 0.1 <= waited < 1.0
    finally:
        sink.release.set()
    assert t.flush(timeout=5) and mine.pending == other.pending == 0


def test_after_a_timeout_waits_are_skipped_until_the_queue_drains(caplog):
    sink = _Stuck()
    mono = [100.0]
    t = RemoteTraces(sink, monotonic=lambda: mono[0])
    first, second = Batch(), Batch()
    t.record(_at(TraceRoot(RID, PHOTO_READ), request=first), REC)
    t.record(_at(TraceRoot(RID, PHOTO_READ), request=second), REC)

    async def timed(batch, timeout):
        began = time.monotonic()
        ok = await t.settle(batch, timeout=timeout)
        return ok, time.monotonic() - began

    try:
        assert asyncio.run(timed(first, 0.1))[0] is False and t.paused
        ok, took = asyncio.run(timed(second, 5))
        assert ok is False and took < 0.05  # LangSmith is struggling: nobody waits
        mono[0] += BREAKER_S + 1
        ok, took = asyncio.run(timed(second, 0.1))
        assert ok is False and took >= 0.1  # a minute later, one request tries again
        assert caplog.text.count("traces still pending") == 2
    finally:
        sink.release.set()
    assert t.flush(timeout=5) and not t.paused  # all sent: no longer paused


# --- the LangSmith sink and wiring ---

PROJECT = uuid.uuid4()
BASE = {"HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "-0.12"}


class _RecordingClient:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return SimpleNamespace(id=PROJECT)

        return call


def test_no_key_no_traces(tmp_path):
    assert remote_traces_from(load_settings(BASE)) is None
    deps = build_deps(load_settings(BASE), tmp_path / "t.db")
    assert deps.traces is None and deps.trace_store.on_record is None


def test_a_key_wires_the_store_to_langsmith(tmp_path):
    s = load_settings({**BASE, "HERBTWIN_LANGSMITH_API_KEY": "lsv2-test"})
    deps = build_deps(s, tmp_path / "t.db")
    assert isinstance(deps.traces._sink, LangSmithSink)
    assert deps.traces._sink.project == "herbtwin-dev"
    assert deps.trace_store.on_record == deps.traces.record


def test_the_sink_calls_bind_to_the_sdk():
    client = _RecordingClient()
    t = RemoteTraces(LangSmithSink(client, "p"), background=False)
    t.record(_at(TraceRoot(RID, PHOTO_READ)), REC)
    t.record(_at(TraceRoot(RID, PHOTO_READ)), REC)
    t.feedback(RID, "improved", "less droop")
    t.flush()
    names = [n for n, _, _ in client.calls]
    assert names == ["create_run"] * 3 + [
        "create_run",
        "read_project",
        "create_feedback",
    ]
    for name, args, kwargs in client.calls:
        inspect.signature(getattr(Client, name)).bind(None, *args, **kwargs)
    assert all(kw["project_name"] == "p" for n, _, kw in client.calls if n == "create_run")
    _, args, kwargs = client.calls[-1]
    assert args == (uuid.UUID(RID), "outcome") and kwargs["value"] == "improved"
    assert kwargs["trace_id"] == uuid.UUID(RID) and kwargs["comment"] == "less droop"
    assert kwargs["session_id"] == str(PROJECT) and kwargs["stop_after_attempt"] == 1


def test_the_sdk_tries_each_send_once_and_briefly(monkeypatch):
    t = remote_traces_from(load_settings({**BASE, "HERBTWIN_LANGSMITH_API_KEY": "lsv2-test"}))
    client = t._sink.client
    assert client.retry_config.total == 0 and client.timeout_ms == (2000, 3000)
    seen = []

    def attempts(self, method, path, *, stop_after_attempt=1, **kwargs):
        seen.append(stop_after_attempt)

    monkeypatch.setattr(Client, "request_with_retries", attempts)
    client.request_with_retries("POST", "/runs", stop_after_attempt=3)  # as create_run asks
    assert seen == [1]


def test_feedback_goes_without_the_project_id_when_it_cannot_be_read(caplog):
    class NoProject(_RecordingClient):
        def read_project(self, **kwargs):
            raise ConnectionError("down")

    client = NoProject()
    t = RemoteTraces(LangSmithSink(client, "p"), background=False)
    t.feedback(RID, "worse")
    t.flush()
    [(name, _, kwargs)] = client.calls
    assert name == "create_feedback" and kwargs["session_id"] is None
    assert "could not look up the LangSmith project" in caplog.text


def test_an_eu_account_sends_to_the_eu_host():
    # a key from an EU LangSmith account is refused (403) by the default US host
    eu = "https://eu.api.smith.langchain.com"
    on = {**BASE, "HERBTWIN_LANGSMITH_API_KEY": "lsv2-test"}
    assert remote_traces_from(load_settings(on))._sink.client.api_url != eu
    t = remote_traces_from(load_settings({**on, "HERBTWIN_LANGSMITH_ENDPOINT": eu + "/"}))
    assert t._sink.client.api_url == eu


def test_a_langsmith_endpoint_must_be_https():
    with pytest.raises(ValueError, match="HERBTWIN_LANGSMITH_ENDPOINT"):
        load_settings({**BASE, "HERBTWIN_LANGSMITH_ENDPOINT": "eu.api.smith.langchain.com"})
