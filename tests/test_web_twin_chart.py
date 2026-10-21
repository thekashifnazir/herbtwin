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
from herbtwin.twin_chart import BOTTOM, LABEL_MAX_X, RIGHT, TOP, twin_chart
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
    assert 'role="img" aria-labelledby="twin-chart-cap"' in svg
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
