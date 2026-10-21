import importlib.util
import json
from pathlib import Path

import pytest

from herbtwin.adapters.base import CallRecord, ModelAdapter


def _script():
    spec = importlib.util.spec_from_file_location(
        "judge_pairs", Path(__file__).parents[1] / "scripts" / "judge_pairs.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PricedJudge(ModelAdapter):
    """Always prefers A; each call records a fixed cost, as Token Factory's adapter does."""

    name = "priced"
    model = "nvidia/Nemotron-3-Ultra-550b-a55b"

    def __init__(self, cost: float) -> None:
        self.cost = cost
        self.calls = 0

    def complete(self, system, user, *, max_tokens=1024):
        self.calls += 1
        self._record(CallRecord(self.model, "judge", user, "", 1, 100, 10, self.cost, False))
        return '{"better": "A", "reason": "r"}'

    def complete_json(self, system, user, schema, *, max_tokens=1024, temperature=0.0):
        raise NotImplementedError

    def complete_with_image(self, system, user, image, mime, schema=None, *, max_tokens=1024):
        raise NotImplementedError


@pytest.fixture
def dirs(tmp_path):
    eval_dir, ext = tmp_path / "eval", tmp_path / "ext"
    (eval_dir / "sets").mkdir(parents=True)
    (ext / "s3").mkdir(parents=True)
    items, questions = [], []
    for q in range(1, 5):
        items.append(
            {
                "id": f"pairs_se/{q}",
                "set": "pairs_se",
                "path": "s3/se_diagnosis_herb.jsonl",
                "root": "external",
                "label": {
                    "question_id": q,
                    "preferred_id": 10 * q,
                    "other_id": 10 * q + 1,
                    "gap": 2,
                    "accepted": True,
                    "subsets": ["herb"],
                },
                "licence": "CC BY-SA",
                "tag": "safe-to-train",
                "source": "t",
            }
        )
        questions.append(
            {
                "id": q,
                "title": "T",
                "body": "B",
                "answers": [
                    {"id": 10 * q, "body": "preferred", "score": 3},
                    {"id": 10 * q + 1, "body": "other", "score": 0},
                ],
            }
        )
    (eval_dir / "sets" / "pairs_se.jsonl").write_text("".join(json.dumps(i) + "\n" for i in items))
    (ext / "s3" / "se_diagnosis_herb.jsonl").write_text(
        "".join(json.dumps(q) + "\n" for q in questions)
    )
    return ["--eval-dir", str(eval_dir), "--external", str(ext)], eval_dir


def test_a_token_factory_judge_needs_yes_paid_and_makes_no_call_without_it(
    dirs, monkeypatch, capsys
):
    mod, (args, _) = _script(), dirs
    judge = PricedJudge(0.001)
    monkeypatch.setattr(mod, "make_judge", lambda spec, think=False: judge)
    code = mod.main(["--judge", "tokenfactory:nvidia/Nemotron-3-Ultra-550b-a55b", *args])
    assert code == 2
    assert judge.calls == 0
    assert "quote" in capsys.readouterr().out


def test_a_paid_judge_stops_at_the_budget_and_writes_no_report(dirs, monkeypatch):
    mod, (args, eval_dir) = _script(), dirs
    judge = PricedJudge(0.01)
    monkeypatch.setattr(mod, "make_judge", lambda spec, think=False: judge)
    code = mod.main(
        [
            "--judge",
            "tokenfactory:nvidia/Nemotron-3-Ultra-550b-a55b",
            "--yes-paid",
            "--budget",
            "0.025",
            "--run-id",
            "r",
            *args,
        ]
    )
    assert code == 3
    # three calls take the spend past $0.025; every later call is refused unpaid
    assert judge.calls == 3
    assert not (eval_dir / "reports" / "r.md").exists()
    cached = (eval_dir / "runs" / "r.jsonl").read_text().splitlines()
    assert len(cached) == 3  # the paid verdicts are kept for a resume


def test_a_paid_judge_within_budget_writes_its_report(dirs, monkeypatch):
    mod, (args, eval_dir) = _script(), dirs
    judge = PricedJudge(0.001)
    monkeypatch.setattr(mod, "make_judge", lambda spec, think=False: judge)
    code = mod.main(
        [
            "--judge",
            "tokenfactory:nvidia/Nemotron-3-Ultra-550b-a55b",
            "--yes-paid",
            "--run-id",
            "r",
            *args,
        ]
    )
    assert code == 0
    assert judge.calls == 8
    summary = json.loads((eval_dir / "reports" / "r.summary.json").read_text())
    assert summary["spent_this_run_usd"] == pytest.approx(0.008)


def test_a_judge_model_with_no_price_does_not_start(dirs, monkeypatch, capsys):
    mod, (args, _) = _script(), dirs
    judge = PricedJudge(0.001)
    monkeypatch.setattr(mod, "make_judge", lambda spec, think=False: judge)
    assert mod.main(["--judge", "tokenfactory:unpriced/model", "--yes-paid", *args]) == 2
    assert judge.calls == 0
