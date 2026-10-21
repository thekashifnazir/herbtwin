import json

from PIL import Image

from herbtwin.adapters.base import AdapterError
from herbtwin.adapters.mock import MockAdapter
from herbtwin.evals.items import EvalItem
from herbtwin.evals.runner import load_image, prompt_hash, run_observe

OBS = {
    "species": [{"name": "Ocimum basilicum", "common_name": "basil", "confidence": 0.8}],
    "is_plant": True,
    "water_stress": 1,
    "decline": 0,
    "leaf_colour": "green",
    "heat_light_stress": 0,
    "fine_leave_it": False,
    "symptoms": [],
    "leaf_cues": [],
    "soil_surface": "not_visible",
}


def _item(name: str) -> EvalItem:
    return EvalItem(
        id=f"t/{name}",
        set="droop_soybean",
        path=f"img/{name}.jpg",
        root="external",
        label={"droop": 1, "raw": 2},
        cluster="p1",
        licence="CC BY 4.0",
        tag="safe-to-train",
        source="test",
    )


def _tree(tmp_path, names):
    (tmp_path / "ext" / "img").mkdir(parents=True)
    for n in names:
        Image.new("RGB", (40, 30), "green").save(tmp_path / "ext" / "img" / f"{n}.jpg")
    return {"external": tmp_path / "ext"}


def _run(items, adapter, tmp_path, roots):
    return run_observe(
        items,
        adapter,
        backend="mock",
        model="m",
        cache_path=tmp_path / "runs" / "r.jsonl",
        roots=roots,
    )


def test_statuses_cover_ok_missing_and_failed(tmp_path):
    roots = _tree(tmp_path, ["a", "b", "c"])
    items = [_item("a"), _item("gone"), _item("b"), _item("c")]
    # a: ok; b: prose then prose -> failed after repair; c: reply missing decline twice
    no_decline = {k: v for k, v in OBS.items() if k != "decline"}
    adapter = MockAdapter(
        [json.dumps(OBS), "prose", "prose", json.dumps(no_decline), json.dumps(no_decline)]
    )
    rows = _run(items, adapter, tmp_path, roots)
    assert [r["status"] for r in rows] == ["ok", "missing", "failed", "failed"]
    assert rows[0]["observation"]["water_stress"] == 1
    assert "decline" in rows[3]["error"]
    assert rows[2]["calls"] == 2


def test_second_run_is_served_from_cache_and_a_prompt_change_misses_it(tmp_path, monkeypatch):
    roots = _tree(tmp_path, ["a", "b"])
    items = [_item("a"), _item("b")]
    _run(items, MockAdapter([json.dumps(OBS)] * 2), tmp_path, roots)
    again = MockAdapter([])  # any call would raise "mock exhausted"
    rows = _run(items, again, tmp_path, roots)
    assert [r["status"] for r in rows] == ["ok", "ok"] and again.calls == []

    before = prompt_hash()
    monkeypatch.setattr("herbtwin.stages.observe.SYSTEM", "a different prompt")
    assert prompt_hash() != before
    fresh = MockAdapter([json.dumps(OBS)] * 2)
    _run(items, fresh, tmp_path, roots)
    assert len(fresh.calls) == 2


def test_call_errors_are_not_cached(tmp_path):
    roots = _tree(tmp_path, ["a"])

    class Down(MockAdapter):
        def complete_with_image(self, *a, **k):
            raise AdapterError("connection refused")

    rows = _run([_item("a")], Down(), tmp_path, roots)
    assert rows[0]["status"] == "error"
    rows = _run([_item("a")], MockAdapter([json.dumps(OBS)]), tmp_path, roots)
    assert rows[0]["status"] == "ok"


def test_load_image_downscales_large_photos_only(tmp_path):
    big, small = tmp_path / "big.jpg", tmp_path / "small.png"
    Image.new("RGB", (3000, 1500), "red").save(big)
    Image.new("RGB", (100, 50), "red").save(small)
    data, mime = load_image(big, 1024)
    assert mime == "image/jpeg"
    with Image.open(__import__("io").BytesIO(data)) as img:
        assert img.size == (1024, 512)
    data, mime = load_image(small, 1024)
    assert mime == "image/png" and data == small.read_bytes()


def test_a_torn_cache_line_is_skipped_and_that_item_rerun(tmp_path):
    roots = _tree(tmp_path, ["a", "b"])
    items = [_item("a"), _item("b")]
    _run(items, MockAdapter([json.dumps(OBS)] * 2), tmp_path, roots)
    cache = tmp_path / "runs" / "r.jsonl"
    lines = cache.read_text().splitlines()
    cache.write_text(lines[0] + "\n" + lines[1][:20])  # crash mid-write
    again = MockAdapter([json.dumps(OBS)])
    rows = _run(items, again, tmp_path, roots)
    assert [r["status"] for r in rows] == ["ok", "ok"] and len(again.calls) == 1


def test_prompt_hash_covers_the_token_limit(monkeypatch):
    before = prompt_hash()
    monkeypatch.setattr("herbtwin.stages.observe.OBSERVE_MAX_TOKENS", 8192)
    assert prompt_hash() != before
