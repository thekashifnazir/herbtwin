import pytest

from herbtwin.consequences import NO_DATA, consequence_for, named_problem
from herbtwin.outcomes import load_outcomes
from herbtwin.plant_model import ModelView

VIEWS = {"water": ModelView("water", "worse", "stays moist without watering", None)}


def test_plant_model_actions_use_the_view():
    c = consequence_for("water", plant_key="mentha", month=10, answer="", views=VIEWS)
    assert (c.text, c.source, c.less_sure) == ("stays moist without watering", "plant_model", False)


def test_prune_uses_the_table_row_and_is_less_sure():
    row = next(r for r in load_outcomes() if r.action == "prune")
    c = consequence_for("prune", plant_key=row.plant, month=row.months[0], answer="", views={})
    assert c.text == row.if_you_do and c.source == "outcome_table" and c.less_sure


def test_treat_needs_a_named_problem_from_the_plants_list():
    row = next(r for r in load_outcomes() if r.action == "treat_or_remove")
    named = f"This looks like {row.problem}. Remove affected stems."
    c = consequence_for(
        "treat_or_remove", plant_key=row.plant, month=row.months[0], answer=named, views={}
    )
    assert c.text == row.if_you_do
    vague = consequence_for(
        "treat_or_remove",
        plant_key=row.plant,
        month=row.months[0],
        answer="Spray it with something.",
        views={},
    )
    assert vague.text == NO_DATA and vague.source == "none"


def test_named_problem_is_whole_phrase_only():
    assert named_problem("mint rust on the leaves", ["mint rust", "rust"]) == "mint rust"
    assert named_problem("trustworthy advice", ["rust"]) is None


def test_feed_off_season_says_when_it_is_best_done():
    rows = [r for r in load_outcomes() if r.action == "feed"]
    plant = rows[0].plant
    months = {m for r in rows if r.plant == plant for m in r.months}
    off = next(m for m in range(1, 13) if m not in months)
    c = consequence_for(
        "other", plant_key=plant, month=off, answer="Feed it with a liquid feed.", views={}
    )
    assert c.text.startswith("best done in ") and c.source == "outcome_table"


def test_unknown_plant_or_action_has_no_data():
    assert consequence_for("prune", plant_key=None, month=10, answer="", views={}).text == NO_DATA
    other = consequence_for("other", plant_key="mentha", month=10, answer="Say hello.", views={})
    assert other.text == NO_DATA


def test_feed_is_its_own_action_now():
    r = next(r for r in load_outcomes() if r.action == "feed")
    c = consequence_for("feed", plant_key=r.plant, month=r.months[0], answer="", views={})
    assert c.source == "outcome_table" and c.text == r.if_you_do


def test_a_new_action_without_a_row_says_no_data():
    c = consequence_for("rotate", plant_key="rosa", month=1, answer="", views={})
    assert c.text == NO_DATA and c.source == "none"


@pytest.mark.parametrize(
    ("action", "plant", "month"),
    [("check_pests", "rosa", 10), ("humidity", "phalaenopsis", 1), ("rotate", "rosa", 1)],
)
def test_non_seasonal_actions_never_say_best_done_later(action, plant, month):
    c = consequence_for(action, plant_key=plant, month=month, answer="", views={})
    assert not c.text.startswith("best done in")


@pytest.mark.parametrize(
    ("answer", "want"),
    [
        ("This looks like downy mildew. Remove the affected leaves.", "basil downy mildew"),
        ("The grey fuzz under the leaves is downy mildew.", "basil downy mildew"),
        ("Basil downy mildew: remove the plant.", "basil downy mildew"),
        ("Some powdery mildew on the leaves.", "powdery mildew"),  # its own listed name
        ("A fungal infection on the leaves.", None),
    ],
)
def test_a_plants_own_name_is_optional_in_its_problem(answer, want):
    # panel steadiness, 21 Oct: one of 5 repeats said plain "downy mildew", found no row, and
    # headlined "Treat it." over a disease with no cure
    from herbtwin.outcomes import problems_for

    assert named_problem(answer, problems_for("ocimum basilicum"), "ocimum basilicum") == want


def test_only_a_two_word_problem_drops_the_plants_name():
    # "rust" alone, or "beetle" alone, could be anything: the full name is still needed
    from herbtwin.outcomes import problems_for

    assert (
        named_problem("Rust on the leaves.", problems_for("mentha spicata"), "mentha spicata")
        is None
    )
    rosemary = problems_for("salvia rosmarinus")
    assert named_problem("A beetle on it.", rosemary, "salvia rosmarinus") is None


def test_a_no_cure_problem_named_without_the_plant_heads_the_answer_as_no_cure():
    c = consequence_for(
        "treat_or_remove", plant_key="ocimum basilicum", month=10,
        answer="This looks like downy mildew. Remove the affected leaves.", views={},
    )  # fmt: skip
    assert c.source == "outcome_table" and "no" in c.text.lower() and "cure" in c.text.lower()
