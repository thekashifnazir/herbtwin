"""27 Oct live walk, the coriander sample's "Leave it. This is normal for October.": the twin's
chart opened on "Water it ▼ Worse", captioned "Water it: soil stays moist enough; no frost
risk", which read as praise for a choice rated worse. On a leave-it answer that no choice
beats, the chart now opens on leaving it, the advice's own line; and each choice's line says
its verdict against leaving it wherever it is captioned."""

import re

from herbtwin.schemas import CompareRow
from herbtwin.twin_chart import chart_opens_on, twin_chart, twin_strip
from herbtwin.web import style
from tests.test_answer_twin_front import LABELS, _leave, _outdoor, _sec, _strip
from tests.test_web_answer_page import _render
from tests.test_web_answer_reveal import _rules

ANSWER_CSS = "src/herbtwin/web/static/pages/answer.css"
WORSE_WHY = "stays moist without watering; extra water isn't needed"


def _coriander(tmp_path):
    """A "Leave it" card where watering is rated worse and protecting it the same."""
    rec = _leave(_outdoor(tmp_path), "same")
    for r in rec.answer.compare:
        if r.action == "water":
            r.vs_leaving_it, r.why = "worse", WORSE_WHY
    return rec


def _pressed(sec: str) -> list[str]:
    return re.findall(r'class="twin-pick" data-line="(\w+)"[^>]*aria-pressed="true"', sec)


def test_a_leave_it_answer_nothing_beats_opens_the_chart_on_leave_it(tmp_path):
    rec = _coriander(tmp_path)
    s = twin_strip(twin_chart(rec, LABELS), rec.answer)
    assert s is not None and s.lead == "leave_normal" and s.other.action != "leave_normal"
    assert chart_opens_on(s, rec.answer) == "leave_normal"
    page = _render(rec)
    sec = _sec(page)
    assert 'data-shown="leave_normal"' in sec
    assert _pressed(sec) == ["leave_normal"]
    how = sec.split('<div class="twin-chart-how">', 1)[1].split("</div>", 1)[0]
    assert re.findall(r'<ul class="twin-line twin-how on" data-line="(\w+)">', how) == [
        "leave_normal"
    ]
    # its key is the green dashed line it is drawn as on a leave-it answer, not a solid one
    shown = how.split('twin-how on" data-line="leave_normal">', 1)[1].split("</ul>", 1)[0]
    assert re.findall(r'class="key-mark km-([\w-]+)"', shown)[0] == "base-lead"
    # the card's strip still draws its pair, Leave it against the choice that differs most
    assert f'points="{s.other.points}"' in _strip(page)


def test_a_leave_it_answer_with_a_better_choice_still_opens_on_it(tmp_path):
    rec = _leave(_outdoor(tmp_path), "better")
    s = twin_strip(twin_chart(rec, LABELS), rec.answer)
    assert s is not None and chart_opens_on(s, rec.answer) == "water" == s.other.action
    assert _pressed(_sec(_render(rec))) == ["water"]


def test_any_other_job_opens_on_the_strips_pick_as_before(tmp_path):
    rec = _outdoor(tmp_path)
    s = twin_strip(twin_chart(rec, LABELS), rec.answer)
    assert s is not None and s.lead == "water" and chart_opens_on(s, rec.answer) == "water"
    assert _pressed(_sec(_render(rec))) == ["water"]


def test_each_choices_caption_says_its_verdict(tmp_path):
    rec = _coriander(tmp_path)
    by = {ln.action: ln for ln in twin_chart(rec, LABELS).lines}
    water = by["water"].said
    assert water.startswith("Water it (worse than leaving it): ")
    assert water.endswith(" It stays moist without watering. Extra water isn't needed.")
    assert by["shelter"].said.startswith("Protect it (the same as leaving it): ")
    assert by["leave_normal"].said.startswith("Leave it: ")
    # the key under the title says it too, on the line it names
    assert ("other", "Water it", "the soil's water if you water it (worse than leaving it).") in (
        by["water"].legend_leave
    )
    # and the page carries the words the tap swaps in
    page = _render(rec)
    assert f'<span data-line="water">{water}</span>' in page.replace("&#39;", "'")


def test_unknown_verdicts_and_leaving_it_say_no_verdict(tmp_path):
    rec = _outdoor(tmp_path)
    rec.answer.compare = [
        CompareRow(action="leave_normal", vs_leaving_it="same", why="baseline"),
        CompareRow(action="water", vs_leaving_it="unknown", why=""),
        CompareRow(action="shelter", vs_leaving_it="better", why="cold risk Monday"),
    ]
    by = {ln.action: ln for ln in twin_chart(rec, LABELS).lines}
    assert by["water"].said.startswith("Water it: ")
    assert "than leaving it" not in by["leave_normal"].said
    assert "(" not in by["leave_normal"].legend[0][2]


def test_leaving_its_own_line_on_a_leave_it_chart_is_the_green_dashed_one():
    rules = {sel: body for at, sel, body in _rules(open(ANSWER_CSS).read()) if not at}
    sel = '.answer-page .twin-chart.leave-leads .twin-line[data-line="leave_normal"] polyline'
    assert "display: none" in rules[sel]
    name = '.answer-page .twin-chart.leave-leads .twin-names[data-line="leave_normal"] .line-name'
    assert "fill: var(--primary)" in rules[name]
    assert style._minify(open(ANSWER_CSS).read()) in style.CSS


def test_a_move_to_light_line_says_no_verdict_the_twin_cannot_give(tmp_path):
    # the twin can't model light: its "no difference" for moving it is not a verdict on light,
    # so the caption keeps to what the line does (27 Oct review of this PR)
    rec = _outdoor(tmp_path)
    rec.answer.compare = [
        CompareRow(action="leave_normal", vs_leaving_it="same", why="baseline"),
        CompareRow(
            action="move_light", vs_leaving_it="same", why="no difference over the next 2 weeks"
        ),
    ]
    by = {ln.action: ln for ln in twin_chart(rec, LABELS).lines}
    said = by["move_light"].said
    assert "than leaving it" not in said and "no difference" not in said.lower()
