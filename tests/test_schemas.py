from datetime import date, datetime

import pytest
from pydantic import ValidationError

from herbtwin.schemas import (
    AnalysisRecord,
    DailyWeather,
    Observation,
    SpeciesCandidate,
    StageFailure,
)


def test_observation_scores_are_bounded():
    with pytest.raises(ValidationError):
        Observation(
            species=[],
            is_plant=True,
            water_stress=4,
            heat_light_stress=0,
            fine_leave_it=False,
            symptoms=[],
            leaf_cues=[],
            soil_surface="dry",
            notes="",
        )


def test_species_confidence_is_bounded():
    with pytest.raises(ValidationError):
        SpeciesCandidate(name="Ocimum basilicum", common_name="basil", confidence=1.4)


def test_analysis_record_round_trips_with_partial_failure():
    rec = AnalysisRecord(
        record_id="abc",
        taken_at=datetime(2026, 10, 2, 9, 0),
        observation=None,
        environment=None,
        pack=None,
        state=None,
        failures=[StageFailure(stage="observe", message="model returned prose", raw="hello")],
    )
    again = AnalysisRecord.model_validate_json(rec.model_dump_json())
    assert again.failures[0].stage == "observe"
    assert again.observation is None


def test_daily_weather_round_trip():
    d = DailyWeather(
        date=date(2026, 10, 2),
        t_min=6.0,
        t_max=15.0,
        rain_mm=2.0,
        et0_mm=1.1,
        radiation_mj=8.0,
        daylight_h=11.5,
        wet_hours=5,
        is_forecast=False,
    )
    assert DailyWeather.model_validate_json(d.model_dump_json()) == d


NEW_ACTIONS = (
    "feed",
    "repot",
    "change_soil",
    "check_pests",
    "isolate",
    "mulch",
    "humidity",
    "rotate",
)


def test_every_care_action_has_a_definition_and_a_coarse_class():
    from herbtwin.schemas import CARE_ACTION_DEFINITIONS, CARE_ACTIONS, COARSE_ACTIONS, coarse

    assert set(NEW_ACTIONS) <= set(CARE_ACTIONS) and len(CARE_ACTIONS) == 17
    assert set(CARE_ACTION_DEFINITIONS) == set(CARE_ACTIONS)
    assert all(coarse(a) in COARSE_ACTIONS for a in CARE_ACTIONS)


def test_coarse_map_is_the_agreed_one():
    from herbtwin.schemas import COARSE_ACTIONS, coarse

    assert coarse("check_pests") == "ask_first"
    assert coarse("isolate") == "treat_or_remove"
    for a in ("feed", "repot", "change_soil", "mulch", "humidity", "rotate"):
        assert coarse(a) == "other"
    for a in COARSE_ACTIONS:
        assert coarse(a) == a


def test_coarse_classes_keep_phase_a_wording():
    from herbtwin.schemas import COARSE_ACTION_DEFINITIONS, COARSE_ACTIONS

    assert COARSE_ACTIONS == (
        "water",
        "dont_water",
        "move_light",
        "shelter",
        "treat_or_remove",
        "prune",
        "leave_normal",
        "ask_first",
        "other",
    )
    assert COARSE_ACTION_DEFINITIONS["other"] == (
        "any other action (feed, repot, change soil, buy a new plant, ...)"
    )


def test_unknown_action_is_refused():
    from herbtwin.schemas import coarse

    with pytest.raises(KeyError):
        coarse("dance")


def test_told_question_is_trimmed_and_whitespace_collapsed():
    from herbtwin.schemas import Told

    t = Told(question="  should I\ncut   the brown bits off?  ")
    assert t.question == "should I cut the brown bits off?"
    assert Told(question="   ").question is None and Told().is_empty()


def test_told_place_is_trimmed_and_counts_as_an_answer():
    from herbtwin.schemas import Told

    t = Told(place="  Leeds\n city  ")
    assert t.place == "Leeds city"
    assert not Told(place="Leeds").is_empty()


def test_told_refuses_control_characters_and_long_text():
    from herbtwin.schemas import Told

    with pytest.raises(ValidationError):
        Told(question="hi\x00there")
    with pytest.raises(ValidationError):
        Told(question="x" * 501)
    with pytest.raises(ValidationError):
        Told(place="x" * 81)
    with pytest.raises(ValidationError):
        Told(place="Leeds\x00")
    with pytest.raises(ValidationError):
        Told(soil_feel="soggy")
    with pytest.raises(ValidationError):
        Told(mood="sad")  # unknown fields are refused, not ignored
