from datetime import UTC, datetime, timedelta

import pytest

from herbtwin import scoring
from herbtwin.history import AdviceScore, Evidence, StoredAnswer
from herbtwin.schemas import (
    ActionCard,
    Answer,
    Comparison,
    LightReading,
    Observation,
    SpeciesCandidate,
)

T0 = datetime(2026, 10, 2, 10, tzinfo=UTC)
PASSED = scoring.Gate(
    prompt_version="c2-v1",
    signals={"posture": "passed", "tissue": "untested", "colour": "untested"},
)


def _obs(stress=2, decline=0, species="Petroselinum crispum", quality="good"):
    return Observation(
        species=[SpeciesCandidate(name=species, common_name="parsley", confidence=0.9)],
        is_plant=True,
        water_stress=stress,
        decline=decline,
        heat_light_stress=0,
        fine_leave_it=False,
        symptoms=[],
        leaf_cues=[],
        soil_surface="dry",
        photo_quality=quality,
    )


def _answer(action="water"):
    card = ActionCard(
        action=action,
        when="today",
        because="dry",
        if_you_do="",
        if_you_do_from="none",
        less_sure=False,
    )
    return Answer(
        headline="Water it.",
        do=[card],
        dont=None,
        watch="",
        tell_me=None,
        level="sure",
        level_text="Sure",
        in_ten=8,
        factors=[],
        chips=[],
        compare=[],
        runs=[],
        assumptions=[],
    )


def _light(now):
    return LightReading(
        fraction=1.0,
        now=now,
        local_time=datetime(2026, 10, 2, 12),
        lux=1,
        sky_wm2=100,
        route="shutter",
    )


def _stored(aid, when, action="water", obs=None, light=None, predicted=True):
    obs = obs or _obs()
    answer = _answer(action)
    if predicted:
        answer.prediction = scoring.predict(answer, obs)
    return StoredAnswer(
        id=aid,
        plant_id="p",
        taken_at=when,
        created_at=when,
        photo_path=f"u1/{aid}.jpg",
        observation=obs,
        evidence=Evidence(
            location=None,
            taken_at_source="exif",
            environment=None,
            pack=None,
            season=None,
            notes=[],
            failures=[],
            season_missing=None,
            weather_missing=None,
            light=light,
        ),
        answer=answer,
        told=None,
    )


def _comparison(verdict, reason=None):
    return Comparison(
        signal="posture",
        verdict=verdict,
        reason=reason,
        looks=[],
        prompt_version="c2-v1",
        model="m",
    )


def test_every_rule_names_a_source():
    assert all(rule.source for rule in scoring.RULES.values())


def test_water_predicts_less_droop_when_drooping_and_not_more_when_not():
    p = scoring.predict(_answer("water"), _obs(stress=2))
    assert (p.signal, p.expected, p.window_days, p.before) == ("posture", "less", (1, 7), 2)
    assert scoring.predict(_answer("water"), _obs(stress=0)).expected == "not_more"


def test_other_rules():
    assert scoring.predict(_answer("dont_water"), _obs()).expected == "not_more"
    leave = scoring.predict(_answer("leave_normal"), _obs(decline=1))
    assert (leave.signal, leave.window_days, leave.before) == ("tissue", (3, 21), 1)
    prune = scoring.predict(_answer("prune"), _obs())
    assert prune.signal == "tissue" and prune.less_sure is True
    feed = scoring.predict(_answer("feed"), _obs())
    assert (feed.signal, feed.window_days, feed.before) == ("colour", (7, 21), None)


def test_unscored_actions_and_empty_answers_predict_nothing():
    assert scoring.predict(_answer("repot"), _obs()) is None
    empty = _answer()
    empty.do = []
    assert scoring.predict(empty, _obs()) is None
    assert scoring.predict(_answer(), None) is None


@pytest.mark.parametrize(
    ("days", "due"),
    # 23 h counts as a day: EXIF wall time is stored as if UTC, so a pair of one EXIF and
    # one undated photo is off by the UTC offset (an hour in summer)
    [
        (0.9, False),
        (23 / 24, True),
        (1.0, True),
        (3.0, True),
        (7.0, True),
        (7 + 1 / 24, True),
        (7.1, False),
    ],
)
def test_water_window_edges(days, due):
    earlier = _stored("e" * 32, T0)
    later = _stored("f" * 32, T0 + timedelta(days=days))
    assert (scoring.earlier_visit([earlier], later) is earlier) is due


def test_only_the_latest_earlier_visit_is_asked_about():
    oldest = _stored("a" * 32, T0)  # 3 days before: inside its own window
    latest = _stored("b" * 32, T0 + timedelta(days=2, hours=12), action="repot")  # not scored
    later = _stored("c" * 32, T0 + timedelta(days=3))
    assert scoring.earlier_visit([latest, oldest], later) is None


def test_an_answer_without_a_prediction_is_never_due():
    earlier = _stored("e" * 32, T0, predicted=False)
    assert scoring.earlier_visit([earlier], _stored("f" * 32, T0 + timedelta(days=2))) is None


def test_the_later_answer_itself_and_later_visits_are_not_earlier_visits():
    later = _stored("f" * 32, T0 + timedelta(days=2))
    after = _stored("g" * 32, T0 + timedelta(days=3))
    assert scoring.earlier_visit([after, later], later) is None


@pytest.mark.parametrize(
    ("a", "b", "mismatch"),
    [
        ("direct_sun", "bright_shade", True),
        ("deep_shade", "direct_sun", True),
        ("bright_shade", "deep_shade", False),
        ("direct_sun", "direct_sun", False),
        (None, "direct_sun", False),
    ],
)
def test_light_mismatch(a, b, mismatch):
    assert scoring.light_mismatch(a, b) is mismatch


def _pair(**later_kw):
    return _stored("e" * 32, T0), _stored("f" * 32, T0 + timedelta(days=2), **later_kw)


def test_plan_score_runs_the_comparison_when_nothing_stops_it():
    e, later = _pair()
    assert scoring.plan_score(e, later, "yes", PASSED) == (None, None)


def test_plan_score_without_a_call():
    e, later = _pair()
    assert scoring.plan_score(e, later, "skip", PASSED) == ("cant_tell", "you skipped the question")
    untested = PASSED.model_copy(update={"signals": {"posture": "failed"}})
    assert scoring.plan_score(e, later, "yes", untested) == ("not_scored_yet", None)
    e, poor = _pair(obs=_obs(quality="poor"))
    assert scoring.plan_score(e, poor, "yes", PASSED) == ("cant_tell", "one of the photos was poor")
    e, other = _pair(obs=_obs(species="Mentha spicata"))
    assert scoring.plan_score(e, other, "partly", PASSED)[1] == (
        "the plant was named differently in the two photos"
    )
    e = _stored("e" * 32, T0, light=_light("direct_sun"))
    shade = _stored("f" * 32, T0 + timedelta(days=2), light=_light("deep_shade"))
    assert scoring.plan_score(e, shade, "yes", PASSED) == (
        "cant_tell",
        "one photo was in direct sun and the other in shade",
    )
    assert scoring.plan_score(e, shade, "no", PASSED)[0] == "not_done"


@pytest.mark.parametrize(
    ("did_it", "verdict", "result"),
    [
        ("yes", "less", "improved"),
        ("partly", "same", "no_clear_change"),
        ("yes", "more", "worse"),
        ("yes", "cant_tell", "cant_tell"),
        ("no", "less", "not_done"),
    ],
)
def test_result_of(did_it, verdict, result):
    got, reason = scoring.result_of(did_it, _comparison(verdict, "why"))
    assert got == result
    assert reason == ("why" if result == "cant_tell" else None)


def _score(result, did_it="yes", verdict=None, reason=None, action="water", signal="posture"):
    p = scoring.predict(_answer(action), _obs())
    return AdviceScore(
        plant_id="p",
        earlier_answer_id="e" * 32,
        later_answer_id="f" * 32,
        prediction=p,
        did_it=did_it,
        result=result,
        reason=reason,
        comparison=_comparison(verdict) if verdict else None,
        scored_at=T0,
    )


def test_ask_text():
    assert scoring.ask_text(_stored("e" * 32, T0)) == (
        "On 2 Oct we suggested watering it. Did you do it?"
    )


@pytest.mark.parametrize(
    ("score", "line"),
    [
        (
            _score("improved", verdict="less"),
            "Last advice: water (you did it). Since then: less droop.",
        ),
        (
            _score("worse", did_it="partly", verdict="more"),
            "Last advice: water (you partly did it). Since then: more droop.",
        ),
        (
            _score("cant_tell", verdict="cant_tell", reason="the four looks did not agree"),
            "Last advice: water (you did it). Since then: couldn't tell from these two photos "
            "(the four looks did not agree).",
        ),
        (_score("not_done", did_it="no", verdict="less"), "Last advice: water (you didn't)."),
        (_score("cant_tell", did_it="skip"), "Last advice: water (you skipped the question)."),
        (
            _score("not_scored_yet", action="leave_normal"),
            "Last advice: leave it (you did it). We can't check dead or brown parts from "
            "photos reliably yet.",
        ),
    ],
)
def test_score_line(score, line):
    assert scoring.score_line(score) == line


def test_score_lines_are_keyed_by_the_later_answer():
    assert scoring.score_lines([_score("improved", verdict="less")]) == {
        "f" * 32: "Last advice: water (you did it). Since then: less droop."
    }


def test_the_committed_gate_file_loads():
    gate = scoring.load_gate()
    assert set(gate.signals) == {"posture", "tissue", "colour"}
    assert set(gate.signals.values()) <= {"passed", "failed", "untested"}
