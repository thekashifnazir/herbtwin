import json

from herbtwin.evals.advice_eval import EMPTY_CONTEXT
from herbtwin.evals.finetune_data import held_out_ids, training_rows
from herbtwin.evals.items import EvalItem
from herbtwin.stages import advise as advise_stage


def _item(n: int, primary: str = "water", tag: str = "safe-to-train") -> EvalItem:
    return EvalItem(
        id=f"actions_se/{n}",
        set="actions_se",
        path="s3/x.jsonl",
        root="external",
        label={"actions": [primary], "primary": primary},
        licence="CC BY-SA",
        tag=tag,
        source="https://example.org",
    )


def _row(n: int, primary: str = "water", status: str = "ok") -> dict:
    advice = {
        "actions": [primary],
        "primary": primary,
        "answer": "Water it well.",
        "ask": "",
        "confidence": "high",
    }
    return {"id": f"actions_se/{n}", "status": status, "advice": advice}


ITEMS = [_item(n) for n in range(10)]
QUESTIONS = {i.id: f"question {i.id}" for i in ITEMS}


def test_held_out_is_the_eval_sample_plus_every_mirage_id():
    held = held_out_ids(ITEMS, limit=5, mirage_ids={"actions_mirage/1"})
    # the same spaced sample `eval_advice.py --limit 5` scores: every second item
    assert held == {f"actions_se/{n}" for n in (0, 2, 4, 6, 8)} | {"actions_mirage/1"}


def test_only_expert_matched_rows_outside_the_held_out_set_become_examples():
    rows = [_row(n) for n in range(10)]
    rows[1] = _row(1, primary="prune")  # disagrees with the expert
    rows[3] = _row(3, status="failed")
    out = training_rows(ITEMS, QUESTIONS, rows, held_out=held_out_ids(ITEMS, limit=5))
    assert [r["id"] for r in out] == ["actions_se/5", "actions_se/7", "actions_se/9"]


def test_an_example_is_the_exact_advisor_prompt_and_the_teacher_json():
    out = training_rows(ITEMS, QUESTIONS, [_row(5)], held_out=set())
    system, user, assistant = out[0]["messages"]
    assert system == {"role": "system", "content": advise_stage.SYSTEM}
    want = advise_stage._user("question actions_se/5", None, None, EMPTY_CONTEXT)
    assert user == {"role": "user", "content": want}
    assert json.loads(assistant["content"]) == _row(5)["advice"]
    assert assistant["role"] == "assistant"


def test_items_not_tagged_safe_to_train_never_become_examples():
    items = [_item(0, tag="test-only")]
    out = training_rows(items, {"actions_se/0": "q"}, [_row(0)], held_out=set())
    assert out == []


def test_a_held_out_id_never_leaks_even_when_its_row_matches():
    out = training_rows(ITEMS, QUESTIONS, [_row(n) for n in range(10)], held_out={"actions_se/4"})
    assert "actions_se/4" not in {r["id"] for r in out}
