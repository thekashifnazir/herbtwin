import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_rhs_month_picks import names_of, picks_in  # noqa: E402
from eval_grow import run  # noqa: E402


def test_names_cover_plurals_and_ids():
    assert {"broad bean", "broad beans"} <= names_of("broad_bean", "Broad bean")
    assert "potatoes" in names_of("potato_first_early", "Potato")
    assert "spring cabbage" in names_of("cabbage_spring", "Spring cabbage / spring greens")


def test_only_sentences_that_say_sow_or_plant_count():
    crops = [
        ("garlic", {"garlic"}),
        ("broad_bean", {"broad bean", "broad beans"}),
        ("mint", {"mint"}),
    ]
    text = "Plant garlic cloves now. Pick the last mint leaves. Sow broad beans in mild areas."
    assert picks_in(text, crops) == ["garlic", "broad_bean"]


def test_eval_run_scores_every_month_and_setting():
    labels = {"months": {str(m): {"picks": ["garlic"] if m == 10 else []} for m in range(1, 13)}}
    result = run(labels)
    assert len(result["rows"]) == 48 and result["hard_errors"] == []
    assert result["wanted"] == 3  # garlic needs full sun: not the part-shade setting
