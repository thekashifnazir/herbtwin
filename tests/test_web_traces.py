"""LangSmith traces through the web routes (D64), against a fake sink. The traces are made
with no background sender, so anything the sink holds was sent by a flush."""

import json
import threading
import time
import uuid
from datetime import UTC, datetime

import httpx
import pytest
import respx

from herbtwin import remote_traces, scoring
from herbtwin.adapters.base import CallRecord
from herbtwin.remote_traces import Batch, RemoteTraces
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.tracing import PHOTO_READ, CallScope, TraceRoot, current_request
from tests.fakes import NEXT, FakeSink, follow
from tests.test_web import ADV, HOLD, JPEG, OBS, OCT_4, SAMPLE, _client, _first
from tests.test_web_checkup import AGREE_LESS, PASSED, SAGE, _second_visit, _signed_in


def _wire(c, sink: FakeSink | None = None) -> FakeSink:
    sink = sink or FakeSink()
    traces = RemoteTraces(sink, background=False)
    deps = c.app.state.deps
    deps.trace_store.on_record, deps.traces = traces.record, traces
    return sink


def _weather():
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))


@respx.mock
def test_a_streamed_read_is_sent_before_the_page_ends(tmp_path):
    _weather()
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    sink = _wire(c)
    r = c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")})
    rid = NEXT.search(r.text).group(1).rsplit("/", 1)[-1]
    [root] = sink.roots()
    assert root["id"] == uuid.UUID(rid) and root["name"] == PHOTO_READ
    assert {s["name"] for s in sink.under(root["id"])} == {"observe", "advise"}
    assert c.app.state.deps.traces.pending == 0


@respx.mock
def test_the_json_read_is_sent_before_its_response_ends(tmp_path):
    _weather()
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    sink = _wire(c)
    rid = _first(c)
    assert [r["id"] for r in sink.roots()] == [uuid.UUID(rid)]


@respx.mock
def test_langsmith_down_never_touches_the_page(tmp_path, caplog):
    _weather()
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    _wire(c, FakeSink(down=True))
    page = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    assert page.status_code == 200 and "Water it." in page.text
    assert "could not send a trace" in caplog.text


def _calls(sink, root) -> list[str]:
    """The model calls under a root, as stage names."""
    return [s["name"] for s in sink.under(root["id"]) for _ in sink.under(s["id"])]


@respx.mock
def test_a_refine_is_a_trace_of_its_own(tmp_path):
    _weather()
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3 + [HOLD] * 3)
    sink = _wire(c)
    rid = _first(c)
    assert c.post(f"/answers/{rid}/refine", data={"soil_feel": "wet"}).status_code == 200
    read, refine = sink.roots()
    assert read["id"] == uuid.UUID(rid) and _calls(sink, read) == ["observe"] + ["advise"] * 3
    assert refine["name"] == "refine" and refine["id"] != read["id"]
    assert refine["extra"]["metadata"] == {"answer_id": rid}
    assert _calls(sink, refine) == ["advise"] * 3


@respx.mock
def test_a_chat_message_is_a_trace_of_its_own(tmp_path):
    _weather()
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3 + ["Water it tonight."])
    sink = _wire(c)
    rid = _first(c)
    r = c.post(f"/api/answers/{rid}/chat", json={"message": "When?"})
    assert r.status_code == 200
    read, chat = sink.roots()
    assert chat["name"] == "chat" and chat["extra"]["metadata"] == {"answer_id": rid}
    assert _calls(sink, chat) == ["chat"] and len(_calls(sink, read)) == 4


@pytest.fixture
def _gate(monkeypatch):
    monkeypatch.setattr(scoring, "load_gate", lambda: PASSED)


def _earlier(hist, plant, later: str) -> str:
    [earlier] = [a.id for a in hist.for_user("u1").answers_for(plant.id) if a.id != later]
    return earlier


@respx.mock
def test_a_scored_checkup_is_feedback_on_the_earlier_read(tmp_path, _gate):
    _weather()
    now = [OCT_4]
    c, hist = _signed_in(tmp_path, [json.dumps(SAGE)] * 2 + AGREE_LESS, now)
    sink = _wire(c)
    rid, _, plant = _second_visit(c, hist, now)
    assert c.post(f"/answers/{rid}/did-it", data={"did_it": "yes"}).status_code == 200
    earlier = _earlier(hist, plant, rid)
    [(run_id, key, value, _)] = sink.feedback
    assert (run_id, key, value) == (uuid.UUID(earlier), "outcome", "improved")
    assert uuid.UUID(earlier) in {r["id"] for r in sink.roots()}  # the read it scores
    [checkup] = [r for r in sink.roots() if r["name"] == "checkup"]
    assert checkup["extra"]["metadata"] == {"answer_id": rid}
    assert _calls(sink, checkup) == ["compare"] * 4


@respx.mock
def test_a_skipped_checkup_is_cant_tell(tmp_path, _gate):
    _weather()
    now = [OCT_4]
    c, hist = _signed_in(tmp_path, [json.dumps(SAGE)] * 2, now)
    sink = _wire(c)
    rid, _, plant = _second_visit(c, hist, now)
    c.post(f"/answers/{rid}/did-it", data={"did_it": "skip"})
    [(run_id, _, value, _)] = sink.feedback
    assert (run_id, value) == (uuid.UUID(_earlier(hist, plant, rid)), "can't tell")


class _Stuck(FakeSink):
    """LangSmith hanging: every run waits until released."""

    def __init__(self):
        super().__init__()
        self.release = threading.Event()

    def create_run(self, run):
        self.release.wait(10)
        super().create_run(run)


def _wire_stuck(c) -> tuple[_Stuck, RemoteTraces]:
    sink = _Stuck()
    traces = RemoteTraces(sink)  # a real background sender
    deps = c.app.state.deps
    deps.trace_store.on_record, deps.traces = traces.record, traces
    return sink, traces


REC = CallRecord("m", "observe", "p", "o", 10, 1, 1, 0.0, False)


def test_requests_that_queued_nothing_never_wait(tmp_path):
    c = _client(tmp_path, [], [])
    sink, traces = _wire_stuck(c)
    try:
        traces.record(CallScope(TraceRoot(uuid.uuid4().hex, PHOTO_READ), datetime.now(UTC)), REC)
        assert traces.pending
        began = time.monotonic()
        assert c.get("/healthz").status_code == 200 and c.get("/").status_code == 200
        assert time.monotonic() - began < 0.5
    finally:
        sink.release.set()


@respx.mock
def test_a_read_waits_at_most_the_flush_timeout_then_nobody_waits(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(remote_traces, "FLUSH_S", 0.3)
    _weather()
    c = _client(tmp_path, [json.dumps(OBS)] * 2, [json.dumps(ADV)] * 6)
    sink, traces = _wire_stuck(c)
    waits, settle = [], traces.settle

    async def timed(*args, **kwargs):  # time the trace wait alone, not the whole read
        began = time.monotonic()
        try:
            return await settle(*args, **kwargs)
        finally:
            waits.append(time.monotonic() - began)

    traces.settle = timed
    try:
        _first(c)
        _first(c)
        first, second = waits
        assert 0.3 <= first < 3.0  # waited for its own traces, then gave up
        assert second < 0.1  # LangSmith is struggling: the next read does not wait
        assert caplog.text.count("traces still pending") == 1 and traces.paused
    finally:
        sink.release.set()


@respx.mock
def test_the_streamed_page_waits_for_its_own_read_before_the_jump(tmp_path, monkeypatch):
    seen = []
    real = RemoteTraces.settle

    async def spy(self, batch=None, timeout=None):
        got = batch if batch is not None else current_request()
        seen.append(got.pending if isinstance(got, Batch) else None)
        return await real(self, batch, timeout)

    monkeypatch.setattr(RemoteTraces, "settle", spy)
    _weather()
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    _wire(c)
    follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    # the page's own settle (before the jump) saw the read's sends as this request's
    assert seen[0] == 7  # 4 calls: 3 runs, then 1 run for each advise ask
