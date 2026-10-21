from pathlib import Path

from herbtwin.evals import twin_at_scale as T
from herbtwin.plant_model import ModelView


def test_the_case_set_is_the_pre_registered_one():
    cases = T.cases()
    assert len(cases) == 120 and len({c.id for c in cases}) == 120
    assert {c.scenario for c in cases} == set(T.SCENARIOS)
    # a hardy herb's frost night falls in midwinter, a tender herb's in autumn or spring
    chives = next(c for c in cases if c.id == "chives/frost/pot")
    basil = next(c for c in cases if c.id == "basil/frost/pot")
    assert chives.on.month in (12, 1, 2) and basil.on.month in (4, 10, 11)


def test_the_damage_lines_match_the_seed_packs():
    for case in T.cases()[:: len(T.SCENARIOS) * len(T.CONTAINERS)]:
        assert T.HARDY_LINE_C[case.common] == T.pack_for(case, Path("data/packs")).frost_damage_c


def test_the_twin_choice_is_what_beats_leaving_it_before_a_risky_day():
    base = {"leave_normal": ModelView("leave_normal", "same", "x", 3)}
    shelter = ModelView("shelter", "better", "cold risk Sunday", 3)
    small = ModelView("water", "better", "a little moister", None)  # no risky day
    assert T.twin_choice({**base, "shelter": shelter}) == {"shelter"}
    assert T.twin_choice({**base, "water": small}) == T.LEAVE


def test_the_arms_differ_only_in_the_plant_model_block():
    case = next(c for c in T.cases() if c.id == "basil/uk_frost/pot")
    p = T.prompts(case, T.pack_for(case, Path("data/packs")))
    off, on = p["off"].context, p["on"].context
    assert off.split("PLANT MODEL")[0] == on.split("PLANT MODEL")[0]
    assert "Truro" in off or "London" in off or "Edinburgh" in off or "Manchester" in off
    assert off != on


def _row(id_, arm, primary, choice, repeat=0, app=None):
    return {
        "id": id_,
        "arm": arm,
        "repeat": repeat,
        "status": "ok",
        "primary": primary,
        "app_primary": app or primary,
        "twin_choice": sorted(choice),
        "scenario": "frost",
        "agree": 3,
        "total": 3,
    }


def test_the_summary_scores_each_metric_where_it_applies_and_pairs_the_arms():
    risky, fine = ["shelter"], sorted(T.LEAVE)
    rows = [
        _row("a", "off", "leave_normal", risky),
        _row("a", "on", "shelter", risky),
        _row("b", "off", "shelter", fine),
        _row("b", "on", "leave_normal", fine),
        _row("c", "off", "treat_or_remove", fine),
        _row("c", "on", "leave_normal", fine),
    ]
    s = T.summarise(rows, n=200)
    assert s["arms"]["off"]["twin_match"]["value"] == 0.0
    assert s["arms"]["on"]["twin_match"]["value"] == 1.0
    assert s["arms"]["on"]["protect_when_needed"]["n"] == 1
    assert s["arms"]["on"]["leave_when_fine"]["n"] == 2
    assert abs(s["arms"]["off"]["over_treat"]["value"] - 1 / 3) < 1e-9
    assert s["diff"]["twin_match"]["value"] == 1.0
    assert s["risky_cases"] == ["a"]


def test_the_summary_says_how_many_risky_cases_moved():
    # an interval on 84 rows can rest on a handful of cases: the report names them
    risky = ["shelter"]
    rows = [
        _row("a", "off", "leave_normal", risky),
        _row("a", "on", "shelter", risky),
        _row("b", "off", "shelter", risky),
        _row("b", "on", "shelter", risky),
    ]
    f = T.summarise(rows, n=100)["risky_flips"]
    assert (f["to_twin"], f["away"], f["of"]) == (["a"], [], 2)
    assert f["sign_test_p"] == 1.0  # one case alone is no evidence
