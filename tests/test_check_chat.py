import importlib.util
import json
import sys
from pathlib import Path

from herbtwin.adapters.mock import MockAdapter

_spec = importlib.util.spec_from_file_location(
    "check_chat", Path(__file__).parents[1] / "scripts" / "check_chat.py"
)
cc = importlib.util.module_from_spec(_spec)
sys.modules["check_chat"] = cc  # dataclasses look their module up here
_spec.loader.exec_module(cc)


def _tool(name, **args):
    return json.dumps({"tool_calls": [{"name": name, "arguments": args}]})


def test_ten_cases_five_frost_five_wet():
    assert len(cc.CASES) == 10
    assert sorted({c.kind for c in cc.CASES}) == ["frost_inside", "wet_water"]


def test_records_are_synthetic_and_outdoor(tmp_path):
    for c in cc.CASES:
        rec = cc.build_record(c, cache_dir=tmp_path)
        assert rec.location is None and rec.observation.setting == "outdoor"
        assert (rec.told is not None and rec.told.soil_feel == "wet") == (c.kind == "wet_water")


def test_the_plant_model_gives_the_wanted_verdict_for_every_case(tmp_path):
    from herbtwin.scenarios import run_scenario

    for c in cc.CASES:
        action, want = c.expect
        assert run_scenario(cc.build_record(c, cache_dir=tmp_path), action).vs_leaving_it == want


def test_a_case_passes_only_on_the_right_tool_and_verdict(tmp_path):
    frost = next(c for c in cc.CASES if c.kind == "frost_inside")
    good = MockAdapter([_tool("run_scenario", action="move_inside"), "Bring it in."])
    assert cc.verdict([(frost, cc.run_case(good, frost, cache_dir=tmp_path))])[0] is True
    lazy = MockAdapter(["Bring it in."])  # no tool call: a guess
    ok, problems = cc.verdict([(frost, cc.run_case(lazy, frost, cache_dir=tmp_path))])
    assert ok is False and "no run_scenario call" in problems[0]
    wrong = MockAdapter([_tool("run_scenario", action="water"), "Water it."])
    ok, problems = cc.verdict([(frost, cc.run_case(wrong, frost, cache_dir=tmp_path))])
    assert ok is False and "wanted move_inside better" in problems[0]
