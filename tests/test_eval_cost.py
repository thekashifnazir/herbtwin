import json

from herbtwin.evals.cost import estimate_cost, measured_cost_per_image


def _write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_measured_cost_is_the_mean_over_paid_observe_rows_of_that_model(tmp_path):
    _write(
        tmp_path / "a.jsonl",
        [
            {"model": "glm", "status": "ok", "cost_usd": 0.001, "calls": 1},
            {"model": "glm", "status": "failed", "cost_usd": 0.003, "calls": 2},
            {"model": "qwen", "status": "ok", "cost_usd": 0.0, "calls": 1},
        ],
    )
    _write(tmp_path / "b.jsonl", [{"model": "glm", "status": "ok", "cost_usd": 0.002, "calls": 1}])
    (tmp_path / "broken.jsonl").write_text("not json\n")
    assert abs(measured_cost_per_image(tmp_path, "glm") - 0.002) < 1e-12
    assert measured_cost_per_image(tmp_path, "nothing") is None
    assert measured_cost_per_image(tmp_path / "absent", "glm") is None


def test_estimate_cost_uses_the_price_table_and_knows_when_it_cannot():
    assert estimate_cost("zai-org/GLM-5.3-Flash", 0) == 0.0
    assert estimate_cost("zai-org/GLM-5.3-Flash", 100) > 0
    assert estimate_cost("no/such-model", 100) is None


def test_measured_cost_per_question_uses_advice_rows_of_that_advisor(tmp_path):
    from herbtwin.evals.cost import measured_cost_per_question

    _write(
        tmp_path / "a.jsonl",
        [
            {"model": "super", "advise_calls": 1, "advise_cost_usd": 0.001},
            {"model": "super+fewshot6", "advise_calls": 2, "advise_cost_usd": 0.003},
            {"model": "super-duper", "advise_calls": 1, "advise_cost_usd": 9.0},
            {"model": "super", "status": "missing"},
            {"model": "super", "advise_calls": 1, "advise_cost_usd": 0.0},  # free replay
        ],
    )
    assert abs(measured_cost_per_question(tmp_path, "super") - 0.002) < 1e-12
    assert measured_cost_per_question(tmp_path, "other") is None


def test_a_panel_row_counts_per_ask(tmp_path):
    import json

    from herbtwin.evals.cost import measured_cost_per_question

    panel = {"model": "super", "advise_calls": 3, "advise_cost_usd": 0.003, "runs": [{}, {}, {}]}
    single = {"model": "super", "advise_calls": 1, "advise_cost_usd": 0.001}
    (tmp_path / "r.jsonl").write_text(json.dumps(panel) + "\n" + json.dumps(single) + "\n")
    assert abs(measured_cost_per_question(tmp_path, "super") - 0.001) < 1e-12
