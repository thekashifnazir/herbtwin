import importlib.util
import json
import sys
from pathlib import Path

from herbtwin.adapters.mock import MockAdapter

_spec = importlib.util.spec_from_file_location(
    "check_refine", Path(__file__).parents[1] / "scripts" / "check_refine.py"
)
cr = importlib.util.module_from_spec(_spec)
sys.modules["check_refine"] = cr  # dataclasses look their module up here
_spec.loader.exec_module(cr)


def test_twelve_cases_six_plants_dry_and_wet():
    assert len(cr.CASES) == 12
    assert {c.feel for c in cr.CASES} == {"dry", "wet"}
    assert len({c.species for c in cr.CASES}) == 6


def test_readings_have_no_location_and_outdoor_ones_have_weather(tmp_path):
    for c in cr.CASES:
        r = cr.build_reading(c, cache_dir=tmp_path)
        assert r.rec.location is None and r.rec.observation.water_stress == 2
        assert (r.rec.environment is not None) == (c.setting == "outdoor")


def test_verdict_rules():
    wet = next(c for c in cr.CASES if c.feel == "wet")
    dry = next(c for c in cr.CASES if c.feel == "dry")
    ok, _ = cr.verdict([(wet, "dont_water"), (dry, "water")])
    assert ok
    ok, why = cr.verdict([(wet, "water"), (dry, "water")])
    assert not ok and "wet" in why[0]
    ok, why = cr.verdict([(wet, "leave_normal"), (dry, "leave_normal")])
    assert not ok and "dry" in why[0]


def test_one_case_runs_offline_with_the_told_block(tmp_path):
    adv = json.dumps(
        {
            "actions": ["dont_water"],
            "primary": "dont_water",
            "answer": "Wet below. Hold off.",
            "ask": "",
            "confidence": "high",
        }
    )
    deps = cr.offline_deps(tmp_path, MockAdapter([adv] * 3))
    case = next(c for c in cr.CASES if c.feel == "wet" and c.setting == "outdoor")
    assert cr.run_case(deps, case) == "dont_water"
    prompt = deps.advise_adapter.calls[0]["prompt"]
    assert "soil 2 cm down: wet" in prompt and "PLANT MODEL" in prompt
