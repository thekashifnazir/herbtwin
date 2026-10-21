import pytest

from herbtwin.evals.items import EvalItem
from herbtwin.evals.metrics import quadratic_weighted_kappa
from herbtwin.evals.report import render_markdown, species_keys, summarise


def _item(i, set_name, label, cluster="p", tag="safe-to-train"):
    return EvalItem(
        id=f"{set_name}/{i}",
        set=set_name,
        path=f"x/{i}.jpg",
        root="external",
        label=label,
        cluster=cluster,
        licence="CC BY 4.0",
        tag=tag,
        source="t",
    )


def _ok(i, **obs):
    base = {
        "water_stress": 0,
        "decline": 0,
        "leaf_colour": "green",
        "species": [],
        "is_plant": True,
    }
    return {"id": i, "status": "ok", "observation": {**base, **obs}, "latency_ms": 10}


def test_droop_summary_matches_hand_computed_kappa_and_counts():
    truth = [0, 1, 2, 3, 1, 2]
    pred = [0, 2, 2, 1, 1, 3]
    items = [
        _item(n, "droop_soybean", {"droop": t}, cluster=f"p{n % 3}") for n, t in enumerate(truth)
    ]
    rows = [_ok(i.id, water_stress=p) for i, p in zip(items, pred, strict=True)]
    items.append(_item(99, "droop_soybean", {"droop": 0}))
    rows.append({"id": items[-1].id, "status": "missing"})
    s = summarise(items, rows, {"run_id": "r"})
    assert s["n_total"] == 7 and s["n_ok"] == 6 and s["n_missing"] == 1
    assert s["metrics"]["qwk"]["value"] == pytest.approx(quadratic_weighted_kappa(truth, pred, 4))
    assert s["metrics"]["exact"]["value"] == pytest.approx(3 / 6)
    assert s["pred_histogram"] == {0: 1, 1: 2, 2: 2, 3: 1}
    assert s["largest_disagreements"][0] == items[3].id  # truth 3, predicted 1
    assert "qwk" in render_markdown(s)


def test_decline_summary_is_binary_on_decline_at_least_one():
    labels = [True, True, False, False]
    preds = [2, 0, 0, 1]
    items = [_item(n, "decline_indoor", {"decline": t}, cluster=None) for n, t in enumerate(labels)]
    rows = [_ok(i.id, decline=p) for i, p in zip(items, preds, strict=True)]
    s = summarise(items, rows, {"run_id": "r"})
    assert s["metrics"]["recall"]["value"] == pytest.approx(0.5)
    assert s["metrics"]["specificity"]["value"] == pytest.approx(0.5)


def test_recovery_reports_spearman_per_clip_without_ci():
    items = [_item(n, "droop_recovery", {"t": n}, cluster="fittonia") for n in range(4)]
    rows = [_ok(i.id, water_stress=w) for i, w in zip(items, [3, 2, 1, 0], strict=True)]
    s = summarise(items, rows, {"run_id": "r"})
    m = s["metrics"]["spearman_fittonia"]
    assert m["value"] == pytest.approx(-1.0) and m["lo"] is None


def test_species_keys_handle_both_bracket_orders_and_synonyms():
    assert "salvia officinalis" in species_keys("Common sage (Salvia officinalis)")
    assert "dryopteris filix-mas" in species_keys("Dryopteris filix-mas (male fern)")
    assert "salvia rosmarinus" in species_keys("Rosmarinus officinalis L.")


def test_species_summary_scores_top1_top3_and_genus():
    items = [
        _item(0, "species_gbif", {"species": "Salvia officinalis"}),
        _item(1, "species_gbif", {"species": "Thymus vulgaris"}),
    ]
    rows = [
        _ok(items[0].id, species=[{"name": "Salvia officinalis"}]),
        _ok(items[1].id, species=[{"name": "Thymus serpyllum"}, {"name": "Thymus vulgaris"}]),
    ]
    s = summarise(items, rows, {"run_id": "r"})
    assert s["metrics"]["top1"]["value"] == pytest.approx(0.5)
    assert s["metrics"]["top3"]["value"] == pytest.approx(1.0)
    assert s["metrics"]["genus_top1"]["value"] == pytest.approx(1.0)


def test_garden_compares_condition_with_the_worse_of_droop_and_decline():
    items = [_item(n, "garden_v1", {"condition": c}, tag="owner") for n, c in enumerate([2, 0])]
    rows = [_ok(items[0].id, water_stress=0, decline=2), _ok(items[1].id)]
    s = summarise(items, rows, {"run_id": "r"})
    assert s["metrics"]["exact"]["value"] == pytest.approx(1.0)
    assert s["tags"] == {"owner": 2}


def test_failed_rows_are_counted_not_scored():
    items = [_item(0, "droop_soybean", {"droop": 1}), _item(1, "droop_soybean", {"droop": 2})]
    rows = [_ok(items[0].id, water_stress=1), {"id": items[1].id, "status": "failed"}]
    s = summarise(items, rows, {"run_id": "r"})
    assert s["n_failed"] == 1 and s["failed_ids"] == [items[1].id]


@pytest.mark.parametrize(
    "answer, wrong",
    [
        ("Mentha x piperita", "mentha spicata"),
        ("Peppermint", "mentha spicata"),
        ("Basil (Ocimum tenuiflorum)", "ocimum basilicum"),
        ("Thyme (Thymus serpyllum)", "thymus vulgaris"),
        ("Oregano (Origanum majorana)", "origanum vulgare"),
        ("Sage (Salvia nemorosa)", "salvia officinalis"),
    ],
)
def test_look_alike_species_do_not_count_as_the_garden_herb(answer, wrong):
    assert wrong not in species_keys(answer)


def test_common_names_resolve_only_without_a_scientific_name():
    assert species_keys("Common sage") == {"salvia officinalis"}
    assert species_keys("rosemary") == {"salvia rosmarinus"}


def test_not_a_plant_answers_are_counted():
    items = [_item(0, "droop_soybean", {"droop": 1}), _item(1, "droop_soybean", {"droop": 0})]
    rows = [_ok(items[0].id, is_plant=False), _ok(items[1].id, is_plant=True)]
    s = summarise(items, rows, {"run_id": "r"})
    assert s["n_not_plant"] == 1


def test_garden_common_names_and_wcvp_synonyms_resolve():
    assert species_keys("Japanese maple") == {"acer palmatum"}
    assert species_keys("Male fern") == {"dryopteris filix-mas"}
    assert species_keys("Chives") == {"allium schoenoprasum"}
    assert species_keys("Polystichum angulare") == {"polystichum setiferum"}  # WCVP synonym


def test_report_flags_intervals_resting_on_few_draws():
    from herbtwin.evals.report import render_markdown

    s = {
        "set": "x",
        "n_total": 1,
        "n_ok": 1,
        "n_missing": 0,
        "n_failed": 0,
        "n_error": 0,
        "n_not_plant": 0,
        "tags": {},
        "cost_usd": 0,
        "mean_latency_ms": 1,
        "metrics": {"qwk": {"value": 0.1, "lo": 0.0, "hi": 0.2, "skipped": 1500}},
    }
    assert "**Warning:** qwk" in render_markdown(s)


def test_multi_word_common_names_match_on_the_whole_phrase():
    assert species_keys("Soft shield fern") == {"polystichum setiferum"}
    assert species_keys("Soft shield fern (Polystichum setiferum)") == {"polystichum setiferum"}
    assert species_keys("Allium montanum") == {"allium montanum"}  # ambiguous homonym: no credit


def test_report_says_when_every_item_got_the_same_score():
    items = [
        _item(n, "droop_soybean", {"droop": t}, cluster=f"p{n % 3}")
        for n, t in enumerate([0, 1, 2, 3, 1, 2])
    ]
    rows = [_ok(i.id, water_stress=0) for i in items]
    s = summarise(items, rows, {"run_id": "r"})
    assert s["constant_prediction"] == 0
    assert "gave every scored item the same score (0)" in render_markdown(s)


def test_varied_predictions_carry_no_constant_warning():
    items = [_item(n, "droop_soybean", {"droop": n % 2}) for n in range(4)]
    rows = [_ok(i.id, water_stress=n % 2) for n, i in enumerate(items)]
    s = summarise(items, rows, {"run_id": "r"})
    assert s["constant_prediction"] is None and "same score" not in render_markdown(s)


def test_a_run_with_nothing_scored_still_renders():
    items = [_item(0, "droop_soybean", {"droop": 1})]
    s = summarise(items, [{"id": items[0].id, "status": "failed"}], {"run_id": "r"})
    md = render_markdown(s)
    assert "0 scored" in md and "same score" not in md


def test_singular_and_common_name_answers_resolve():
    from herbtwin.evals.report import candidate_keys

    assert species_keys("Garlic Chive") == {"allium tuberosum"}
    assert species_keys("Chive") == {"allium schoenoprasum"}
    # name holds a common name, common_name holds the binomial
    assert candidate_keys({"name": "Garlic Chive", "common_name": "Allium tuberosum"}) == {
        "allium tuberosum"
    }
    # a bare "Mint" names no species; a common name in common_name never rescues it
    assert candidate_keys({"name": "Mint", "common_name": "Spearmint"}) == set()
    # a scientific name in name wins; a common_name cannot rescue a look-alike
    assert candidate_keys({"name": "Thymus serpyllum", "common_name": "Thyme"}) == {
        "thymus serpyllum"
    }
    # lower-case scientific names still count as scientific
    assert species_keys("ocimum basilicum L.") == {"ocimum basilicum"}


@pytest.mark.parametrize(
    "candidate, truth",
    [
        ({"name": "Marjoram", "common_name": "Oregano"}, "origanum vulgare"),
        ({"name": "Leek", "common_name": "Garlic Chives"}, "allium tuberosum"),
        ({"name": "Holy Basil", "common_name": "Basil"}, "ocimum basilicum"),
        ({"name": "Lemon Thyme", "common_name": "Thyme"}, "thymus vulgaris"),
        ({"name": "Pineapple Sage", "common_name": "Sage"}, "salvia officinalis"),
    ],
)
def test_common_name_field_cannot_credit_a_look_alike(candidate, truth):
    from herbtwin.evals.report import candidate_keys

    assert truth not in candidate_keys(candidate)


def test_correct_common_names_in_name_are_not_overridden():
    from herbtwin.evals.report import candidate_keys

    assert candidate_keys({"name": "Lemon Balm", "common_name": "Melissa"}) == {
        "melissa officinalis"
    }
    assert candidate_keys({"name": "Basil", "common_name": "Sweet basil"}) == {"ocimum basilicum"}
    assert species_keys("Sweet basil") == {"ocimum basilicum"}
    assert species_keys("Basil (Rosmarinus officinalis)") == {"salvia rosmarinus"}
