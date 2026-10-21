"""Stage 2 of the trusted-page check (stages/trusted_check.decide): plain code over the
form Stage 1 read and the plant's state. It agrees only when every part is checkable."""

import pytest

from herbtwin.stages.trusted_check import Condition, Form, PlantState, decide, months_in

DO = {"polarity": "do", "applies_to": "this_plant", "hedged": False, "is_instruction": True}


def form(action="water", conditions=(), **kw):
    return Form(
        action=action,
        conditions=[Condition(kind=k, value=v) for k, v in conditions],
        **{**DO, **kw},
    )


def st(**kw):
    return PlantState(**{"plant": "basil", "month": 10, "action": "water", **kw})


def test_a_plain_instruction_for_our_action_agrees():
    assert decide(form(), st()) == "agree"
    assert decide(form("bring_in"), st(action="shelter")) == "agree"  # the same advice
    assert decide(form("protect_cold"), st(action="shelter")) == "agree"


@pytest.mark.parametrize(
    "change",
    [
        {"polarity": "dont"},
        {"hedged": True},
        {"is_instruction": False},
        {"applies_to": "other_plant"},
        {"action": "withhold_water"},
        {"action": "feed"},
    ],
)
def test_anything_less_than_a_plain_do_of_our_action_is_unsure(change):
    action = change.pop("action", "water")
    assert decide(form(action, **change), st()) == "unsure"


def test_leave_it_never_agrees_and_no_form_is_unsure():
    assert decide(form("none"), st(action="leave_normal")) == "unsure"
    assert decide(None, st()) == "unsure"


@pytest.mark.parametrize(
    ("group", "plant", "want"),
    [("tender herbs", "basil", "agree"), ("tender herbs", "rosemary", "unsure"),
     ("tender herbs", "coriander", "unsure"),
     ("Mediterranean herbs", "thyme", "agree"), ("woody herbs", "rosemary", "unsure")],
)  # fmt: skip
def test_a_plant_group_agrees_only_for_a_member(group, plant, want):
    f = form(applies_to="plant_group", group=group)
    assert decide(f, st(plant=plant)) == want


@pytest.mark.parametrize(
    ("cond", "holding", "failing"),
    [
        (("soil_dry", ""), {"soil": "dry"}, {"soil": "wet"}),
        (("soil_wet", ""), {"soil": "wet"}, {"soil": "moist"}),
        (("cold_or_frost_forecast", ""), {"cold_ahead": True}, {"cold_ahead": False}),
        (("hot_dry_weather", ""), {"hot_dry": True}, {"hot_dry": False}),
        (("rain_forecast", ""), {"rain_ahead": True}, {"rain_ahead": False}),
        (("indoor", ""), {"setting": "indoor"}, {"setting": "outdoor"}),
        (("container", "pot"), {"container": "pot"}, {"container": "ground"}),
        (("named_problem", "downy mildew"), {"problem": "downy mildew"}, {"problem": "aphids"}),
        (("plant_stage", "seedlings"), {"seedlings": True}, {"seedlings": False}),
        (("month_range", "autumn"), {"month": 10}, {"month": 4}),
    ],
)
def test_each_condition_must_hold_in_the_state(cond, holding, failing):
    f = form(conditions=[cond])
    assert decide(f, st(**holding)) == "agree"
    assert decide(f, st(**failing)) == "unsure"


def test_a_condition_the_state_cannot_tell_or_we_cannot_check_is_unsure():
    assert decide(form(conditions=[("soil_dry", "")]), st()) == "unsure"  # soil unknown
    assert decide(form(conditions=[("cold_or_frost_forecast", "")]), st()) == "unsure"
    assert decide(form(conditions=[("other", "late at night")]), st()) == "unsure"
    assert decide(form(conditions=[("month_range", "after flowering")]), st()) == "unsure"
    # every condition must hold, not just one
    both = form(conditions=[("soil_dry", ""), ("cold_or_frost_forecast", "")])
    assert decide(both, st(soil="dry")) == "unsure"
    assert decide(both, st(soil="dry", cold_ahead=True)) == "agree"


@pytest.mark.parametrize(
    ("value", "months"),
    [("spring", {3, 4, 5}), ("October", {10}), ("March to May", {3, 4, 5}),
     ("November to February", {11, 12, 1, 2}), ("Sept", {9}), ("after flowering", None),
     ("late autumn", {11}), ("early spring", {3}), ("mid-summer", {7}), ("late winter", {2}),
     ("late March", {3})],
)  # fmt: skip
def test_month_ranges_are_read_or_refused(value, months):
    assert months_in(value) == months


@pytest.mark.parametrize(
    ("ours", "theirs"),
    [("dont_water", "water_less"), ("prune", "deadhead"), ("prune", "thin")],
)
def test_near_miss_actions_are_not_our_advice(ours, theirs):
    """Watering less is not holding off; deadheading or thinning is not cutting back."""
    assert decide(form(theirs), st(action=ours)) == "unsure"


@pytest.mark.parametrize(
    "cond",
    [("rain_forecast", "heavy rain"), ("cold_or_frost_forecast", "a hard frost"),
     ("soil_dry", "very dry"), ("plant_trait", "leggy")],
)  # fmt: skip
def test_a_strength_or_trait_the_state_cannot_confirm_is_unsure(cond):
    full = {"rain_ahead": True, "cold_ahead": True, "soil": "dry"}
    assert decide(form(conditions=[cond]), st(**full)) == "unsure"


@pytest.mark.parametrize(
    ("sentence", "state", "want"),
    [
        ("Water the pots when heavy rain has missed them.", {}, "unsure"),
        ("Fleece basil before a hard frost.", {}, "unsure"),
        ("Water young basil daily.", {}, "unsure"),
        ("Water beds of basil in the evening.", {"container": "pot"}, "unsure"),
        ("Water beds of basil in the evening.", {"container": "ground"}, "agree"),
        ("Water pots of basil in the evening.", {"container": "ground"}, "unsure"),
        ("Water pots of basil in the evening.", {"container": "pot"}, "agree"),
        ("Water basil in the evening.", {"container": "unknown"}, "agree"),
    ],
)
def test_the_sentence_itself_is_checked_for_what_the_state_cannot_confirm(sentence, state, want):
    """Even when Stage 1 leaves the qualifier out of the form."""
    assert decide(form(), st(**state), sentence) == want


def test_treating_or_removing_must_name_the_problem_we_found():
    remove = form("treat_or_remove")
    assert decide(remove, st(action="treat_or_remove", problem="aphids")) == "unsure"
    named = form("treat_or_remove", conditions=[("named_problem", "aphids")])
    assert decide(named, st(action="treat_or_remove", problem="aphids")) == "agree"
    assert decide(named, st(action="treat_or_remove", problem="mint rust")) == "unsure"


@pytest.mark.parametrize(
    "sentence",
    ["Water when the soil is bone dry.", "Water when the soil is bone-dry.",
     "Water once the compost is parched.", "Hold off while the soil is soggy.",
     "Hold off in waterlogged ground."],
)  # fmt: skip
def test_round_5_strengths_are_unsure(sentence):
    assert decide(form(), st(container="unknown"), sentence) == "unsure"


def test_pulling_up_the_whole_plant_is_not_removing_affected_parts():
    named = [("named_problem", "downy mildew")]
    whole = form("remove_plant", conditions=named)
    assert decide(whole, st(action="treat_or_remove", problem="downy mildew")) == "unsure"
    assert decide(whole, st(action="remove_plant", problem="downy mildew")) == "agree"
    assert decide(form("remove_plant"), st(action="remove_plant", problem="x")) == "unsure"


@pytest.mark.parametrize(
    "sentence",
    ["Pinch out the growing tips of basil.", "Keep basil pinched to stop it flowering.",
     "Pinching the tips keeps it bushy, so do it often."],
)  # fmt: skip
def test_pinching_out_is_not_cutting_back(sentence):
    # post-test tightening (round 5's 4 false agrees were all pinch-out lines the blind
    # labeller did not count as "cut it back"): code only, it can only remove agrees
    assert decide(form("prune"), st(action="prune"), sentence) == "unsure"
    assert decide(form("prune"), st(action="prune"), "Cut basil back by a third.") == "agree"


def test_checking_for_a_pest_is_not_treating_it():
    # post-test (live, 19 Oct): "check for" was read as treat_or_remove
    pest = form("treat_or_remove", conditions=[("named_problem", "rosemary beetle")])
    state = st(plant="rosemary", action="treat_or_remove", problem="rosemary beetle")
    for looking in (
        "Check rosemary plants regularly for rosemary beetle.",
        "Inspect rosemary for rosemary beetle.",
        "Look out for rosemary beetle.",
    ):
        assert decide(pest, state, looking) == "unsure"
    assert decide(pest, state, "Pick off and destroy rosemary beetle.") == "agree"


@pytest.mark.parametrize(
    ("sentence", "form_action", "state"),
    [
        # live pages, 19 Oct: each read by the model as our action, none saying it
        ("Dig up and destroy mint plants affected by rust.", "treat_or_remove",
         {"plant": "mint", "action": "treat_or_remove", "problem": "mint rust"}),
        ("When growing basil in a greenhouse, ventilate well to help reduce problems.",
         "protect_cold", {"action": "shelter", "setting": "indoor"}),
        ("Remove the affected plants straight away.", "treat_or_remove",
         {"action": "treat_or_remove", "problem": "mint rust"}),
    ],
)  # fmt: skip
def test_the_action_must_be_said_and_whole_plants_are_not_their_parts(sentence, form_action, state):
    conds = [("named_problem", "rust")] if form_action == "treat_or_remove" else []
    assert decide(form(form_action, conditions=conds), st(**state), sentence) == "unsure"


@pytest.mark.parametrize(
    ("sentence", "form_action", "action"),
    [
        ("Give sage a long drink.", "water", "water"),
        ("Hold back on watering the thyme.", "withhold_water", "dont_water"),
        ("Basil should come inside for winter.", "bring_in", "shelter"),
        ("Cover basil with fleece.", "protect_cold", "shelter"),
        ("Shift basil to the sunniest windowsill.", "move_light", "move_light"),
        ("Trim sage lightly.", "prune", "prune"),
    ],
)
def test_each_action_in_its_own_words_still_agrees(sentence, form_action, action):
    s = st(action=action, setting="unknown", container="unknown")
    assert decide(form(form_action), s, sentence) == "agree"


@pytest.mark.parametrize(
    ("value", "want"),
    [
        ("may indicate the roots are too wet", None),  # the verb, not the month
        ("it may be harder in heavy soil", None),
        ("May", {5}),
        ("late may", {5}),
        ("in may", {5}),
        ("March to May", {3, 4, 5}),
        ("autumn", {9, 10, 11}),
    ],
)
def test_may_is_a_month_only_when_it_reads_as_one(value, want):
    assert months_in(value) == want


@pytest.mark.parametrize(
    ("value", "month", "want"),
    [("May", 5, True), ("May to June", 6, True), ("April or May", 5, True),
     ("may indicate", 5, None), ("May", 10, False)],
)  # fmt: skip
def test_a_month_range_condition_keeps_its_own_case(value, month, want):
    # review of #305: holds() lowercased the value first, so "May" never read as the month
    from herbtwin.stages.trusted_check import holds

    assert holds(Condition(kind="month_range", value=value), st(month=month)) is want
