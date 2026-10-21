import json

import pytest
from pydantic import ValidationError

from herbtwin.evals.items import EvalItem, load_set, resolve, spaced_sample, write_set


def _item(i: str, path: str = "s4/a.jpg", **kw) -> dict:
    return {
        "id": f"droop_soybean/{i}",
        "set": "droop_soybean",
        "path": path,
        "root": "external",
        "label": {"droop": 1, "raw": 2},
        "cluster": "3-106",
        "licence": "CC BY 4.0",
        "tag": "safe-to-train",
        "source": "Zenodo 8256382",
        **kw,
    }


def _write(tmp_path, rows):
    p = tmp_path / "s.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return p


def test_load_set_reads_rows(tmp_path):
    items = load_set(_write(tmp_path, [_item("a"), _item("b")]))
    assert [i.id for i in items] == ["droop_soybean/a", "droop_soybean/b"]
    assert items[0].label == {"droop": 1, "raw": 2}


def test_load_set_rejects_duplicate_ids(tmp_path):
    with pytest.raises(ValueError, match="duplicate"):
        load_set(_write(tmp_path, [_item("a"), _item("a")]))


def test_unknown_tag_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="line 1 is not a valid item"):
        load_set(_write(tmp_path, [_item("a", tag="maybe")]))
    with pytest.raises(ValidationError):
        EvalItem(**_item("a", tag="maybe"))


def test_load_set_names_the_bad_line(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text(json.dumps(_item("a")) + "\n{not json\n")
    with pytest.raises(ValueError, match="line 2"):
        load_set(p)


def test_resolve_finds_existing_and_returns_none_for_missing(tmp_path):
    (tmp_path / "ext" / "s4").mkdir(parents=True)
    (tmp_path / "ext" / "s4" / "a.jpg").write_bytes(b"x")
    roots = {"external": tmp_path / "ext"}
    assert resolve(EvalItem(**_item("a")), roots) == tmp_path / "ext" / "s4" / "a.jpg"
    assert resolve(EvalItem(**_item("b", path="s4/b.jpg")), roots) is None


def test_resolve_refuses_paths_that_escape_the_root(tmp_path):
    (tmp_path / "ext").mkdir()
    (tmp_path / "secret.txt").write_text("x")
    item = EvalItem(**_item("a", path="../secret.txt"))
    with pytest.raises(ValueError, match="outside"):
        resolve(item, {"external": tmp_path / "ext"})


def test_resolve_refuses_absolute_paths(tmp_path):
    (tmp_path / "ext").mkdir()
    item = EvalItem(**_item("a", path=str(tmp_path / "elsewhere.jpg")))
    with pytest.raises(ValueError, match="outside"):
        resolve(item, {"external": tmp_path / "ext"})


def test_write_set_refuses_duplicate_ids(tmp_path):
    with pytest.raises(ValueError, match="duplicate"):
        write_set(tmp_path / "x.jsonl", [EvalItem(**_item("a")), EvalItem(**_item("a"))])


def test_resolve_rejects_an_unknown_root(tmp_path):
    with pytest.raises(ValueError, match="root"):
        resolve(EvalItem(**_item("a", root="nowhere")), {"external": tmp_path})


def test_write_set_is_sorted_and_round_trips(tmp_path):
    items = [EvalItem(**_item("b")), EvalItem(**_item("a"))]
    p = tmp_path / "out.jsonl"
    write_set(p, items)
    assert [i.id for i in load_set(p)] == ["droop_soybean/a", "droop_soybean/b"]
    first = p.read_bytes()
    write_set(p, list(reversed(items)))
    assert p.read_bytes() == first


def test_spaced_sample_reaches_every_part_of_the_set():
    items = [EvalItem(**_item(f"{c}{k}")) for c in "ab" for k in range(10)]
    picked = spaced_sample(items, 4)
    assert len(picked) == 4
    assert {i.id.split("/")[1][0] for i in picked} == {"a", "b"}
    assert spaced_sample(items, 50) == items


def test_write_set_replaces_the_file_atomically(tmp_path, monkeypatch):
    p = tmp_path / "s.jsonl"
    write_set(p, [EvalItem(**_item("a"))])
    before = p.read_bytes()

    def boom(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr("herbtwin.evals.items.os.replace", boom)
    with pytest.raises(KeyboardInterrupt):
        write_set(p, [EvalItem(**_item("b"))])
    assert p.read_bytes() == before  # the old set survives an interrupted save
