import importlib.util
import json
from pathlib import Path


def _script():
    spec = importlib.util.spec_from_file_location(
        "compare_advice", Path(__file__).parents[1] / "scripts" / "compare_advice.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _row(i, primary, key="k"):
    adv = {"actions": [primary], "primary": primary, "answer": "a", "ask": ""}
    return {"key": key, "id": f"actions_se/{i}", "status": "ok", "advice": adv}


def test_the_last_row_per_question_wins(tmp_path):
    f = tmp_path / "r.jsonl"
    lines = [_row(1, "water", "old"), _row(2, "water"), _row(1, "prune", "new")]
    f.write_text("\n".join(json.dumps(r) for r in lines) + "\nnot json\n")
    rows = {r["id"]: r for r in _script().latest_rows(f)}
    assert len(rows) == 2 and rows["actions_se/1"]["key"] == "new"


def test_compare_writes_a_paired_report(tmp_path):
    item = {
        "id": "actions_se/1",
        "set": "actions_se",
        "path": "p",
        "root": "external",
        "label": {"actions": ["water"], "primary": "water", "model": "m"},
        "licence": "l",
        "tag": "safe-to-train",
        "source": "s",
    }
    (tmp_path / "sets").mkdir()
    (tmp_path / "sets" / "actions_se.jsonl").write_text(json.dumps(item) + "\n")
    a, b, out = tmp_path / "a.jsonl", tmp_path / "b.jsonl", tmp_path / "o.json"
    a.write_text(json.dumps(_row(1, "ask_first")) + "\n")
    b.write_text(json.dumps(_row(1, "water")) + "\n")
    argv = ["--set", "actions_se", "--a", str(a), "--b", str(b), "--labels", "x,y"]
    assert _script().main(argv + ["--out", str(out), "--eval-dir", str(tmp_path)]) == 0
    got = json.loads(out.read_text())
    assert got["n_paired"] == 1 and got["metrics"]["primary_match"]["diff"] == 1.0
    assert got["runs"] == {"x": "a.jsonl", "y": "b.jsonl"}
    # 19 Oct: the same main action question by question, for two serving paths of one model
    agree = got["primary_agreement"]
    assert agree["n"] == 1 and agree["agree"] == 0
    assert agree["differ"] == [{"id": "actions_se/1", "x": "ask_first", "y": "water"}]


def test_a_run_file_mixing_model_settings_is_refused(tmp_path):
    import pytest

    (tmp_path / "sets").mkdir()
    (tmp_path / "sets" / "actions_se.jsonl").write_text("")
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    a.write_text(json.dumps(_row(1, "water")) + "\n")
    mixed = [
        {**_row(1, "water"), "model": "m:think"},
        {**_row(2, "water"), "model": "m:vllm-no-think"},
    ]
    b.write_text("\n".join(json.dumps(r) for r in mixed) + "\n")
    argv = ["--set", "actions_se", "--a", str(a), "--b", str(b), "--eval-dir", str(tmp_path)]
    with pytest.raises(SystemExit):
        _script().main(argv)
