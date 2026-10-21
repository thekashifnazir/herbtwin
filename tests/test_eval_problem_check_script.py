import importlib.util
from pathlib import Path


def _script():
    spec = importlib.util.spec_from_file_location(
        "eval_problem_check", Path(__file__).parents[1] / "scripts" / "eval_problem_check.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_each_class_reports_the_photos_whose_plant_the_app_knows_apart():
    # 17 Oct: 0/24 powdery mildew and 0/24 slugs, but 5 mildew photos were chervil or
    # hogweed and every slug photo showed no plant: out of scope for a herb app
    res = [
        ("powdery_mildew_herbs", "powdery mildew", "powdery mildew", "white coating", None, True),
        ("powdery_mildew_herbs", "powdery mildew", None, "white coating", None, True),
        ("powdery_mildew_herbs", "powdery mildew", None, "white coating", None, False),
        ("slugs_snails", "slugs and snails", None, "", None, False),
        ("healthy", None, None, "", None, True),
        ("judge:1-parsley-healthy.jpg", None, None, "", None, True),
    ]
    classes, wrong, judges = _script().tally(res)
    pm = classes["powdery_mildew_herbs"]
    assert (pm["n"], pm["right"], pm["none"]) == (3, 1, 2)
    assert pm["in_scope"] == {"n": 2, "right": 1, "none": 1}
    assert classes["slugs_snails"]["in_scope"] == {"n": 0}
    assert classes["judges"]["n"] == 1 and "1-parsley-healthy.jpg" in judges
    assert wrong == {}


def test_a_wrong_name_is_counted_and_listed():
    res = [("mint_rust", "mint rust", "aphids", "spots", None, True)]
    classes, wrong, _ = _script().tally(res)
    assert classes["mint_rust"]["wrong"] == 1 and classes["mint_rust"]["in_scope"]["wrong"] == 1
    assert wrong == {"mint_rust": {"aphids": 1}}
