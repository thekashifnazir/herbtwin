from datetime import UTC, date, datetime, timedelta

import pytest

from herbtwin.consequences import consequence_for
from herbtwin.plant_model import compare_actions
from herbtwin.scenarios import INDOORS, NO_MODEL, SCENARIOS, run_scenario
from herbtwin.schemas import (
    AnalysisRecord,
    DailyWeather,
    Environment,
    Observation,
    SpeciesCandidate,
    Told,
)
from herbtwin.stages.research import research
from herbtwin.stages.twin import simulate

ON = date(2026, 10, 6)


def _env(frost_night: int | None = None, rain: float = 0.5) -> Environment:
    """A synthetic October fortnight and week ahead: no real place."""
    days = [
        DailyWeather(
            date=ON + timedelta(days=i),
            t_min=-6.0 if i == frost_night else 9.0,
            t_max=14.0,
            rain_mm=0.0 if i <= 0 else rain,
            et0_mm=1.5,
            radiation_mj=6.0,
            daylight_h=11.0,
            wet_hours=0,
            is_forecast=i > 0,
        )
        for i in range(-14, 8)
    ]
    return Environment(lat=0.0, lon=0.0, days=days, source="synthetic")


def _rec(tmp_path, *, env, setting="outdoor", told=None, stress=1) -> AnalysisRecord:
    obs = Observation(
        species=[
            SpeciesCandidate(name="Salvia rosmarinus", common_name="rosemary", confidence=0.9)
        ],
        is_plant=True,
        water_stress=stress,
        decline=0,
        heat_light_stress=0,
        fine_leave_it=False,
        symptoms=[],
        leaf_cues=[],
        soil_surface="not_visible",
        setting=setting,
        container="pot",
    )
    pack = research("Salvia rosmarinus", "rosemary", cache_dir=tmp_path)
    return AnalysisRecord(
        record_id="r1",
        taken_at=datetime(ON.year, ON.month, ON.day, 10, tzinfo=UTC),
        observation=obs,
        environment=env,
        pack=pack,
        state=None,
        told=told,
    )


def test_six_scenarios():
    assert SCENARIOS == (
        "water",
        "dont_water",
        "shelter",
        "move_inside",
        "move_light",
        "wait_7_days",
    )


def test_frost_forecast_makes_moving_inside_better(tmp_path):
    r = run_scenario(_rec(tmp_path, env=_env(frost_night=2)), "move_inside")
    assert r.vs_leaving_it == "better" and "frost" in r.why


def test_no_frost_moving_inside_is_no_better(tmp_path):
    r = run_scenario(_rec(tmp_path, env=_env(rain=2.0)), "move_inside")
    assert r.vs_leaving_it in ("same", "worse")


def test_water_on_wet_soil_is_worse(tmp_path):
    r = run_scenario(_rec(tmp_path, env=_env(rain=2.0)), "water", soil_feel="wet")
    assert r.vs_leaving_it == "worse" and r.soil_feel == "wet"


def test_the_soil_feel_the_person_told_us_is_used(tmp_path):
    rec = _rec(tmp_path, env=_env(rain=2.0), told=Told(soil_feel="wet"))
    r = run_scenario(rec, "water")
    assert r.vs_leaving_it == "worse" and r.soil_feel == "wet"


def test_scenarios_match_the_answers_if_you_do_lines(tmp_path):
    rec = _rec(tmp_path, env=_env(frost_night=3))
    views = compare_actions(simulate(rec.observation, rec.environment, rec.pack, on=ON))
    for a in ("water", "dont_water", "shelter", "move_light"):
        r = run_scenario(rec, a)
        c = consequence_for(a, plant_key=None, month=10, answer="", views=views)
        assert (r.vs_leaving_it, r.why) == (views[a].vs_leaving_it, c.text)


def test_waiting_a_week_on_a_dry_pot_says_when_it_dries(tmp_path):
    r = run_scenario(_rec(tmp_path, env=_env(rain=0.0), stress=3), "wait_7_days")
    assert r.vs_leaving_it == "same" and r.why.startswith("dry by")


def test_waiting_a_week_in_damp_weather_is_fine(tmp_path):
    r = run_scenario(_rec(tmp_path, env=_env(rain=2.0)), "wait_7_days")
    assert r.why == "no dry days or frost in the next 7 days"


@pytest.mark.parametrize("action", SCENARIOS)
def test_indoor_plants_and_missing_weather_are_unknown(tmp_path, action):
    indoor = run_scenario(_rec(tmp_path, env=_env(), setting="indoor"), action)
    assert (indoor.vs_leaving_it, indoor.why) == ("unknown", INDOORS)
    no_weather = run_scenario(_rec(tmp_path, env=None), action)
    assert (no_weather.vs_leaving_it, no_weather.why) == ("unknown", NO_MODEL)


def test_tool_result_is_plain_json(tmp_path):
    r = run_scenario(_rec(tmp_path, env=_env(frost_night=2)), "move_inside")
    assert r.as_tool_result() == {
        "action": "move_inside",
        "vs_leaving_it": "better",
        "why": r.why,
        "soil_feel": None,
    }


def test_a_tender_plant_hears_cold_not_frost(tmp_path):
    rec = _rec(tmp_path, env=_env(frost_night=3))
    rec.pack = research("Ocimum basilicum", "basil", cache_dir=tmp_path)  # damage below 10 C
    assert run_scenario(rec, "move_inside").why.startswith("cold risk")
    assert run_scenario(rec, "wait_7_days").why.startswith("cold risk")
    assert run_scenario(rec, "shelter").why.startswith("cold risk")
