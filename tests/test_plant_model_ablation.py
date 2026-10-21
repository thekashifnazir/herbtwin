import difflib

import pytest

from herbtwin.evals import plant_model_ablation as A


def _row(item_id, scenario, arm, primary, repeat=0, status="ok"):
    return {
        "id": item_id,
        "scenario": scenario,
        "arm": arm,
        "primary": primary,
        "repeat": repeat,
        "status": status,
    }


def test_sixty_items_five_herbs_four_scenarios_three_variants():
    items = A.items()
    assert len(items) == 60 and len({i.id for i in items}) == 60
    assert {i.scenario for i in items} == set(A.SCENARIOS)


def test_only_the_told_variant_carries_a_soil_word():
    told = [i for i in A.items() if i.told is not None]
    assert told and all(i.variant == "pot_told" for i in told)


@pytest.mark.parametrize(
    ("scenario", "primary", "right"),
    [
        ("frost", "shelter", True),
        ("frost", "leave_normal", False),
        ("wet", "dont_water", True),
        ("wet", "water", False),
        ("dry", "water", True),
        ("dry", "leave_normal", False),
        ("mild", "leave_normal", True),
        ("mild", "feed", False),  # a fine action scores by its coarse class ("other")
    ],
)
def test_the_rule_for_each_scenario(scenario, primary, right):
    assert A.correct(scenario, primary) is right


def test_scores_count_harm_both_ways():
    s = A.scores(_row("x", "wet", "on", "water"))
    assert s == {"correct": 0.0, "treat": 0.0, "water_unwanted": 1.0, "frost_missed": 0.0}
    s = A.scores(_row("x", "frost", "on", "treat_or_remove"))
    assert s["treat"] == 1.0 and s["frost_missed"] == 1.0
    # watering is wanted in the dry spell, so it is never "unwanted" there
    assert A.scores(_row("x", "dry", "on", "water"))["water_unwanted"] == 0.0


def test_summary_pairs_arms_and_lists_items_where_the_model_arm_did_worse():
    rows = [
        _row("a", "frost", "off", "leave_normal"),
        _row("a", "frost", "on", "shelter"),
        _row("b", "wet", "off", "dont_water"),
        _row("b", "wet", "on", "water"),
        _row("c", "dry", "off", "water"),
        _row("c", "dry", "on", "water"),
        _row("d", "mild", "on", "leave_normal", status="error"),  # not scored
    ]
    s = A.summarise(rows, n=200)
    assert s["n_ok"] == 6
    assert s["arms"]["off"]["correct"]["value"] == pytest.approx(2 / 3)
    assert s["arms"]["on"]["correct"]["value"] == pytest.approx(2 / 3)
    assert s["diff"]["correct"]["value"] == pytest.approx(0.0)
    # the dry pair is out: watering is wanted there
    assert s["diff"]["water_unwanted"]["value"] == pytest.approx(1 / 2)
    assert s["on_worse"] == ["b"] and s["on_better"] == ["a"]
    assert s["by_scenario"]["frost"] == {"off": 0.0, "on": 1.0}


def test_repeats_of_one_item_stay_together_in_the_interval():
    rows = [_row("a", "dry", arm, "water", repeat=r) for arm in A.ARMS for r in (0, 1)]
    rows += [_row("b", "dry", arm, "leave_normal", repeat=r) for arm in A.ARMS for r in (0, 1)]
    ci = A.summarise(rows, n=300)["arms"]["on"]["correct"]
    # two items, so the resampled share can only be 0, 0.5 or 1
    assert ci["value"] == 0.5 and ci["lo"] in (0.0, 0.5) and ci["hi"] in (0.5, 1.0)


def test_the_arms_differ_only_in_the_plant_model_block(tmp_path):
    for item in A.items()[::7]:
        p = A.prompts(item, A.pack_for(item, tmp_path))
        changed = [
            line
            for line in difflib.unified_diff(
                p["off"].context.splitlines(), p["on"].context.splitlines(), lineterm="", n=0
            )
            if line[:1] in "+-" and not line.startswith(("+++", "---"))
        ]
        assert changed[0] == "-not available"
        assert all(line.startswith("+") for line in changed[1:])
        assert p["off"].note == p["on"].note and p["off"].soil_known == p["on"].soil_known


@pytest.mark.parametrize(
    ("scenario", "advised"),
    [("frost", "shelter: better"), ("dry", "water: better"), ("wet", "water: worse")],
)
def test_the_plant_model_points_the_way_the_rule_does(tmp_path, scenario, advised):
    # the scenarios are only fair if the model's own verdict agrees with the rule
    for item in [i for i in A.items() if i.scenario == scenario]:
        on = A.prompts(item, A.pack_for(item, tmp_path))["on"].context
        assert advised in on, item.id


def _script():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "eval_plant_model", Path(__file__).parents[1] / "scripts" / "eval_plant_model.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_run_is_paid_so_it_quotes_and_waits_for_yes(capsys, tmp_path):
    mod = _script()
    where = ["--eval-dir", str(tmp_path), "--cache-dir", str(tmp_path / "packs")]
    assert mod.main(["--dry-run", *where]) == 0
    assert "240 panels, 240 not yet answered" in capsys.readouterr().out
    assert mod.main(where) == 2  # no --yes-paid: no settings loaded, no call made


def test_a_budget_below_the_quote_does_not_start(capsys, tmp_path):
    where = ["--eval-dir", str(tmp_path), "--cache-dir", str(tmp_path / "packs")]
    assert _script().main(["--yes-paid", "--budget", "0.1", *where]) == 2
    assert "above the budget" in capsys.readouterr().out


def test_a_resume_is_quoted_only_on_the_panels_not_yet_answered(capsys, tmp_path):
    import json

    mod = _script()
    item = A.items()[0]
    runs = tmp_path / "runs"
    runs.mkdir()
    row = {"key": "k", "id": item.id, "arm": "on", "repeat": 0, "status": "ok"}
    (runs / "r.jsonl").write_text(json.dumps(row) + "\n")
    where = ["--eval-dir", str(tmp_path), "--cache-dir", str(tmp_path / "packs")]
    assert mod.main(["--dry-run", "--run-id", "r", *where]) == 0
    assert "239 not yet answered" in capsys.readouterr().out


def test_the_spend_guard_refuses_once_the_budget_is_reached():
    from herbtwin.adapters.base import CallRecord

    spend = _script().Spend(0.01)
    assert spend.allow()
    spend(CallRecord("m", "advise", "", "", 1, 1, 1, 0.01, False))
    assert not spend.allow() and spend.stopped


def test_harm_rates_count_only_the_scenarios_they_can_happen_in():
    rows = [
        _row("a", "frost", "on", "leave_normal"),
        _row("b", "dry", "on", "water"),
        _row("c", "mild", "on", "leave_normal"),
        _row("d", "wet", "on", "water"),
    ]
    arm = A.summarise(rows, n=100)["arms"]["on"]
    assert arm["frost_missed"]["value"] == 1.0 and arm["frost_missed"]["n"] == 1
    assert arm["water_unwanted"]["value"] == pytest.approx(1 / 3)
    assert arm["water_unwanted"]["n"] == 3  # the dry spell, where water is wanted, is out
