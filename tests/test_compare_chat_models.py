import importlib.util
import json
import sys
from pathlib import Path

from herbtwin.chat import ChatReply

_dir = Path(__file__).parents[1] / "scripts"
_spec = importlib.util.spec_from_file_location(
    "compare_chat_models", _dir / "compare_chat_models.py"
)
ccm = importlib.util.module_from_spec(_spec)
sys.modules["compare_chat_models"] = ccm  # dataclasses look their module up here
_spec.loader.exec_module(ccm)
HARD = {h.name: h for h in ccm.HARD}


def _said(text, *tools, grounded=True):
    return ChatReply(text, [{"name": n, "arguments": a} for n, a in tools], [], grounded)


def test_thanks_fails_on_a_plant_model_run():
    run = ("run_scenario", {"action": "water"})
    assert ccm.score_hard(HARD["thanks_cold"], _said("Watering is the same.", run))[0] is False
    assert ccm.score_hard(HARD["thanks_cold"], _said("You're welcome!"))[0] is True


def test_us_wording_counts_in_prose_not_in_citations():
    search = ("search_web", {"query": "basil downy mildew"})
    cited = _said("Remove infected plants. [extension.umn.edu/basil]", search)
    assert ccm.score_hard(HARD["prevent_next_year"], cited)[0] is True
    said = _said("Most extension advice says to remove them.", search)
    assert ccm.score_hard(HARD["eat_leaves"], said) == (False, "US wording")


def test_eat_leaves_needs_a_grounded_search():
    search = ("search_web", {"query": "eat basil"})
    assert ccm.score_hard(HARD["eat_leaves"], _said("Yes.", search, grounded=False))[0] is False
    assert ccm.score_hard(HARD["eat_leaves"], _said("Yes.", search))[0] is True


def test_basil_records_carry_the_downy_mildew_answer(tmp_path):
    rec = ccm.hard_record(HARD["eat_leaves"], cache_dir=tmp_path)
    assert rec.observation.species[0].common_name == "basil"
    assert "downy mildew" in rec.answer.headline
    assert (
        ccm.hard_record(HARD["water_today"], cache_dir=tmp_path).observation.species[0].common_name
        == "rosemary"
    )


def _row(case, kind, text, tools, ok=False):
    # as main() saves it: tools keep name and arguments, never the result
    return {
        "case": case,
        "kind": kind,
        "text": text,
        "tools": tools,
        "grounded": True,
        "ok": ok,
        "note": "",
        "wall_s": 1.0,
        "call_ms": [400, 300],
        "retried": False,
        "unsure": False,
        "leak": False,
        "error": None,
        "no_answer": False,
        "in_tok": 10,
        "out_tok": 2,
        "cost": 0.001,
    }


def test_rescore_scores_saved_replies_again_and_writes_the_table(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ccm, "RUNS", tmp_path)
    water = [{"name": "run_scenario", "arguments": {"action": "water"}}]
    saved = {
        "spent_usd": 0.003,
        "results": {
            "m": [
                _row("check-chat-sage-wet_water", "base", "Worse.", water, ok=True),
                _row("hard-water_today", "hard", "About the same.", water),
                _row("hard-thanks_cold", "hard", "Same. [extension.umn.edu/x]", water, ok=True),
            ]
        },
    }
    src = tmp_path / "saved.json"
    src.write_text(json.dumps(saved))
    assert ccm.rescore(src) == 0
    rows = json.loads((tmp_path / "compare_chat.json").read_text())["results"]["m"]
    assert [r["ok"] for r in rows] == [True, True, False]  # base kept; hard scored again
    assert rows[2]["us_words"] is False  # a cited extension page is not the reply's wording
    out = capsys.readouterr().out
    assert "m | 1/1 | 1/2 |" in out and "0.70/0.70" in out
