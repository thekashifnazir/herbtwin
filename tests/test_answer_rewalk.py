"""17 Oct live re-walk: the watch line repeated the problem the photo check had just
named (sample 6, basil downy mildew)."""

from herbtwin.schemas import ProblemSeen
from herbtwin.seasonal import normal_for
from tests.test_answer import build

BASIL = "ocimum basilicum"


from herbtwin.answer import watch_list  # noqa: E402
from tests.test_answer import VIEWS  # noqa: E402


def test_the_watch_line_is_the_named_problems_spread_not_its_signs():
    # 17 Oct walk: the named problem's own signs again read as a repeat; judge walk of
    # c485f29: the month's other signs alone (root rot on a rosemary beetle) missed it.
    # The problem first, then one other sign worth knowing
    seen = ProblemSeen(name="basil downy mildew", looks_like="grey fuzz", source="https://x")
    a = build(norm=normal_for(BASIL, 10), plant_key=BASIL, problem=seen, setting="outdoor")
    signs, after = watch_list(a.watch)
    assert signs[0] == "Basil downy mildew on new leaves or the plants beside it"
    assert after == (
        "Seen either? Send a new photo." if len(signs) == 2 else "Seen it? Send a new photo."
    )
    assert "grey-purple fuzz" not in a.watch and "indoor" not in a.watch
    # where the month has another sign, it follows the problem's own line
    b = build(norm=normal_for(BASIL, 10), plant_key=BASIL, problem=seen)
    assert watch_list(b.watch)[0][1:], b.watch


def test_a_problem_that_does_not_spread_says_where_to_look():
    # polish review: "Root rot on new leaves" read wrong
    seen = ProblemSeen(name="root rot", looks_like="soft roots", source="https://x")
    a = build(norm=None, plant_key=None, problem=seen)
    assert a.watch == (
        "• Root rot: more wilting, or soft dark stems at the base. Seen it? Send a new photo."
    )


def test_a_named_problem_keeps_the_cold_night_warning():
    # polish review: the named problem used to push the twin's frost sign out
    from herbtwin.plant_model import ModelView

    cold = ModelView("shelter", "better", "cold risk Sunday if left out", 4, True, "Sunday")
    seen = ProblemSeen(name="aphids", looks_like="green flies", source="https://x")
    a = build(norm=None, plant_key=None, problem=seen, views={**VIEWS, "shelter": cold})
    signs, _ = watch_list(a.watch)
    assert signs[0].startswith("Aphids on new leaves") and "cold night" in signs[1]


def test_without_a_named_problem_the_watch_line_still_names_it():
    a = build(norm=normal_for(BASIL, 10), plant_key=BASIL)
    assert "grey-purple fuzz" in a.watch


def test_a_named_problem_with_no_season_signs_is_still_watched():
    seen = ProblemSeen(name="rosemary beetle", looks_like="metallic beetles", source="https://x")
    a = build(norm=None, plant_key=None, problem=seen)
    assert a.watch.startswith("• Rosemary beetle on new leaves or the plants beside it.")


def test_message_pages_head_only_where_a_heading_fits():
    from herbtwin.web.app import TEMPLATES

    t = TEMPLATES.get_template("message.html")
    still = t.render(message="Still reading your photo, this page refreshes.", refresh=3,
                     heading="One moment")  # fmt: skip
    assert "<h1>One moment</h1>" in still and 'http-equiv="refresh" content="3"' in still
    plain = t.render(message="Check your email for a sign-in link.")
    assert plain.count("<h1") == 1 and "<h1>Check your email for a sign-in link.</h1>" in plain
    assert "<title>Check your email for a sign-in link. · herbtwin</title>" in plain
