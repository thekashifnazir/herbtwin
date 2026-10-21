import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "esa", Path(__file__).parents[1] / "scripts" / "eval_seasonal_advice.py"
)
esa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(esa)


def _row(verdict, primary, uk=True, norm_key="mentha"):
    return {
        "status": "ok",
        "label": {"verdict": verdict, "uk": uk, "norm_key": norm_key},
        "primary": primary,
    }


def test_normal_means_leave_it_and_no_norm_is_scored_apart():
    rows = [
        _row("normal", "leave_normal"),
        _row("problem", "treat_or_remove"),
        _row("problem", "leave_normal"),
        _row("normal", "prune", norm_key=None),
    ]
    s = esa.score_rows(rows)
    assert s["n"] == 3 and s["accuracy"] == 2 / 3
    assert s["no_norm_n"] == 1 and s["no_norm_accuracy"] == 0.0


def test_question_names_the_month():
    assert "taken in October" in esa.question(10)
