import csv
import importlib.util
import json
from pathlib import Path

import pytest


def _script():
    spec = importlib.util.spec_from_file_location(
        "eval_advice", Path(__file__).parents[1] / "scripts" / "eval_advice.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def dirs(tmp_path):
    from PIL import Image

    eval_dir, ext = tmp_path / "eval", tmp_path / "ext"
    (eval_dir / "sets").mkdir(parents=True)
    (ext / "s3" / "images").mkdir(parents=True)
    item = {
        "id": "actions_se/7",
        "set": "actions_se",
        "path": "s3/se_diagnosis_herb.jsonl",
        "root": "external",
        "label": {"actions": ["water"], "primary": "water", "model": "m"},
        "licence": "CC BY-SA",
        "tag": "safe-to-train",
        "source": "t",
    }
    (eval_dir / "sets" / "actions_se.jsonl").write_text(json.dumps(item) + "\n")
    (ext / "s3" / "se_diagnosis_herb.jsonl").write_text(
        json.dumps({"id": 7, "title": "t", "body": "b"}) + "\n"
    )
    Image.new("RGB", (20, 20), "green").save(ext / "s3" / "images" / "7_0.jpg")
    with (ext / "s3" / "images" / "manifest.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, ["question_id", "post_type", "fetch_status", "local_file"])
        w.writeheader()
        w.writerow(
            {
                "question_id": "7",
                "post_type": "question",
                "fetch_status": "ok",
                "local_file": "images/7_0.jpg",
            }
        )
    return ["--eval-dir", str(eval_dir), "--external", str(ext)]


PAID = ["--set", "actions_se", "--model", "qwen3:14b", "--with-photos"]
PAID += ["--observe-backend", "tokenfactory", "--observe-model", "zai-org/GLM-5.3-Flash"]


def test_a_paid_observe_run_quotes_and_stops_without_a_yes(dirs, capsys, monkeypatch):
    mod = _script()
    monkeypatch.setattr(mod, "load_settings", lambda *a: pytest.fail("no settings before a yes"))
    assert mod.main(PAID + dirs + ["--dry-run"]) == 0
    assert "photos to observe: 1" in capsys.readouterr().out
    assert mod.main(PAID + dirs) == 2
    assert "--yes-paid" in capsys.readouterr().out


def test_the_quote_prefers_the_measured_rate(dirs, capsys):
    mod = _script()
    runs = Path(dirs[1]) / "runs"
    runs.mkdir()
    row = {"model": "zai-org/GLM-5.3-Flash", "status": "ok", "cost_usd": 0.25, "calls": 1}
    (runs / "old.jsonl").write_text(json.dumps(row) + "\n")
    assert mod.main(PAID + dirs + ["--dry-run"]) == 0
    assert "$0.2500" in capsys.readouterr().out


def test_the_budget_guard_stops_once_spend_passes_the_limit():
    mod = _script()
    guard = mod.BudgetGuard(0.002)
    guard({"observe_cost_usd": 0.001})
    guard({"status": "missing"})
    with pytest.raises(mod.BudgetExceeded):
        guard({"observe_cost_usd": 0.0015})
    assert guard.spent == pytest.approx(0.0025)


def test_a_paid_run_refuses_a_quote_above_the_budget(dirs, capsys):
    mod = _script()
    assert mod.main(PAID + dirs + ["--yes-paid", "--budget", "0.00001"]) == 2
    assert "above the budget" in capsys.readouterr().out


def test_a_paid_run_stops_at_the_budget_and_writes_no_report(dirs, monkeypatch):
    mod = _script()
    monkeypatch.setattr(mod, "load_settings", lambda *a: None)
    monkeypatch.setattr(mod, "get_adapter", lambda *a: object())

    def fake_run(items, *a, progress, **k):
        row = {"id": items[0].id, "status": "ok", "observe_cost_usd": 0.6}
        progress(1, 2, row)
        progress(2, 2, dict(row))
        pytest.fail("the guard should have stopped the run")

    monkeypatch.setattr(mod, "run_advice", fake_run)
    assert mod.main(PAID + dirs + ["--yes-paid", "--budget", "1.0"]) == 3
    assert not (Path(dirs[1]) / "reports").exists()


def test_a_paid_reader_without_photos_is_an_error(dirs):
    mod = _script()
    args = ["--set", "actions_se", "--model", "q", "--observe-backend", "tokenfactory"]
    with pytest.raises(SystemExit):
        mod.main(args + dirs)


def test_shards_split_the_items_without_overlap_or_gaps():
    mod = _script()
    items = list(range(10))
    parts = [mod.take_shard(items, f"{i}/3") for i in range(3)]
    assert sorted(x for p in parts for x in p) == items
    assert mod.take_shard(items, None) == items
    with pytest.raises(ValueError):
        mod.take_shard(items, "3/3")


def test_a_shard_writes_rows_but_no_report(dirs, monkeypatch):
    mod = _script()
    monkeypatch.setattr(mod, "run_advice", lambda items, *a, **k: [])
    args = ["--set", "actions_se", "--model", "q", "--with-photos", "--shard", "0/2"]
    assert mod.main(args + dirs) == 0
    assert not (Path(dirs[1]) / "reports").exists()


def test_shards_get_their_own_run_file_and_bad_specs_are_refused(dirs, monkeypatch):
    mod = _script()
    seen = []
    monkeypatch.setattr(
        mod, "run_advice", lambda items, *a, cache_path, **k: seen.append(cache_path) or []
    )
    args = ["--set", "actions_se", "--model", "q", "--with-photos"]
    assert mod.main(args + dirs + ["--shard", "1/2"]) == 0
    assert seen[0].name.endswith("-shard-1-of-2.jsonl")
    for bad in ("x", "1", "2/2"):
        with pytest.raises(SystemExit):
            mod.main(args + dirs + ["--shard", bad])


def test_few_shot_examples_reach_the_advisor_and_leave_scoring(dirs, monkeypatch):
    mod = _script()
    eval_dir, ext = Path(dirs[1]), Path(dirs[3])
    base = json.loads((eval_dir / "sets" / "actions_se.jsonl").read_text())
    lines = [json.dumps(base)]
    for i in (8, 9):
        label = {
            "actions": ["leave_normal"],
            "primary": "leave_normal",
            "model": "m",
            "stratum": "herb",
        }
        lines.append(json.dumps({**base, "id": f"actions_se/{i}", "label": label}))
    (eval_dir / "sets" / "actions_se.jsonl").write_text("\n".join(lines) + "\n")
    answers = [{"accepted": True, "score": 1, "body": "It is normal."}]
    recs = [
        {"id": i, "title": "t", "body": "b", "score": str(i), "answers": answers} for i in (7, 8, 9)
    ]
    (ext / "s3" / "se_diagnosis_herb.jsonl").write_text(
        "\n".join(json.dumps(r) for r in recs) + "\n"
    )
    seen = {}

    def fake_run(items, *a, examples, cache_path, **k):
        seen.update(ids=[i.id for i in items], examples=examples, path=cache_path)
        return []

    monkeypatch.setattr(mod, "run_advice", fake_run)
    assert mod.main(["--set", "actions_se", "--model", "q", "--few-shot"] + dirs) == 0
    # 9 has the higher score, then 8; 7 has a photo and is never an example
    assert [q for q, _ in seen["examples"]] == ["t\n\nb", "t\n\nb"]
    assert seen["ids"] == ["actions_se/7"] and "fewshot2" in seen["path"].name
    text = next((eval_dir / "reports").glob("*.summary.json")).read_text()
    # no scored rows, so every metric is empty: null, never a bare NaN (19 Oct)
    report = json.loads(text, parse_constant=lambda c: pytest.fail(f"{c} in the summary"))
    assert report["few_shot_ids"] == ["actions_se/9", "actions_se/8"]


BRAIN = ["--set", "actions_se", "--model", "nvidia/nemotron-3-super-120b-a12b"]
BRAIN += ["--backend", "tokenfactory"]


def test_a_paid_advisor_quotes_the_worst_case_and_waits_for_a_yes(dirs, capsys, monkeypatch):
    mod = _script()
    monkeypatch.setattr(mod, "load_settings", lambda *a: pytest.fail("no settings before a yes"))
    assert mod.main(BRAIN + dirs + ["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "paid advise on tokenfactory" in out and "1 questions" in out and "quote $" in out
    assert mod.main(BRAIN + dirs) == 2
    assert mod.main(BRAIN + dirs + ["--yes-paid", "--budget", "0.0000001"]) == 2


def test_the_advisor_quote_counts_the_prompt_and_the_full_output():
    mod = _script()
    model = "nvidia/nemotron-3-super-120b-a12b"
    pin, pout = mod.TokenFactoryAdapter.PRICING[model]
    q = mod.advisor_quote(model, ["x" * 400])
    tokens_in = (len(mod.advise_stage.SYSTEM) + 400) / 4
    assert q == pytest.approx(
        2 * (tokens_in * pin + mod.advise_stage.ADVISE_MAX_TOKENS * pout) / 1e6
    )
    assert mod.advisor_quote("no/such", ["x"]) is None


def test_the_budget_counts_advice_cost_too():
    mod = _script()
    guard = mod.BudgetGuard(0.002)
    guard({"advise_cost_usd": 0.0015})
    with pytest.raises(mod.BudgetExceeded):
        guard({"observe_cost_usd": 0.0004, "advise_cost_usd": 0.0002})


def test_a_paid_advisor_run_passes_workers_and_backend(dirs, monkeypatch):
    mod = _script()
    monkeypatch.setattr(mod, "load_settings", lambda *a: None)
    monkeypatch.setattr(mod, "get_adapter", lambda *a: object())
    seen = {}

    def fake_run(items, questions, adapter, **k):
        seen.update(k)
        return [{"id": items[0].id, "status": "error", "advise_cost_usd": 0.001}]

    monkeypatch.setattr(mod, "run_advice", fake_run)
    assert mod.main(BRAIN + dirs + ["--yes-paid", "--workers", "8"]) == 0
    assert seen["workers"] == 8 and seen["backend"] == "tokenfactory"
    assert seen["model"] == "nvidia/nemotron-3-super-120b-a12b"
    report = json.loads(next((Path(dirs[1]) / "reports").glob("*.summary.json")).read_text())
    assert report["advise_cost_usd"] == 0.001 and report["backend"] == "tokenfactory"


def test_the_limit_samples_after_the_photo_filter(dirs, monkeypatch):
    mod = _script()
    sets = Path(dirs[1]) / "sets" / "actions_se.jsonl"
    base = json.loads(sets.read_text())
    rows = [{**base, "id": f"actions_se/{i}"} for i in (1, 2)] + [base]  # only 7 has a photo
    sets.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    seen = {}
    monkeypatch.setattr(
        mod, "run_advice", lambda items, *a, **k: seen.update(ids=[i.id for i in items]) or []
    )
    args = ["--set", "actions_se", "--model", "q", "--only-with-photos", "--limit", "1"]
    assert mod.main(args + dirs) == 0
    assert seen["ids"] == ["actions_se/7"]


def test_holding_out_examples_drops_them_without_showing_them(dirs, monkeypatch):
    mod = _script()
    eval_dir, ext = Path(dirs[1]), Path(dirs[3])
    base = json.loads((eval_dir / "sets" / "actions_se.jsonl").read_text())
    label = {"actions": ["water"], "primary": "water", "model": "m", "stratum": "herb"}
    rows = [base, {**base, "id": "actions_se/8", "label": label}]
    (eval_dir / "sets" / "actions_se.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n"
    )
    answers = [{"accepted": True, "score": 1, "body": "Water it."}]
    recs = [{"id": i, "title": "t", "body": "b", "score": "1", "answers": answers} for i in (7, 8)]
    (ext / "s3" / "se_diagnosis_herb.jsonl").write_text(
        "\n".join(json.dumps(r) for r in recs) + "\n"
    )
    seen = {}

    def fake_run(items, *a, examples, cache_path, **k):
        seen.update(ids=[i.id for i in items], examples=examples, path=cache_path)
        return []

    monkeypatch.setattr(mod, "run_advice", fake_run)
    assert mod.main(["--set", "actions_se", "--model", "q", "--hold-out-examples"] + dirs) == 0
    assert seen["ids"] == ["actions_se/7"] and seen["examples"] is None
    assert "fewshot" not in seen["path"].name


def test_the_advisor_quote_prefers_a_measured_rate_with_a_margin(dirs, capsys):
    mod = _script()
    runs = Path(dirs[1]) / "runs"
    runs.mkdir()
    row = {"model": "nvidia/nemotron-3-super-120b-a12b", "advise_calls": 1, "advise_cost_usd": 0.01}
    (runs / "old.jsonl").write_text(json.dumps(row) + "\n")
    assert mod.main(BRAIN + dirs + ["--dry-run"]) == 0
    assert "quote $0.0150" in capsys.readouterr().out


def test_vllm_no_think_turns_thinking_off_in_every_request(dirs, monkeypatch):
    # 19 Oct: the self-hosted Nemotron Nano run must send what Token Factory gets for a
    # no-thinking model, not lean on the vLLM server's default
    mod = _script()
    seen = []
    monkeypatch.setattr(
        mod,
        "run_advice",
        lambda items, q, adapter, *a, model, **k: seen.append((adapter, model)) or [],
    )
    args = ["--set", "actions_se", "--model", "nvidia/nano", "--vllm-no-think", "--shard", "0/1"]
    assert mod.main(args + dirs) == 0
    adapter, model = seen[0]
    assert adapter.extra_body == {"chat_template_kwargs": {"enable_thinking": False}}
    assert model == "nvidia/nano:vllm-no-think"
    with pytest.raises(SystemExit):
        mod.main(["--set", "actions_se", "--model", "q", "--think", "--vllm-no-think"] + dirs)
