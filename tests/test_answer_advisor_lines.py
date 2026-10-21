"""What each advisor said (21 Oct, Kash on rev 00049: "still not renamed the advisors, what
does each mean?"). One model asked three times: each ask's own call, in the page's words.
The call only, never the advisor's raw words (the integrator, for FINAL: a quoted version
still let chemicals, hard cuts and other calls' commands through an Opus review)."""

import ast
import html
import re
from pathlib import Path

from herbtwin.answer import NO_CURE_HEADLINE, advisor_lines
from herbtwin.confidence import RULE_LED
from herbtwin.schemas import Advice, Factor
from herbtwin.web.answer_text import plan_text
from tests.test_web_answer_page import _full_plan, _render


def _page_labels() -> dict[str, str]:
    """result.html's own `label` dict: the calls as the page names them."""
    src = Path("src/herbtwin/web/templates/result.html").read_text()
    return ast.literal_eval(re.search(r"{% set label = ({.*?}) %}", src).group(1))


LABEL = _page_labels()


def _run(primary, answer="It looks fine."):
    return Advice(actions=[primary], primary=primary, answer=answer)


def _rec(tmp_path, *runs):
    rec = _full_plan(tmp_path)
    rec.answer.runs = list(runs)
    return rec


def _said(rec):
    got = advisor_lines(rec, LABEL)
    return [(x.who, x.action) for x in got.lines], got.note


def test_each_advisor_gets_its_own_call(tmp_path):
    rec = _rec(tmp_path, _run("prune"), _run("leave_normal"), _run("water"))
    lines, note = _said(rec)
    assert lines == [
        ("Advisor 1", "Cut it back"),
        ("Advisor 2", "Leave it"),
        ("Advisor 3", "Water it"),
    ]
    assert note == "Each said something different, so we're less sure of the plan at the top."


def test_all_three_agreeing_is_one_line(tmp_path):
    rec = _rec(tmp_path, _run("leave_normal"), _run("leave_normal"), _run("leave_normal"))
    assert _said(rec) == ([("All three", "Leave it")], "")


def test_a_majority_says_the_plan_goes_with_most(tmp_path):
    rec = _rec(tmp_path, _run("leave_normal"), _run("water"), _run("leave_normal"))
    lines, note = _said(rec)
    assert [w for w, _ in lines] == ["Advisor 1", "Advisor 2", "Advisor 3"]
    assert note == "The plan at the top goes with what most of them said."


def test_the_notes_count_the_exact_calls_not_their_classes(tmp_path):
    # feed, rotate and water are all "other" to coarse(): "most of them" said none of them
    rec = _rec(tmp_path, _run("feed"), _run("rotate"), _run("water"))
    lines, note = _said(rec)
    assert [c for _, c in lines] == ["Feed it", "Turn the pot", "Water it"]
    assert note == "Each said something different, so we're less sure of the plan at the top."
    rec.answer.runs[1] = _run("feed")
    assert _said(rec)[1] == "The plan at the top goes with what most of them said."


def test_a_resting_herbs_cut_is_a_light_tidy(tmp_path):
    rec = _rec(tmp_path, _run("prune"), _run("leave_normal"))
    rec.answer.winter_rest = rec.answer.no_cut_growth = True
    assert _said(rec)[0] == [("Advisor 1", "Give it a light tidy"), ("Advisor 2", "Leave it")]


def test_seedlings_are_thinned_never_cut_back(tmp_path):
    rec = _rec(tmp_path, _run("prune"))
    rec.answer.no_cut_growth = True  # seedlings: no cut for growth, and not a resting herb
    assert _said(rec)[0] == [("Advisor 1", "Thin them out")]


def test_a_bed_plant_is_never_told_to_keep_it_apart(tmp_path):
    rec = _rec(tmp_path, _run("isolate"), _run("treat_or_remove"))
    rec.answer.in_ground = True  # in_proportion treats it instead
    assert _said(rec)[0] == [("Both", "Treat it")]
    rec.answer.in_ground = False
    assert _said(rec)[0] == [("Advisor 1", "Keep it apart"), ("Advisor 2", "Treat it")]


def test_no_cure_names_the_call_remove_it_and_says_our_rule_chose(tmp_path):
    rec = _rec(tmp_path, *[_run("treat_or_remove")] * 3)
    rec.answer.headline = NO_CURE_HEADLINE
    assert _said(rec) == (
        [("All three", "Remove it")],
        "Our rules then chose the plan at the top, so follow that.",
    )


def test_a_rule_led_answer_says_the_plan_at_the_top_is_what_to_do(tmp_path):
    rec = _rec(tmp_path, _run("prune"), _run("prune"), _run("prune"))
    rec.answer.factors = [Factor(name="advisor", effect="lowers", detail=RULE_LED)]
    assert _said(rec) == (
        [("All three", "Cut it back")],
        "Our rules then chose the plan at the top, so follow that.",
    )


def test_a_failed_ask_leaves_fewer_lines_and_says_so(tmp_path):
    rec = _rec(tmp_path, _run("leave_normal"), _run("water"))
    lines, note = _said(rec)
    assert [w for w, _ in lines] == ["Advisor 1", "Advisor 2"]
    assert note == (
        "One ask failed, so two answered. Each said something different, so we're less sure"
        " of the plan at the top."
    )
    rec.answer.runs = [_run("leave_normal")] * 2
    assert _said(rec) == ([("Both", "Leave it")], "One ask failed, so two answered.")
    rec.answer.runs = [_run("leave_normal")]
    assert _said(rec) == ([("Advisor 1", "Leave it")], "Two asks failed, so one answered.")


def test_the_page_lists_them_under_who_advised_and_before_the_folds(tmp_path):
    rec = _rec(tmp_path, _run("prune"), _run("prune"), _run("leave_normal"))
    page = html.unescape(_render(rec, advised_by="NVIDIA Nemotron 3 Super"))
    details = page.split('<h2 id="details">How we worked it out</h2>', 1)[1]
    said = details.split('<div class="advisor-said">', 1)[1].split("</div>", 1)[0]
    assert details.index('<p class="advisors">') < details.index('<div class="advisor-said">')
    assert details.index('<div class="advisor-said">') < details.index("<details")
    assert "<h3>What each advisor said</h3>" in said
    assert "<li>Advisor 1: <strong>Cut it back.</strong></li>" in said
    assert "<li>Advisor 3: <strong>Leave it.</strong></li>" in said
    assert '<p class="note">The plan at the top goes with what most of them said.</p>' in said
    # with no stored replies (an older answer), nothing is shown
    rec.answer.runs = []
    assert '<div class="advisor-said">' not in _render(rec)


def test_no_advisor_words_ever_reach_the_block(tmp_path):
    rec = _rec(
        tmp_path,
        _run("treat_or_remove", "Scatter slug pellets round it. Cut it back hard to the base."),
        _run("prune", "Cut it back hard to the base, then spray with neem."),
        _run("leave_normal", 'Leave it. "Water it tomorrow morning."'),
    )
    page = html.unescape(_render(rec))
    said = page.split('<div class="advisor-said">', 1)[1].split("</div>", 1)[0]
    for words in ("slug pellets", "hard to the base", "neem", "tomorrow", "Scatter"):
        assert words not in page, words
    assert not re.search(r"[“”\"]", re.sub(r"<[^>]*>", "", said))  # no quote, tags aside


def test_the_rater_text_is_unchanged(tmp_path):
    rec = _rec(tmp_path, _run("prune"), _run("water"), _run("leave_normal"))
    shown = _render(rec)
    assert "Advisor 1" in shown
    text = plan_text(shown)
    assert "Advisor" not in text
    rec.answer.runs = []
    assert plan_text(_render(rec)) == text
