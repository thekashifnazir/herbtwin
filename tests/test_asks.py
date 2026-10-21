from herbtwin.asks import questions_for
from herbtwin.schemas import ActionCard, Answer, Observation


def _obs(decline=0):
    return Observation(
        species=[],
        is_plant=True,
        water_stress=1,
        decline=decline,
        heat_light_stress=0,
        fine_leave_it=False,
        symptoms=[],
        leaf_cues=[],
        soil_surface="not_visible",
    )


def _card(action):
    return ActionCard(
        action=action,
        when="today",
        because="b",
        if_you_do="x",
        if_you_do_from="none",
        less_sure=False,
    )


def _answer(*actions, tell_me_key=None):
    return Answer(
        headline="h",
        do=[_card(a) for a in actions],
        dont=None,
        watch="w",
        tell_me=None,
        tell_me_key=tell_me_key,
        level="fairly_sure",
        level_text="t",
        in_ten=6,
        factors=[],
        chips=[],
        compare=[],
        runs=[],
        assumptions=[],
    )


def test_soil_questions_only_when_watering_is_in_play():
    assert questions_for(_answer("water"), _obs()) == ["soil_feel", "last_watered", "question"]
    both = questions_for(_answer("prune", "dont_water"), _obs())
    assert both[:2] == ["soil_feel", "last_watered"]
    leave = questions_for(_answer("leave_normal", tell_me_key="soil_feel"), _obs())
    assert leave[0] == "soil_feel"
    assert questions_for(_answer("prune"), _obs()) == ["question"]


def test_changed_only_after_a_sudden_decline():
    assert "changed" in questions_for(_answer("prune"), _obs(decline=2))
    assert "changed" not in questions_for(_answer("prune"), _obs(decline=1))


def test_typed_question_is_always_offered_last():
    for a in (_answer("water"), _answer("prune"), _answer("leave_normal")):
        assert questions_for(a, _obs(decline=3))[-1] == "question"


def test_changed_uses_the_rise_since_a_recent_visit_when_there_is_one():
    assert "changed" in questions_for(_answer("prune"), _obs(decline=1), last_decline=0)
    assert "changed" not in questions_for(_answer("prune"), _obs(decline=2), last_decline=2)
    assert "changed" in questions_for(_answer("prune"), _obs(decline=2), last_decline=None)


def test_the_spot_questions_come_only_with_the_switch():
    squeeze = _answer("water", tell_me_key="soil_texture")
    assert "soil_texture" not in questions_for(squeeze, _obs())
    assert questions_for(squeeze, _obs(), spot=True) == [
        "soil_feel",
        "last_watered",
        "soil_texture",
        "question",
    ]
    aspect = _answer("leave_normal", tell_me_key="aspect")
    assert questions_for(aspect, _obs(), spot=True) == ["aspect", "question"]
