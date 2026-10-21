import json

import pytest

from herbtwin.adapters.mock import MockAdapter
from herbtwin.schemas import Observation
from herbtwin.stages.observe import OBSERVE_SCHEMA, ObserveError, observe, to_prompt_summary

GOOD = {
    "species": [{"name": "Ocimum basilicum", "common_name": "basil", "confidence": 0.82}],
    "is_plant": True,
    "water_stress": 2,
    "heat_light_stress": 0,
    "fine_leave_it": False,
    "symptoms": ["drooping leaves"],
    "leaf_cues": ["droop"],
    "soil_surface": "dry",
    "notes": "",
}


def test_parses_structured_output():
    obs = observe(MockAdapter([json.dumps(GOOD)]), b"\xff\xd8", "image/jpeg")
    assert obs.species[0].common_name == "basil"
    assert obs.water_stress == 2


def test_repairs_once_when_model_returns_prose():
    adapter = MockAdapter(["It looks like basil, quite droopy.", json.dumps(GOOD)])
    obs = observe(adapter, b"\xff\xd8", "image/jpeg")
    assert obs.species[0].name == "Ocimum basilicum"
    assert len(adapter.calls) == 2
    assert "It looks like basil" in adapter.calls[1]["prompt"]  # repair quotes the bad reply


def test_fails_loudly_after_repair_with_out_of_range_score():
    bad = dict(GOOD, water_stress=7)
    adapter = MockAdapter([json.dumps(bad), json.dumps(bad)])
    with pytest.raises(ObserveError) as e:
        observe(adapter, b"\xff\xd8", "image/jpeg")
    assert "water_stress" in e.value.raw or "7" in e.value.raw
    assert len(adapter.calls) == 2


def test_not_a_plant_zeroes_everything():
    out = dict(GOOD, is_plant=False, water_stress=3)
    obs = observe(MockAdapter([json.dumps(out)]), b"\xff\xd8", "image/jpeg")
    assert obs.is_plant is False
    assert obs.species == [] and obs.water_stress == 0


def test_provider_failure_becomes_observe_error():
    with pytest.raises(ObserveError, match="mock exhausted"):
        observe(MockAdapter([]), b"\xff\xd8", "image/jpeg")


def test_few_shot_examples_land_in_prompt():
    adapter = MockAdapter([json.dumps(GOOD)])
    observe(
        adapter, b"\xff\xd8", "image/jpeg", few_shot=["Example: drooping basil -> water_stress 2"]
    )
    assert "drooping basil" in adapter.calls[0]["prompt"]


def test_observe_gives_the_vision_model_room_to_finish_on_both_calls():
    adapter = MockAdapter(["prose", json.dumps(GOOD)])
    observe(adapter, b"\xff\xd8", "image/jpeg")
    assert all(c["max_tokens"] >= 4096 for c in adapter.calls) and len(adapter.calls) == 2
    assert "at most 3" in adapter.calls[0]["prompt"]


def test_new_fields_parse_and_default_for_old_recordings():
    full = dict(GOOD, decline=2, leaf_colour="some_yellow")
    obs = observe(MockAdapter([json.dumps(full)]), b"\xff\xd8", "image/jpeg")
    assert obs.decline == 2 and obs.leaf_colour == "some_yellow"
    old = observe(MockAdapter([json.dumps(GOOD)]), b"\xff\xd8", "image/jpeg")
    assert old.decline == 0 and old.leaf_colour == "not_visible"


def test_schema_requires_the_new_fields():
    from herbtwin.stages.observe import OBSERVE_SCHEMA

    assert {"decline", "leaf_colour"} <= set(OBSERVE_SCHEMA["required"])
    assert OBSERVE_SCHEMA["properties"]["leaf_colour"]["enum"] == [
        "green",
        "some_yellow",
        "mostly_yellow",
        "not_visible",
    ]


def test_strict_mode_repairs_then_fails_when_new_fields_are_missing():
    # In an eval, a reply that omits decline must not be scored as "no decline".
    adapter = MockAdapter([json.dumps(GOOD), json.dumps(GOOD)])
    with pytest.raises(ObserveError, match="decline"):
        observe(adapter, b"\xff\xd8", "image/jpeg", strict=True)
    assert len(adapter.calls) == 2


def test_strict_mode_accepts_a_complete_reply():
    full = dict(GOOD, decline=1, leaf_colour="green")
    obs = observe(MockAdapter([json.dumps(full)]), b"\xff\xd8", "image/jpeg", strict=True)
    assert obs.decline == 1


def test_not_a_plant_also_clears_decline_and_colour():
    out = dict(GOOD, is_plant=False, decline=3, leaf_colour="mostly_yellow")
    obs = observe(MockAdapter([json.dumps(out)]), b"\xff\xd8", "image/jpeg")
    assert obs.decline == 0 and obs.leaf_colour == "not_visible"


def test_prompt_separates_droop_from_decline():
    adapter = MockAdapter([json.dumps(GOOD)])
    observe(adapter, b"\xff\xd8", "image/jpeg")
    prompt = adapter.calls[0]["prompt"]
    assert "posture" in prompt and "decline" in prompt


def test_phase_a_fields_parse_and_reach_the_prompt_summary():
    reply = {
        **GOOD,
        "setting": "outdoor",
        "container": "ground",
        "photo_quality": "poor",
        "quality_note": "blurred",
    }
    obs = observe(MockAdapter([json.dumps(reply)]), b"\xff\xd8", "image/jpeg")
    assert (obs.setting, obs.container, obs.photo_quality) == ("outdoor", "ground", "poor")
    summary = json.loads(to_prompt_summary(obs))
    assert summary["setting"] == "outdoor" and summary["container"] == "ground"
    assert summary["photo_quality"] == "poor"


def test_recordings_without_phase_a_fields_still_parse():
    obs = Observation.model_validate(GOOD)
    assert (obs.setting, obs.container, obs.photo_quality) == ("unknown", "unknown", "good")


def test_strict_mode_does_not_require_the_unscored_phase_a_fields():
    reply = {**GOOD, "decline": 0, "leaf_colour": "green"}
    obs = observe(MockAdapter([json.dumps(reply)]), b"\xff\xd8", "image/jpeg", strict=True)
    assert obs.setting == "unknown"


def test_schema_asks_for_the_phase_a_fields():
    for k in ("setting", "container", "photo_quality"):
        assert k in OBSERVE_SCHEMA["required"]


def test_the_read_says_whether_the_photo_is_one_plant_a_bed_or_neither():
    # 16 Oct probe: a planted raised bed came back is_plant=true, "Salad rocket", and a
    # bare bed is_plant=true with no species, so the read names the scene itself
    assert "scene" in OBSERVE_SCHEMA["required"]
    assert OBSERVE_SCHEMA["properties"]["scene"]["enum"] == [
        "one_plant",
        "bed_or_border",
        "no_plant",
    ]
    assert "bed_or_border" in observe.__globals__["SYSTEM"]
    bed = observe(
        MockAdapter([json.dumps({**GOOD, "scene": "bed_or_border"})]), b"\xff\xd8", "image/jpeg"
    )
    assert bed.scene == "bed_or_border"
    assert Observation.model_validate(GOOD).scene == "one_plant"  # recordings made before it


def test_not_a_plant_is_never_read_as_one_plant():
    out = {**GOOD, "is_plant": False, "scene": "one_plant"}
    assert observe(MockAdapter([json.dumps(out)]), b"\xff\xd8", "image/jpeg").scene == "no_plant"
    bare = {**GOOD, "is_plant": False, "species": [], "scene": "bed_or_border"}
    assert (
        observe(MockAdapter([json.dumps(bare)]), b"\xff\xd8", "image/jpeg").scene == "bed_or_border"
    )


def test_the_read_says_whether_the_plant_has_outgrown_its_pot():
    # 21 Oct, a gardener asked "is it too big for its pot?": the read says, and the advisor
    # sees it with the rest of the photo (repot advice; in_season keeps it to its months)
    assert (
        "pot_fit" in OBSERVE_SCHEMA["properties"] and "too_small" in observe.__globals__["SYSTEM"]
    )
    assert "pot_fit" not in OBSERVE_SCHEMA["required"]  # a reply may leave it out
    tight = {**GOOD, "container": "pot", "pot_fit": "too_small"}
    obs = observe(MockAdapter([json.dumps(tight)]), b"\xff\xd8", "image/jpeg")
    assert obs.pot_fit == "too_small"
    assert json.loads(to_prompt_summary(obs))["pot_fit"] == "too_small"
    empty = {**tight, "is_plant": False, "species": []}  # an empty pot has no plant to fit
    assert observe(MockAdapter([json.dumps(empty)]), b"\xff\xd8", "image/jpeg").pot_fit == "unknown"
    bed = {**tight, "container": "ground"}  # a plant in the ground has no pot to outgrow
    assert observe(MockAdapter([json.dumps(bed)]), b"\xff\xd8", "image/jpeg").pot_fit == "unknown"
    # a reply without it, and every recording made before it, still parses
    assert observe(MockAdapter([json.dumps(GOOD)]), b"\xff\xd8", "image/jpeg").pot_fit == "unknown"
