"""18 Oct judge ideas, item 3: the twin drawn on Compare, a 14-day soil water line per
choice with its cold nights, redrawn when a choice is tapped."""

import json
import re
from datetime import date

import httpx
import respx

from herbtwin.plant_model import _peak
from herbtwin.schemas import AnalysisRecord, CompareRow
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.stages.twin import simulate
from herbtwin.twin_chart import (
    BOTTOM,
    LABEL_MAX_X,
    NAME_BOTTOM,
    NAME_CHAR,
    NAME_GAP,
    NAME_TOP,
    NEEDS_W,
    RIGHT,
    TOP,
    _crosses,
    _names,
    plain_why,
    twin_chart,
)
from herbtwin.web import style
from tests.test_answer_walk_fixes import _render
from tests.test_twin import PACK, _env, _obs
from tests.test_web import ADV, JPEG, OBS, SAMPLE, _client

LABELS = {"leave_normal": "Leave it", "water": "Water it", "shelter": "Protect it"}


@respx.mock
def _record(tmp_path) -> AnalysisRecord:
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    r = c.post("/api/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")})
    return AnalysisRecord.model_validate(r.json())


def _cold_basil(rec: AnalysisRecord) -> AnalysisRecord:
    """The same record on a cold fortnight for basil (harmed under 10 C): leaving it has
    cold nights, bringing it in has none."""
    start = date(2026, 10, 19)  # a Monday
    rec.pack = PACK
    rec.state = simulate(_obs(1), _env(t_min=3.0, start=start), PACK, on=start)
    assert rec.answer is not None
    rec.answer.compare = [
        CompareRow(action="leave_normal", vs_leaving_it="same", why="baseline"),
        CompareRow(action="water", vs_leaving_it="same", why="no difference"),
        CompareRow(action="shelter", vs_leaving_it="better", why="cold risk Monday"),
    ]
    return rec


def test_compare_draws_the_twin_with_a_line_per_choice_and_tappable_rows(tmp_path):
    page = _render(_cold_basil(_record(tmp_path)))
    fig = page.split('<figure class="twin-chart"', 1)[1].split("</figure>", 1)[0]
    svg = fig.split("<svg", 1)[1].split("</svg>", 1)[0]
    assert 'role="img" aria-labelledby="twin-chart-title"' in svg
    # plain words on the axis, never raw mm
    assert ">wet</text>" in svg and ">dry</text>" in svg and ">needs water</text>" in svg
    assert ">Today</text>" in svg and ">2 weeks</text>" in svg and " mm" not in fig
    lines = re.findall(r'<g class="twin-line( on)?" data-line="(\w+)"', svg)
    assert len(lines) >= 3 and sum(1 for on, _ in lines if on) == 1
    shown = "shelter"  # the better choice is drawn first
    assert f'data-shown="{shown}"' in page and (" on", shown) in lines
    # each drawn choice is a button in the table, the shown one pressed
    table = page.split('<details class="compare fold', 1)[1].split("</table>", 1)[0]
    picks = re.findall(r'class="twin-pick" data-line="(\w+)"[^>]*aria-pressed="(\w+)"', table)
    assert {a for a, _ in picks} == {a for _, a in lines}
    assert [a for a, p in picks if p == "true"] == [shown]
    # the photo dot on Today, and words for a screen reader that follow the tap
    assert 'id="twin-chart-photo"' in svg and 'aria-live="polite"' in fig
    assert 'id="twin-chart-words"' in fig


def test_the_line_is_the_twins_soil_water(tmp_path):
    rec = _cold_basil(_record(tmp_path))
    chart = twin_chart(rec, LABELS)
    assert chart is not None and rec.state is not None
    base = next(ln for ln in chart.lines if ln.action == "leave_normal")
    ys = [float(p.split(",")[1]) for p in base.points.split()]
    strip = next(s for s in rec.state.strips if s.action == "do_nothing")
    cap = rec.state.capacity_mm
    want = [rec.state.water_mm] + [d.soil_water_mm for d in strip.days]
    assert len(ys) == 15  # today, then the end of each of the 14 days
    for y, mm in zip(ys, want, strict=True):
        assert abs(y - (BOTTOM - (BOTTOM - TOP) * mm / cap)) < 0.1


def test_cold_nights_belong_to_the_choice_and_sheltering_clears_them(tmp_path):
    chart = twin_chart(_cold_basil(_record(tmp_path)), LABELS)
    assert chart is not None
    by = {ln.action: ln for ln in chart.lines}
    assert by["leave_normal"].cold and by["leave_normal"].cold_label == "Cold risk Mon"
    assert by["shelter"].cold == [] and by["shelter"].cold_label == ""
    assert chart.shown == "shelter"  # the better choice is drawn first
    assert "no cold risk" in by["shelter"].said and "cold risk Monday" in by["leave_normal"].said


def test_records_saved_before_the_soil_water_draw_no_chart(tmp_path):
    rec = _cold_basil(_record(tmp_path))
    assert rec.state is not None
    for s in rec.state.strips:
        for d in s.days:
            d.soil_water_mm = None
    assert twin_chart(rec, LABELS) is None
    rec = _cold_basil(_record(tmp_path))
    assert rec.state is not None
    rec.state.needs_water_mm = None
    assert twin_chart(rec, LABELS) is None


def test_the_chart_fades_only_when_motion_is_welcome():
    css = style.CSS
    moving = css.split("@media (prefers-reduced-motion: no-preference) { .answer-page .twin-chart")
    assert len(moving) == 2 and "transition: opacity" in moving[1].split("}", 1)[0]
    still = css.split(".answer-page .twin-chart .twin-line {", 1)[1].split("}", 1)[0]
    assert "transition" not in still


def _ys(points: str) -> list[float]:
    return [float(p.split(",")[1]) for p in points.split()]


def test_each_choice_draws_the_twin_run_its_verdict_was_judged_on(tmp_path):
    # "Water it" maps to two runs (water now, water lightly); the line is the one with the
    # lower peak risk, as plant_model's verdict picks it, so the word and the line agree
    rec = _cold_basil(_record(tmp_path))
    assert rec.state is not None
    by = {s.action: s for s in rec.state.strips}
    for d in by["water_lightly"].days:  # the second of the two runs is the safer one here
        d.frost = 0.0
    best = min((by["water_now"], by["water_lightly"]), key=_peak)
    assert best is by["water_lightly"]
    other = by["water_lightly"] if best is by["water_now"] else by["water_now"]
    assert [d.soil_water_mm for d in best.days] != [d.soil_water_mm for d in other.days]
    chart = twin_chart(rec, LABELS)
    assert chart is not None
    water = next(ln for ln in chart.lines if ln.action == "water")
    cap = rec.state.capacity_mm
    want = [round(BOTTOM - (BOTTOM - TOP) * min(d.soil_water_mm / cap, 1), 1) for d in best.days]
    assert _ys(water.points)[1:] == want


def test_a_late_cold_night_keeps_its_band_and_label_inside_the_chart(tmp_path):
    rec = _cold_basil(_record(tmp_path))
    assert rec.state is not None
    for s in rec.state.strips:
        for i, d in enumerate(s.days):
            d.frost = 0.9 if i == 13 and s.action == "do_nothing" else 0.0
    chart = twin_chart(rec, LABELS)
    assert chart is not None
    base = next(ln for ln in chart.lines if ln.action == "leave_normal")
    assert len(base.cold) == 1 and base.cold_label.startswith("Cold risk ")
    band = base.cold[0]
    assert band.x + band.width <= RIGHT + 0.1 and base.cold_x <= LABEL_MAX_X


def test_leaving_its_cold_nights_show_faintly_before_any_tap(tmp_path):
    # 18 Oct pre-deploy check: Compare opens on Protect, and the cold bands that make it
    # better only showed after a tap on a risky choice
    page = _render(_cold_basil(_record(tmp_path)))
    svg = page.split('<figure class="twin-chart"', 1)[1].split("</svg>", 1)[0]
    assert 'data-shown="shelter"' in page
    faint = svg.split('<g class="base-cold">', 1)[1].split("</g>", 1)[0]
    assert faint.count("<rect ") >= 1 and ">Cold risk Mon if left out</text>" in faint
    # drawn under the choice lines, so the shown line's own bands sit on top
    assert svg.index('<g class="base-cold">') < svg.index('<g class="twin-line')
    css = style.CSS
    assert re.search(r"\.twin-chart \.base-cold rect \{[^}]*opacity", css)
    assert re.search(
        r":has\(\.twin-line\.on \.cold-label\) \.base-cold text \{[^}]*display: none", css
    )


def test_a_late_left_out_label_ends_at_the_right_edge(tmp_path):
    # "Cold risk Mon if left out" is about 180 units wide: from a second-week night it
    # would run off the 340-wide chart, so it is anchored at the right edge instead
    rec = _cold_basil(_record(tmp_path))
    assert rec.state is not None
    for s in rec.state.strips:
        for i, d in enumerate(s.days):
            d.frost = 0.9 if i == 12 else 0.0
    chart = twin_chart(rec, LABELS)
    assert chart is not None
    base = next(ln for ln in chart.lines if ln.action == "leave_normal")
    assert base.left_out == (RIGHT, "end")
    page = _render(rec)
    assert f'x="{RIGHT}" y="16" text-anchor="end">Cold risk ' in page
    early = next(
        ln
        for ln in twin_chart(_cold_basil(_record(tmp_path)), LABELS).lines
        if ln.action == "leave_normal"
    )
    assert early.left_out == (early.cold[0].x, "start")


def test_no_faint_layer_when_leaving_it_has_no_cold_night(tmp_path):
    rec = _cold_basil(_record(tmp_path))
    assert rec.state is not None
    for s in rec.state.strips:
        for d in s.days:
            d.frost = 0.0
    assert '<g class="base-cold">' not in _render(rec)


def test_each_cold_night_has_an_edge_that_can_be_seen():
    # #290 follow-up: the sky wash is 1.18:1 on the card, so a band alone failed the 3:1 a
    # chart mark needs. A --cold-fg edge on top of every band carries it in both themes
    from tests.test_web_home import _contrast, _tokens

    for i, card in enumerate(_tokens("card")):
        for under in (card, _tokens("sky")[i]):
            assert _contrast(_tokens("sky-fg")[i], under) >= 3, (i, under)
    css = style.CSS
    assert re.search(r"\.twin-chart \.cold-edge \{[^}]*stroke: var\(--cold-fg\)", css)
    # leaving it's edge is dashed like its line, and never faded with its wash
    assert re.search(r"\.twin-chart \.base-cold \.cold-edge \{[^}]*stroke-dasharray", css)
    assert ".base-cold rect {" in css and ".base-cold line" not in css


def test_the_shown_and_left_out_bands_both_draw_their_edges(tmp_path):
    page = _render(_cold_basil(_record(tmp_path)))
    svg = page.split('<figure class="twin-chart"', 1)[1].split("</svg>", 1)[0]
    faint = svg.split('<g class="base-cold">', 1)[1].split("</g>", 1)[0]
    shown = svg.split('data-line="leave_normal">', 1)[1].split("</g>", 1)[0]
    for group in (faint, shown):
        bands = re.findall(r'<rect (?:class="cold" )?x="([\d.]+)" y="22" width="([\d.]+)"', group)
        edges = re.findall(r'<line class="cold-edge" x1="([\d.]+)" x2="([\d.]+)"', group)
        assert bands and len(edges) == len(bands)
        for (x, w), (x1, x2) in zip(bands, edges, strict=True):
            assert float(x1) == float(x) and abs(float(x2) - float(x) - float(w)) < 0.11


def test_the_twin_chart_is_open_from_the_start_when_the_twin_ran(tmp_path):
    # 22 Oct, Kash: the twin chart open by default; it is the thing only herbtwin shows
    from herbtwin.schemas import CompareRow
    from tests.test_web_answer_page import _render, _unsure_record

    rec = _unsure_record(tmp_path)
    rec.answer.compare = [
        CompareRow(action="leave_normal", vs_leaving_it="same", why="baseline"),
        CompareRow(action="shelter", vs_leaving_it="better", why="no cold nights"),
    ]
    assert '<details class="compare fold fold-twin" open>' in _render(rec)
    # nothing compared (a no-cure answer): the "Not compared" line stays folded
    from herbtwin.answer import NO_CURE_HEADLINE

    rec.answer.compare, rec.answer.headline = [], NO_CURE_HEADLINE
    page = _render(rec)
    assert '<details class="compare fold fold-twin">' in page and 'fold-twin" open' not in page


# 22 Oct, Kash: "Compare all choices" was not obvious to read. The chart says what it shows,
# names its lines where they end, keeps "needs water" off the lines and marks every cold
# window; the table's verdicts are small tags, and nothing says "baseline"


def _two_cold_windows(rec: AnalysisRecord) -> AnalysisRecord:
    """Leaving it has two cold spells (days 3-4 and day 10); sheltering has none."""
    assert rec.state is not None
    for s in rec.state.strips:
        for i, d in enumerate(s.days):
            d.frost = 0.9 if s.action == "do_nothing" and i in (2, 3, 9) else 0.0
    return rec


def _pts(points: str) -> list[tuple[float, float]]:
    return [(float(a), float(b)) for a, b in (p.split(",") for p in points.split())]


def test_the_chart_says_what_it_shows_above_it(tmp_path):
    page = _render(_cold_basil(_record(tmp_path)))
    fig = page.split('<figure class="twin-chart"', 1)[1].split("</figure>", 1)[0]
    title = fig.split('<p class="twin-chart-title" id="twin-chart-title">', 1)[1]
    assert title.startswith("Soil water and cold nights, next 2 weeks</p>")
    assert fig.index("twin-chart-title") < fig.index("<svg")
    # the caption no longer carries a legend; it says the choices draw their lines
    cap = fig.split('<span id="twin-chart-cap">', 1)[1].split("</span>", 1)[0]
    assert cap == "Tap a choice to see its line on the chart."
    rec = _cold_basil(_record(tmp_path))
    assert rec.state is not None
    for s in rec.state.strips:
        for d in s.days:
            d.frost = 0.0
    assert twin_chart(rec, LABELS).title == "Soil water over the next 2 weeks"


def test_each_line_is_named_at_its_end_clear_of_the_lines(tmp_path):
    rec = _cold_basil(_record(tmp_path))
    chart = twin_chart(rec, {**LABELS, "shelter": "Protect it (shelter or bring in)"})
    assert chart is not None
    by = {ln.action: ln for ln in chart.lines}
    assert by["shelter"].name == "Protect it" and by["leave_normal"].name == "Leave it"
    base = _pts(by["leave_normal"].points)
    for ln in chart.lines:
        if ln.action == "leave_normal":
            assert ln.base_name_y is None  # its own line is the one drawn: one name
            continue
        names = [(ln.name, ln.name_y), ("Leave it", ln.base_name_y)]
        assert abs(ln.name_y - ln.base_name_y) >= NAME_GAP
        for name, y in names:
            assert NAME_TOP <= y <= NAME_BOTTOM
            box = (RIGHT - NAME_CHAR * len(name), RIGHT, y - 10, y)
            assert not _crosses(_pts(ln.points), *box), (ln.action, name)
            assert not _crosses(base, *box), (ln.action, name)
    page = _render(rec)
    svg = page.split('<figure class="twin-chart"', 1)[1].split("</svg>", 1)[0]
    shown = svg.split('<g class="twin-line twin-names on" data-line="shelter">', 1)[1]
    shown = shown.split("</g>", 1)[0]
    assert '<text class="line-name base-name" x="332"' in shown and ">Leave it</text>" in shown
    assert re.search(
        r'<text class="line-name" x="332" y="[\d.]+" text-anchor="end">Protect it<', shown
    )
    # the names sit over every line, and each in its line's colour
    assert svg.index('polyline class="base"') < svg.index("twin-names")
    css = style.CSS
    assert re.search(r"\.twin-chart \.line-name \{[^}]*fill: var\(--primary\)", css)
    assert re.search(r"\.twin-chart \.line-name\.base-name \{[^}]*fill: var\(--muted-fg\)", css)


def test_names_near_the_axis_stay_inside_and_apart():
    up, low = _names((118.0, 119.0), (120.0, 121.0))
    assert NAME_TOP <= min(up, low) and max(up, low) <= NAME_BOTTOM
    assert abs(up - low) >= NAME_GAP
    up, low = _names((22.0, 23.0), (24.0, 25.0))  # both lines at the top: names below them
    assert NAME_TOP <= min(up, low) and abs(up - low) >= NAME_GAP


def test_needs_water_is_never_drawn_over_a_line(tmp_path):
    for rec in (_cold_basil(_record(tmp_path)), _two_cold_windows(_cold_basil(_record(tmp_path)))):
        chart = twin_chart(rec, LABELS)
        assert chart is not None
        x, y = chart.needs_label
        by = {ln.action: ln for ln in chart.lines}
        for action in (chart.shown, "leave_normal"):
            assert not _crosses(_pts(by[action].points), x, x + NEEDS_W, y - 10, y), action
        page = _render(rec)
        assert f'<text class="axis needs-label" x="{x}" y="{y}">needs water</text>' in page


def test_every_cold_window_has_a_snowflake_and_one_says_cold_nights(tmp_path):
    rec = _two_cold_windows(_cold_basil(_record(tmp_path)))
    chart = twin_chart(rec, LABELS)
    assert chart is not None
    base = next(ln for ln in chart.lines if ln.action == "leave_normal")
    assert len(base.cold) == 3 and len(base.marks) == 2  # 3 cold nights in 2 spells
    for m in base.marks:  # each snowflake sits under its own blue band
        assert any(b.x <= m <= b.x + b.width for b in base.cold)
    assert base.key is not None
    svg = _render(rec).split('<figure class="twin-chart"', 1)[1].split("</svg>", 1)[0]
    faint = svg.split('<g class="base-cold">', 1)[1].split("</g>", 1)[0]
    assert faint.count('class="cold-mark"') == 2 and faint.count(">cold nights</text>") == 1
    # a row of its own under the axis, then the week labels below it
    assert re.search(r'class="cold-mark" x="[\d.]+" y="139"', faint)
    assert 'y="159" text-anchor="start">Today</text>' in svg and 'viewBox="0 0 340 166"' in svg
    css = style.CSS
    assert re.search(r"\.twin-chart text\.cold-mark \{[^}]*fill: var\(--cold-fg\)", css)


def test_the_compare_table_says_better_or_same_in_tags_and_never_baseline(tmp_path):
    page = _render(_cold_basil(_record(tmp_path)))
    fold = page.split('<details class="compare fold', 1)[1].split("</details>", 1)[0]
    assert "baseline" not in fold.lower()
    rows = fold.split("<tbody>", 1)[1].split("</tbody>", 1)[0].split("<tr>")[1:]
    by = {re.search(r'data-line="(\w+)"', r)[1]: r for r in rows}
    assert (
        '<span class="verdict better"><span aria-hidden="true">▲</span> Better</span>'
        in by["shelter"]
    )
    assert '<span class="verdict same"><span aria-hidden="true">=</span> Same</span>' in by["water"]
    leave = by["leave_normal"]
    # round 2 (22 Oct, Kash): a neutral tag in words, not a bare dash
    assert '<span class="verdict start">Starting point</span>' in leave and "—" not in leave
    assert '<td class="why">What happens if you do nothing.</td>' in leave  # its why: "baseline"
    # the twin's own words for leaving it are kept, said as a plain sentence
    rec = _cold_basil(_record(tmp_path))
    rec.answer.compare[0].why = "cold risk Monday if left out"
    assert '<td class="why">Cold could harm it on Monday if left out.</td>' in _render(rec)


def test_the_verdict_tags_are_small_tints_not_buttons_and_a_narrow_table_stacks():
    css = style.CSS
    tag = css.split(".answer-page .verdict {", 1)[1].split("}", 1)[0]
    assert "padding: 2px 10px" in tag and "14px" in tag
    better = css.split(".answer-page .verdict.better {", 1)[1].split("}", 1)[0]
    assert better.strip() == "background: var(--soft); color: var(--ok);"
    for rule in (tag, better):
        assert not re.search(r"border:|shadow|--primary", rule)
    # the table stacks by its own width, so the desktop side column stacks too
    assert "container: compare / inline-size" in css
    narrow = css.split("@container compare (max-width: 560px) {", 1)[1]
    assert ".compare-table thead { display: none; }" in narrow
    assert re.search(r"td\.why \{ display: block;", narrow)
    from tests.test_web_home import _contrast, _tokens

    for i in (0, 1):  # light, dark: each tag's words read on its tint
        assert _contrast(_tokens("ok")[i], _tokens("soft")[i]) >= 4.5
        assert _contrast(_tokens("fg")[i], _tokens("muted")[i]) >= 4.5
        assert _contrast(_tokens("clay")[i], _tokens("clay-bg")[i]) >= 4.5


# round 2 (22 Oct, Kash): "text could be improved and explanations, and keep a line between
# these": how to read the chart under its title, plain reasons, a line above the first row


def test_under_the_title_it_says_how_to_read_the_lines_drawn(tmp_path):
    rec = _cold_basil(_record(tmp_path))
    chart = twin_chart(rec, {**LABELS, "shelter": "Protect it (shelter or bring in)"})
    assert chart is not None
    by = {ln.action: ln for ln in chart.lines}
    assert by["shelter"].how == (
        "Green: if you protect it. Dashed: if you leave it. Below the dotted line, it needs "
        "water. \u2744\ufe0e marks cold nights."
    )
    # leaving it drawn: its green line is the dashed one, so the dashed one is not named twice
    assert by["leave_normal"].how.startswith("Green: if you leave it. Below the dotted line")
    assert "Dashed" not in by["leave_normal"].how
    # no cold night on any line: no snowflakes drawn, so none explained
    assert rec.state is not None
    for s in rec.state.strips:
        for d in s.days:
            d.frost = 0.0
    assert all("\u2744" not in ln.how for ln in twin_chart(rec, LABELS).lines)
    # on the page: one sentence per drawn line, the shown one's visible, swapped by the tap
    fig = _render(_cold_basil(_record(tmp_path))).split('<figure class="twin-chart"', 1)[1]
    how = fig.split('<p class="twin-chart-how">', 1)[1].split("</p>", 1)[0]
    spans = re.findall(r'<span class="twin-line twin-how( on)?" data-line="(\w+)">', how)
    assert {a for _, a in spans} == {"leave_normal", "water", "shelter"}
    assert [a for on, a in spans if on] == ["shelter"]
    assert fig.index("twin-chart-how") < fig.index("<svg")
    assert re.search(r"\.twin-chart \.twin-how:not\(\.on\) \{ ?display: none", style.CSS)


def test_the_reasons_read_as_plain_sentences():
    assert (
        plain_why("cold risk Thursday if left out") == "Cold could harm it on Thursday if left out."
    )
    assert plain_why("frost risk Monday if left out; shelter avoids it") == (
        "Sheltering it avoids Monday's frost."
    )
    assert plain_why("no difference over the next 2 weeks") == (
        "Makes no difference in the next 2 weeks."
    )
    assert plain_why("dry by Friday if left; watering keeps it moist") == (
        "It dries out by Friday if left alone. Watering keeps it moist."
    )
    assert plain_why("stays moist without watering; extra water risks waterlogged roots") == (
        "It stays moist without watering. Extra water could waterlog the roots."
    )
    assert plain_why("no cold nights forecast") == "No cold nights forecast."
    assert plain_why("Already a sentence.") == "Already a sentence."


def test_plain_reasons_are_the_tables_alone_the_twins_words_are_kept(tmp_path):
    # the chat, the Also do card and the evals read the twin's own strings
    from herbtwin.web.answer_text import plan_text

    rec = _cold_basil(_record(tmp_path))
    rec.answer.compare[2].why = "cold risk Monday if left out; shelter avoids it"
    page = _render(rec)
    assert '<td class="why">Sheltering it avoids Monday\'s cold.</td>' in page.replace("&#39;", "'")
    assert rec.answer.compare[2].why == "cold risk Monday if left out; shelter avoids it"
    assert "Sheltering it avoids" not in plan_text(page)  # the raters' text never had Compare


def test_a_line_sits_above_the_first_choice_too():
    narrow = style.CSS.split("@container compare (max-width: 560px) {", 1)[1]
    assert re.search(
        r"\.compare-table tbody tr:first-child \{ ?border-top: 1px solid var\(--border\)", narrow
    )
