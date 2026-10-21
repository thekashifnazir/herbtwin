import importlib.util
import sqlite3
from pathlib import Path


def _script():
    spec = importlib.util.spec_from_file_location(
        "time_reads", Path(__file__).parents[1] / "scripts" / "time_reads.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_progress_page_link_to_the_answer_is_found():
    body = '<p><a id="next" href="/answers/abc123">See the answer</a></p>'
    assert _script().NEXT.search(body).group(1) == "/answers/abc123"


def test_summary_takes_the_median_and_range_of_finished_reads():
    rows = [
        {"status": "ok", "total_s": 20.0, "backup": False, "cost_usd": 0.004},
        {"status": "ok", "total_s": 30.0, "backup": True, "cost_usd": 0.005},
        {"status": "ok", "total_s": 50.0, "backup": False, "cost_usd": 0.006},
        {"status": "failed"},
    ]
    s = _script().summarise(rows)
    assert (s["n"], s["n_ok"], s["median_s"], s["min_s"], s["max_s"]) == (4, 3, 30.0, 20.0, 50.0)
    assert s["backup_reads"] == 1 and s["cost_usd"] == 0.015


def test_the_trace_store_says_which_model_read_the_photo(tmp_path):
    db = tmp_path / "traces.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE traces (run_id TEXT, stage TEXT, model TEXT, cost_usd REAL)")
        c.executemany(
            "INSERT INTO traces VALUES (?, ?, ?, ?)",
            [
                ("a1", "observe", "zai-org/GLM-5.3-Flash", 0.001),
                ("a1", "observe", "deepseek-ai/DeepSeek-V4.1-Flash", 0.003),
                ("a1", "advise", "nvidia/nemotron-3-super-120b-a12b", 0.004),
                ("b2", "observe", "zai-org/GLM-5.3-Flash", 0.001),
            ],
        )
    got = _script().from_traces(db, "a1")
    assert got["backup"] and got["calls"] == 3 and got["cost_usd"] == 0.008
    assert not _script().from_traces(db, "b2")["backup"]


def _client(handler):
    import httpx

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_a_read_that_never_links_to_an_answer_is_a_failure(tmp_path):
    import httpx

    photo = tmp_path / "p.jpg"
    photo.write_bytes(b"jpeg")
    row = _script().read_once(
        _client(lambda req: httpx.Response(200, text="<p>Something went wrong</p>")),
        "http://x",
        photo,
        "London",
    )
    assert row["status"] == "failed" and row["http"] == 200


def test_the_answer_id_is_taken_from_either_answer_link(tmp_path):
    import httpx

    def handler(req):
        if req.method == "POST":
            return httpx.Response(200, text='<a id="next" href="/answers/abc123/plant">x</a>')
        return httpx.Response(200, text="answer")

    photo = tmp_path / "p.jpg"
    photo.write_bytes(b"jpeg")
    mod = _script()
    row = mod.read_once(_client(handler), "http://x", photo, "London")
    assert row["status"] == "ok" and row["answer_id"] == "abc123"
