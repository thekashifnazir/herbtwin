"""How we worked it out, and Compare (23 Oct answer-page critique, parts 9 and 10, Kash:
"sounds great"): the advisors as a vote of chips with the call our rules chose in amber, how
our rule led said once, the model steps as a flow strip coloured as About's legend, and
Compare under a head in the twin's deep green."""

import html
import re
from pathlib import Path

from herbtwin import receipt
from herbtwin.answer import RULES_CHOSE, advisor_lines
from herbtwin.confidence import RULE_LED
from herbtwin.schemas import Factor, StepCost
from herbtwin.web import style
from tests.test_answer_advisor_lines import LABEL, _rec, _run
from tests.test_web_answer_page import _render
from tests.test_web_answer_reveal import _rules

SHEET = Path(__file__).parents[1] / "src/herbtwin/web/static/pages/answer_workings.css"
LED = "The advisors led with cutting it back; the soil is dry, so watering comes first."


def _sheet() -> dict[str, str]:
    return {s: b for at, s, b in _rules(SHEET.read_text("utf-8")) if not at}


def _ruled(tmp_path):
    rec = _rec(tmp_path, _run("leave_normal"), _run("prune"), _run("prune"))
    rec.answer.factors = [
        *rec.answer.factors,
        Factor(name="advisor", effect="lowers", detail=RULE_LED),
    ]
    return rec


def _said(page: str) -> str:
    return html.unescape(page).split('<div class="advisor-said">', 1)[1].split("</div>", 1)[0]


# ---------- 9. the vote ----------


def test_each_advisor_is_a_chip_in_the_order_they_answered(tmp_path):
    rec = _rec(tmp_path, _run("prune"), _run("prune"), _run("prune"))
    got = advisor_lines(rec, LABEL)
    assert got.calls == ("Cut it back", "Cut it back", "Cut it back") and got.chose == ""
    said = _said(_render(rec))
    chips = re.findall(r'<li class="vote-chip">(.*?)</li>', said)
    assert chips == [f'<span class="sr-only">Advisor {i}: </span>Cut it back' for i in (1, 2, 3)]
    assert "vote-chose" not in said  # the advisors chose it: no rule to name


def test_when_our_rule_led_the_vote_ends_with_its_call_in_amber(tmp_path):
    rec = _ruled(tmp_path)
    first = LABEL[rec.answer.do[0].action]
    assert advisor_lines(rec, LABEL).chose == first
    said = _said(_render(rec))
    assert f'<li class="vote-chose">Our rules chose: <strong>{first}</strong></li>' in said
    chose = _sheet()[".answer-page .advisor-said .vote-chose"]
    assert "background: var(--warn-bg)" in chose and "color: var(--warn)" in chose


def test_how_our_rule_led_is_said_once(tmp_path):
    # it was said twice: "Our rules then chose the plan at the top" and the how-led line
    rec = _ruled(tmp_path)
    rec.notes = [*rec.notes, LED]
    page = html.unescape(_render(rec))
    said = _said(_render(rec))
    assert f'<p class="note how-led">{LED}</p>' in said and page.count(LED) == 1
    assert RULES_CHOSE not in page
    # with no line of how, the note still says it
    rec.notes = [n for n in rec.notes if n != LED]
    assert RULES_CHOSE in html.unescape(_render(rec))


def test_a_failed_ask_is_still_said_when_the_rule_line_takes_the_note(tmp_path):
    rec = _ruled(tmp_path)
    rec.answer.runs = rec.answer.runs[:2]
    assert advisor_lines(rec, LABEL, led=True).note == "One ask failed, so two answered."


def test_with_no_advisor_lines_the_how_led_line_still_shows_once(tmp_path):
    # review: an older answer has no stored replies, so no vote; the rule's line stays
    rec = _ruled(tmp_path)
    rec.answer.runs = []
    rec.notes = [*rec.notes, LED]
    page = html.unescape(_render(rec))
    assert '<div class="advisor-said">' not in page
    assert page.count(f'<p class="note how-led">{LED}</p>') == 1


def test_an_override_names_its_call_and_its_line_is_not_said_twice(tmp_path):
    # review: the no-cure and twin overrides take the same path as a rule that led
    rec = _rec(tmp_path, _run("treat_or_remove"), _run("treat_or_remove"), _run("treat_or_remove"))
    rec.answer.held_water = True
    got = advisor_lines(rec, LABEL)
    assert got.chose == LABEL[rec.answer.do[0].action] and got.note.startswith("Your plant's twin")
    assert advisor_lines(rec, LABEL, led=True).note == ""


# ---------- 9. the model steps ----------


def test_each_map_row_knows_its_step(tmp_path):
    rec = _rec(tmp_path, _run("water"))
    rec.receipt = [
        StepCost(stage="observe", model="zai-org/GLM-5.3-Flash", ms=4200, cost_usd=0.0009),
        StepCost(stage="weather", model="Open-Meteo", ms=300),
        StepCost(stage="twin", model="Our plant twin", ms=60),
        StepCost(stage="advise", model="nvidia/nemotron-3-super-120b-a12b", ms=9800, cost_usd=0.004),
    ]  # fmt: skip
    assert [r.stage for r in receipt.model_map(rec).rows] == [
        "observe",
        "weather",
        "twin",
        "advise",
    ]
    strip = _render(rec).split('<ol class="mm-flow">', 1)[1].split("</ol>", 1)[0]
    kinds = re.findall(r'<li class="mm-step([^"]*)">', strip)
    assert kinds == ["", " weather", " twin", " nvidia"]
    assert '<span class="mm-cost">4.2 s · $0.0009</span>' in strip  # time and cost on each


def test_the_strip_runs_down_with_an_arrow_and_the_legend_colours():
    rules = _sheet()
    assert "flex-direction: column" in rules[".answer-page .model-map .mm-flow"]
    arrow = rules[".answer-page .model-map .mm-step + .mm-step::before"]
    assert 'content: "\\2193" / ""' in arrow  # decoration: a screen reader hears the list
    twin = rules[".answer-page .model-map .mm-step.twin"]
    assert "background: var(--band)" in twin and "color: var(--band-fg)" in twin
    assert "background: var(--sky)" in rules[".answer-page .model-map .mm-step.weather"]
    assert "background: var(--soft)" in rules[".answer-page .model-map .mm-step.nvidia"]


# ---------- 10. Compare ----------


def test_compare_has_the_twins_deep_green_head():
    head = _sheet()[
        ".answer-page details.compare.fold-twin > summary, "
        ".answer-page details.compare.fold-twin > summary:hover"
    ]
    assert "background: var(--band)" in head and "color: var(--band-fg)" in head


def test_answer_workings_css_is_inlined_scoped_and_uses_tokens_only():
    sheet = SHEET.read_text("utf-8")
    assert style._minify(sheet) in style.CSS  # inlined by style.py, no <link>
    for _, sel, body in _rules(sheet):
        for part in re.split(r",(?![^()]*\))", sel):  # not the commas inside :is()
            assert part.strip().startswith(".answer-page"), sel
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", body), sel
        sizes = [int(px) for px in re.findall(r"(\d+)px/", body)]
        assert all(s >= 16 for s in sizes), sel
