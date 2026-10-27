"""The card's twin strip and the twin's own chart draw their lines one way (25 Oct final
walk: the strip drew Leave it solid green and Water it dashed, while the chart's key said
"Green: if you water it. Dashed: if you leave it."). Leaving it is always the dashed line;
the card's job is always the green one, so on a leave-it answer the dashed line is green.
And a line's name never sits on the other line."""

import re

from herbtwin.twin_chart import (
    BELOW,
    RIGHT,
    TOP,
    _legend,
    _names,
    _span,
    short_name,
    twin_chart,
    twin_strip,
)
from herbtwin.web import style
from tests.test_answer_twin_front import LABELS, _leave, _outdoor, _strip
from tests.test_web_answer_page import _render
from tests.test_web_answer_reveal import _rules

ANSWER_CSS = "src/herbtwin/web/static/pages/answer.css"
TWIN_CSS = "src/herbtwin/web/static/pages/answer_twin.css"


def _figure(page: str) -> str:
    return page.split('<figure class="twin-chart', 1)[1].split("</figure>", 1)[0]


def test_leaving_it_is_dashed_on_the_strip_whatever_the_job(tmp_path):
    for leave in (False, True):
        (tmp_path / str(leave)).mkdir()
        rec = _outdoor(tmp_path / str(leave))
        if leave:
            rec = _leave(rec)
        s = twin_strip(twin_chart(rec, LABELS), rec.answer)
        assert s is not None, leave
        svg = _strip(_render(rec)).split("<svg", 1)[1].split("</svg>", 1)[0]
        base = "lead leave" if leave else "alt leave"
        other = "alt" if leave else "lead"
        assert f'<polyline class="{base}" points="{s.base.points}"/>' in svg, leave
        assert f'<polyline class="{other}" points="{s.other.points}"/>' in svg, leave
    rules = {sel: body for at, sel, body in _rules(open(TWIN_CSS).read()) if not at}
    assert "stroke-dasharray: 5 4" in rules[".answer-page .strip-chart polyline.leave"]
    assert "dasharray" not in rules[".answer-page .strip-chart polyline.alt"]
    assert "var(--primary)" in rules[".answer-page .strip-chart polyline.lead"]


def test_on_a_leave_it_answer_the_charts_dashed_line_is_the_green_one(tmp_path):
    (tmp_path / "w").mkdir(), (tmp_path / "l").mkdir()
    water = _render(_outdoor(tmp_path / "w"))
    assert _figure(water).startswith('" id="twin-chart"')  # no leave-leads: as before
    plain = _figure(water).split('twin-how on" data-line="water">', 1)[1].split("</ul>", 1)[0]
    assert re.findall(r'class="key-mark km-([\w-]+)"', plain)[:2] == ["line", "base"]
    leave = _render(_leave(_outdoor(tmp_path / "l")))
    fig = _figure(leave)
    assert fig.startswith(' leave-leads" id="twin-chart"')
    how = fig.split('<div class="twin-chart-how">', 1)[1].split("</div>", 1)[0]
    # nothing beats leaving it here, so the chart opens on it (27 Oct); tapped, Water it's key
    shown = how.split('twin-how" data-line="water">', 1)[1].split("</ul>", 1)[0]
    # leaving it's line is the green dashed one, the water line grey
    assert re.findall(r'class="key-mark km-([\w-]+)"', shown)[:2] == ["base-lead", "other"]
    assert "<strong>Leave it</strong>" in shown.split("km-other", 1)[0]
    rules = {sel: body for at, sel, body in _rules(open(ANSWER_CSS).read()) if not at}
    base = rules[".answer-page .twin-chart.leave-leads polyline.base"]
    assert "stroke: var(--primary)" in base
    other = rules[".answer-page .twin-chart.leave-leads .twin-line polyline"]
    assert "stroke: var(--muted-fg)" in other
    assert (
        "fill: var(--primary)" in rules[".answer-page .twin-chart.leave-leads .line-name.base-name"]
    )
    # leaving it keeps its dashes there: the base rule's dasharray is not overridden
    assert "stroke-dasharray: 5 4" in rules[".answer-page .twin-chart polyline.base"]
    assert "dasharray" not in base
    assert style._minify(open(ANSWER_CSS).read()) in style.CSS


def test_two_lines_near_the_top_have_both_names_under_them():
    # the walk's case: both lines wet, near the top, a few units apart. With no room above
    # the upper line, its name went under it, onto the lower line ("Water it" on Leave it)
    upper = [(34.0, TOP + 6), (RIGHT, TOP + 8)]
    lower = [(34.0, TOP + 12), (RIGHT, TOP + 16)]
    up, low = _names(_span(upper, "Water it"), _span(lower, "Leave it"))
    lowest = max(y for _, y in lower)
    # each name's letters stand about 11 units above its baseline: clear of both lines
    assert up - 11 > lowest and low - 11 > lowest, (up, low, lowest)
    assert up < low  # the upper line's name first
    assert up >= lowest + BELOW


def test_far_apart_the_upper_lines_name_stays_under_its_own_line():
    # review of the fix: with no room above but the lower line far down, the upper line's
    # name goes under its own line, as before; only close lines share the space under both
    up, low = _names((TOP + 2, TOP + 4), (90.0, 100.0))
    assert up == TOP + 4 + BELOW, up
    assert low == 100.0 + BELOW
    assert up - 11 > TOP + 4 and up + 2 < 90.0  # clear of both lines


def test_the_leave_it_key_names_each_compared_choice(tmp_path):
    # review nit: on a leave-it answer the key says the grey line's own name, whichever
    # choice it is: Protect it on the page, Move it to better light from the same code
    page = _render(_leave(_outdoor(tmp_path)))
    how = _figure(page).split('<div class="twin-chart-how">', 1)[1].split("</div>", 1)[0]
    shelter = how.split('data-line="shelter">', 1)[1].split("</ul>", 1)[0]
    assert re.findall(r"<strong>([^<]+)</strong>", shelter)[:2] == ["Leave it", "Protect it"]
    light = short_name("Move it to better light (a brighter spot)")  # the card's own words
    assert _legend(light, "Leave it", False, leave_leads=True)[:2] == (
        ("base-lead", "Leave it", "the soil's water if you leave it."),
        ("other", "Move it to better light", "the soil's water if you move it to better light."),
    )
