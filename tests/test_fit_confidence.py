import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "fit_confidence", Path(__file__).parents[1] / "scripts" / "fit_confidence.py"
)
fc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fc)


def _row(rid, primary, conf, agree, repaired=False):
    return {
        "status": "ok",
        "id": rid,
        "advice": {"primary": primary, "confidence": conf},
        "agree": agree,
        "total": 3,
        "advisor": conf,
        "repaired": repaired,
    }


def test_auroc_perfect_and_coin():
    assert fc.auroc([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0]) == 1.0
    assert fc.auroc([0.5, 0.5, 0.5, 0.5], [1, 0, 1, 0]) == 0.5


def test_features():
    assert fc.features(_row("x", "water", "low", 1, True)) == {
        "advisor_high": 0.0,
        "advisor_low": 1.0,
        "agree3": 0.0,
        "agree1": 1.0,
        "repaired": 1.0,
    }


def test_fit_learns_that_agreement_predicts_rightness():
    rows, truth = [], {}
    for k in range(40):
        rows.append(_row(f"g{k}", "water", "high", 3))
        truth[f"g{k}"] = "water"
        rows.append(_row(f"b{k}", "water", "high", 1))
        truth[f"b{k}"] = "prune"
    w = fc.fit(rows, truth)
    assert w["factors"]["agreement"]["raises"] > 0 > w["factors"]["agreement"]["lowers"]


def test_levels_are_measured_on_their_own_score_band():
    levels = [
        {"level": "not_sure", "below": -0.4, "in_ten": 3, "n": 0},
        {"level": "fairly_sure", "below": 0.2, "in_ten": 4, "n": 0},
        {"level": "sure", "below": None, "in_ten": 6, "n": 0},
    ]
    held = [(-1.0, 0), (-1.0, 0), (0.0, 1), (0.0, 0), (1.0, 1)]
    out = fc.measure_levels(levels, held)
    assert [(lv["n"], lv["in_ten"]) for lv in out] == [(2, 1), (2, 5), (1, 10)]


def test_fit_and_score_use_coarse_classes():
    rows = [_row(f"r{k}", "feed", "high", 3) for k in range(10)]
    truth = {f"r{k}": "other" for k in range(10)}
    fitted = fc.fit(rows, truth)
    assert "other" in fitted["base"] and "feed" not in fitted["base"]
    assert fitted["base"]["other"] > fitted["base"]["default"]  # all ten were right
    as_other = {**rows[0], "advice": {"primary": "other", "confidence": "high"}}
    assert fc.score(rows[0], fitted) == fc.score(as_other, fitted)
