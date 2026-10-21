from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from herbtwin.adapters.base import CallRecord
from herbtwin.adapters.mock import MockAdapter
from herbtwin.tracing import (
    PHOTO_READ,
    StageTracer,
    TraceStore,
    bind,
    current_root,
    request_scope,
    trace_root,
    traced,
)


def _rec(stage, cost, latency):
    return CallRecord(
        model="m",
        stage=stage,
        prompt="p",
        output="o",
        latency_ms=latency,
        input_tokens=1,
        output_tokens=1,
        cost_usd=cost,
        local=False,
    )


def test_store_logs_and_summarises(tmp_path):
    store = TraceStore(tmp_path / "t.db")
    store.log("run1", _rec("observe", 0.01, 100))
    store.log("run1", _rec("recommend", 0.02, 300))
    store.log("run2", _rec("observe", 0.5, 1))
    s = store.summary("run1")
    assert s["calls"] == 2
    assert s["cost_usd"] == 0.03
    assert s["latency_ms"] == 400
    assert s["by_stage"]["observe"]["calls"] == 1


def test_bind_routes_adapter_calls_into_store(tmp_path):
    store = TraceStore(tmp_path / "t.db")
    adapter = bind(MockAdapter(["x"]), "observe", StageTracer(store, "run9"))
    adapter.complete("s", "u")
    rows = store.rows("run9")
    assert rows[0]["stage"] == "observe" and rows[0]["output"] == "x"


def test_store_survives_reopen(tmp_path):
    TraceStore(tmp_path / "t.db").log("r", _rec("observe", 0, 1))
    assert TraceStore(tmp_path / "t.db").summary("r")["calls"] == 1


def test_bind_does_not_mutate_the_shared_adapter(tmp_path):
    store = TraceStore(tmp_path / "t.db")
    shared = MockAdapter(["a", "b"])
    one = bind(shared, "observe", StageTracer(store, "r1"))
    two = bind(shared, "recommend", StageTracer(store, "r2"))
    assert one.stage == "observe" and two.stage == "recommend"
    assert shared.stage == "unassigned" and shared.on_call is None
    one.complete("s", "u")
    two.complete("s", "u")
    assert store.rows("r1")[0]["stage"] == "observe" and store.rows("r2")[0]["stage"] == "recommend"
    assert shared.responses == []  # scripted responses are still shared, so tests keep working


def test_the_hook_gets_the_photo_read_root_by_default(tmp_path):
    seen = []
    store = TraceStore(tmp_path / "t.db", on_record=lambda at, rec: seen.append((at, rec)))
    before = datetime.now(UTC)
    bind(MockAdapter(["x"]), "observe", StageTracer(store, "abc")).complete("s", "u")
    [(at, rec)] = seen
    assert (at.root.id, at.root.name, rec.stage) == ("abc", PHOTO_READ, "observe")
    assert before <= at.started <= datetime.now(UTC) and at.request is None


def test_a_trace_root_is_fixed_when_the_tracer_is_made(tmp_path):
    seen = []
    store = TraceStore(tmp_path / "t.db", on_record=lambda at, rec: seen.append(at.root))
    with trace_root("refine", answer_id="abc") as root:
        adapter = bind(MockAdapter(["x", "y"]), "advise", StageTracer(store, "abc"))
    with ThreadPoolExecutor(2) as pool:  # the advisor's asks run on pool threads
        list(pool.map(lambda _: adapter.complete("s", "u"), range(2)))
    assert seen == [root, root] and root.metadata == {"answer_id": "abc"}
    assert root.id != "abc" and store.summary("abc")["calls"] == 2


def test_a_broken_hook_never_fails_the_call(tmp_path, caplog):
    def boom(at, rec):
        raise RuntimeError("langsmith down")

    store = TraceStore(tmp_path / "t.db", on_record=boom)
    assert bind(MockAdapter(["x"]), "observe", StageTracer(store, "r")).complete("s", "u") == "x"
    assert store.summary("r")["calls"] == 1 and "trace hook failed" in caplog.text


def test_traced_runs_inside_a_root():
    got = traced("chat", {"answer_id": "a"}, lambda n: (current_root(), n), 3)
    assert got[0].name == "chat" and got[0].metadata == {"answer_id": "a"} and got[1] == 3
    assert current_root() is None


def test_the_request_is_fixed_when_the_tracer_is_made(tmp_path):
    seen = []
    store = TraceStore(tmp_path / "t.db", on_record=lambda at, rec: seen.append(at.request))
    token = object()
    with request_scope(token):
        adapter = bind(MockAdapter(["x"]), "advise", StageTracer(store, "abc"))
    with ThreadPoolExecutor(1) as pool:
        pool.submit(adapter.complete, "s", "u").result()
    assert seen == [token]
