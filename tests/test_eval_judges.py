import pytest

from herbtwin.adapters.base import AdapterError
from herbtwin.adapters.mock import MockAdapter
from herbtwin.evals.items import EvalItem
from herbtwin.evals.judges import (
    naive_baselines,
    parse_verdict,
    run_pairs,
    score_order,
    summarise_pairs,
)


def test_parse_verdict_accepts_common_shapes():
    assert parse_verdict('{"better": "A", "reason": "x"}') == "A"
    assert parse_verdict('Sure: {"better": "b."}') == "B"
    assert parse_verdict('{"better": "Tie"}') == "tie"
    assert parse_verdict('<think>maybe {A} or {B}</think>{"better": "B"}') == "B"
    with pytest.raises(ValueError):
        parse_verdict('{"better": "both"}')


def test_score_order_follows_where_the_preferred_answer_sat():
    assert score_order("A", "pref_first") == 1 and score_order("A", "pref_second") == 0
    assert score_order("B", "pref_second") == 1 and score_order("tie", "pref_first") == 0.5


def _items(n):
    return [
        EvalItem(
            id=f"pairs_se/{q}",
            set="pairs_se",
            path="s3/x.jsonl",
            root="external",
            label={
                "question_id": q,
                "preferred_id": 10 * q,
                "other_id": 10 * q + 1,
                "gap": 3 if q % 2 else 0,
                "accepted": True,
                "subsets": ["diagnosis"] if q % 2 else ["herb"],
            },
            licence="CC BY-SA",
            tag="safe-to-train",
            source="t",
        )
        for q in range(1, n + 1)
    ]


def _questions(n):
    return {
        q: {
            "title": "T",
            "body": "B",
            "answers": [
                {"id": 10 * q, "body": "preferred answer, longer", "score": 3},
                {"id": 10 * q + 1, "body": "other", "score": 0},
            ],
        }
        for q in range(1, n + 1)
    }


def test_a_judge_that_always_says_a_is_at_chance_and_never_consistent(tmp_path):
    items = _items(4)
    rows = run_pairs(
        items,
        _questions(4),
        MockAdapter(['{"better": "A"}'] * 8),
        judge="m",
        cache_path=tmp_path / "r.jsonl",
    )
    s = summarise_pairs(items, rows, {})
    assert s["metrics"]["accuracy"]["value"] == pytest.approx(0.5)
    assert s["position_consistency"] == 0.0
    assert s["first_position_rate"] == 1.0


def test_a_perfect_judge_is_consistent_and_cached(tmp_path):
    items = _items(2)
    replies = ['{"better": "A"}', '{"better": "B"}'] * 2  # pref_first then pref_second
    run_pairs(
        items, _questions(2), MockAdapter(replies), judge="m", cache_path=tmp_path / "r.jsonl"
    )
    again = MockAdapter([])
    rows = run_pairs(items, _questions(2), again, judge="m", cache_path=tmp_path / "r.jsonl")
    s = summarise_pairs(items, rows, {})
    assert again.calls == [] and s["position_consistency"] == 1.0
    assert s["metrics"]["accuracy"]["value"] == pytest.approx(1.0)
    assert s["metrics"]["accuracy_diagnosis"]["n"] == 2


def test_unparseable_and_failed_calls_are_counted_not_scored(tmp_path):
    class Flaky(MockAdapter):
        def complete(self, system, user, *, max_tokens=1024):
            if "Answer A ===\nother" in user:
                raise AdapterError("down")
            return "no json"

    rows = run_pairs(_items(1), _questions(1), Flaky(), judge="m", cache_path=tmp_path / "r.jsonl")
    assert sorted(r["status"] for r in rows) == ["error", "failed"]
    s = summarise_pairs(_items(1), rows, {})
    assert s["n_ok"] == 0 and s["n_failed"] == 1 and s["n_error"] == 1


def test_parallel_workers_give_the_same_rows(tmp_path):
    items = _items(3)
    rows = run_pairs(
        items,
        _questions(3),
        MockAdapter(['{"better": "tie"}'] * 6),
        judge="m",
        cache_path=tmp_path / "r.jsonl",
        workers=3,
    )
    assert len(rows) == 6 and all(r["score"] == 0.5 for r in rows)


def test_naive_baselines():
    b = naive_baselines(_items(2), _questions(2))
    assert b == {"preferred_is_longer": 1.0, "preferred_is_earlier": 1.0}


class ReadsTheSlots(MockAdapter):
    """Picks whichever slot holds the preferred text, so a swap of slots would show."""

    def complete(self, system, user, *, max_tokens=1024):
        self.calls.append(user)
        a_part = user.split("=== Answer A ===")[1].split("=== Answer B ===")[0]
        return '{"better": "A"}' if "preferred answer" in a_part else '{"better": "B"}'


def test_the_preferred_text_lands_in_the_stated_slot(tmp_path):
    items = _items(3)
    adapter = ReadsTheSlots()
    rows = run_pairs(items, _questions(3), adapter, judge="m", cache_path=tmp_path / "r.jsonl")
    s = summarise_pairs(items, rows, {})
    assert s["metrics"]["accuracy"]["value"] == pytest.approx(1.0)
    assert s["position_consistency"] == 1.0
    first = next(u for u, r in zip(adapter.calls, rows, strict=True) if r["order"] == "pref_first")
    assert first.index("preferred answer") < first.index("=== Answer B ===")


def test_unparseable_rows_pull_the_conservative_accuracy_to_half(tmp_path):
    items = _items(1)
    rows = run_pairs(
        items,
        _questions(1),
        MockAdapter(['{"better": "A"}', "garbage"]),
        judge="m",
        cache_path=tmp_path / "r.jsonl",
    )
    s = summarise_pairs(items, rows, {})
    assert s["metrics"]["accuracy"]["value"] == pytest.approx(1.0)
    assert s["metrics"]["accuracy_counting_unparseable_as_half"]["value"] == pytest.approx(0.75)


def test_first_position_rate_is_nan_without_decisive_verdicts(tmp_path):
    import math

    items = _items(1)
    rows = run_pairs(
        items,
        _questions(1),
        MockAdapter(['{"better": "tie"}'] * 2),
        judge="m",
        cache_path=tmp_path / "r.jsonl",
    )
    assert math.isnan(summarise_pairs(items, rows, {})["first_position_rate"])


class PicksTheLonger(MockAdapter):
    """A length-tracking judge: right whenever the preferred answer is the longer one."""

    def complete(self, system, user, *, max_tokens=1024):
        a = user.split("=== Answer A ===")[1].split("=== Answer B ===")[0]
        b = user.split("=== Answer B ===")[1].split("Reply with JSON")[0]
        return '{"better": "A"}' if len(a) > len(b) else '{"better": "B"}'


def test_confound_free_subsets_catch_a_length_tracking_judge(tmp_path):
    items = _items(3)
    qs = _questions(3)
    # pair 2: the preferred answer was posted later and is the shorter one
    qs[2]["answers"] = [
        {"id": 21, "body": "a much longer other answer than that", "score": 0},
        {"id": 30, "body": "brief", "score": 3},
    ]
    items[1] = items[1].model_copy(
        update={"label": {**items[1].label, "preferred_id": 30, "other_id": 21}}
    )
    rows = run_pairs(items, qs, PicksTheLonger(), judge="m", cache_path=tmp_path / "r.jsonl")
    s = summarise_pairs(items, rows, {}, questions=qs)
    assert s["metrics"]["accuracy"]["value"] == pytest.approx(4 / 6)
    for name in ("accuracy_preferred_is_later", "accuracy_preferred_is_shorter"):
        m = s["metrics"][name]
        assert (m["value"], m["n"], m["n_pairs"]) == (0.0, 2, 1)
    assert "accuracy_preferred_is_later" not in summarise_pairs(items, rows, {})["metrics"]


def test_local_judges_think_only_when_asked():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "judge_pairs", Path(__file__).parents[1] / "scripts" / "judge_pairs.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.make_judge("ollama:qwen3:14b").extra_body == {"reasoning_effort": "none"}
    assert mod.make_judge("ollama:qwen3:14b", think=True).extra_body is None
