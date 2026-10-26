"""25 Oct, Kash on the twin chart's key: "change the text here to make it clearer like we do
when you click between them on the bottom and have each on a different line for green, grey
and dotted line". Each mark drawn gets its own line with a small swatch of that mark, and the
lines still follow the tap. Higher is wetter, not better; the gaps between the cold bands
are milder nights ("what do the gaps mean?"); a brought-in line that runs drier says why."""

import re
from datetime import date

from herbtwin.plant_model import compare_actions
from herbtwin.schemas import CompareRow
from herbtwin.stages.twin import simulate
from herbtwin.twin_chart import twin_chart
from herbtwin.web import style
from tests.test_answer_walk_fixes import _render
from tests.test_twin import PACK, _env, _obs
from tests.test_web_twin_chart import _record

LABELS = {
    "leave_normal": "Leave it",
    "water": "Water it",
    "shelter": "Protect it (shelter or bring in)",
    "move_light": "Move it to better light",
}
NEEDS = ("needs", "", "Below this line, it needs water. Higher is wetter, not better.")
COLD = ("cold", "", "A cold night; the gaps are milder nights. ❄︎ marks each cold spell.")


def _cold_rainy(rec):
    """Kash's screenshot: a cold fortnight with rain and a few milder nights. Bringing it in
    keeps the cold off, but no rain reaches it, so its line runs below leaving it's."""
    start = date(2026, 10, 19)
    env = _env(t_min=3.0, rain=1.5, start=start)
    for i in (4, 5, 9, 10):
        env.days[i].t_min, env.days[i].t_max = 12.0, 18.0
    rec.pack = PACK
    rec.state = simulate(_obs(1), env, PACK, on=start)
    views = compare_actions(rec.state)
    rec.answer.compare = [
        CompareRow(action=a, vs_leaving_it=views[a].vs_leaving_it, why=views[a].why) for a in LABELS
    ]
    return rec


def test_the_key_is_one_line_per_mark_with_why_protect_runs_drier(tmp_path):
    chart = twin_chart(_cold_rainy(_record(tmp_path)), LABELS)
    assert chart is not None and chart.shown == "shelter"
    by = {ln.action: ln for ln in chart.lines}
    assert by["shelter"].legend == (
        ("line", "Protect it", "the soil's water if you protect it. It runs drier: no rain reaches it."),
        ("base", "Leave it", "the soil's water if you leave it."),
        NEEDS,
        COLD,
    )  # fmt: skip
    # moving it to the light gets the rain: nothing to explain
    assert by["move_light"].legend[0] == (
        "line", "Move it to better light", "the soil's water if you move it to better light."
    )  # fmt: skip
    # leaving it drawn: one line for it, then the dotted line and the cold
    assert by["leave_normal"].legend == (
        ("line", "Leave it", "the soil's water if you leave it."), NEEDS, COLD,
    )  # fmt: skip
    # one mark a line, so "dashed" never has to say which (the 25 Oct re-walk's finding)
    assert all("dashed" not in w for ln in chart.lines for _, _, w in ln.legend)


def test_on_a_leave_it_answer_the_green_dashed_line_is_leaving_it(tmp_path):
    chart = twin_chart(_cold_rainy(_record(tmp_path)), LABELS)
    shelter = next(ln for ln in chart.lines if ln.action == "shelter")
    assert shelter.legend_leave[:2] == (
        ("base-lead", "Leave it", "the soil's water if you leave it."),
        ("other", "Protect it", "the soil's water if you protect it. It runs drier: no rain reaches it."),
    )  # fmt: skip


def test_no_cold_night_no_cold_line(tmp_path):
    rec = _cold_rainy(_record(tmp_path))
    for s in rec.state.strips:
        for d in s.days:
            d.frost = 0.0
    assert all(m != "cold" for ln in twin_chart(rec, LABELS).lines for m, _, _ in ln.legend)


def test_the_page_draws_each_line_with_its_swatch_and_the_tap_still_swaps_them(tmp_path):
    page = _render(_cold_rainy(_record(tmp_path)))
    key = page.split('<div class="twin-chart-how">', 1)[1].split("</div>", 1)[0]
    lists = re.findall(r'<ul class="twin-line twin-how( on)?" data-line="(\w+)">', key)
    assert [a for on, a in lists if on] == ["shelter"] and len(lists) >= 3
    shown = key.split('twin-how on" data-line="shelter">', 1)[1].split("</ul>", 1)[0]
    items = re.findall(r'<li><span class="key-mark km-([\w-]+)" aria-hidden="true"></span>', shown)
    assert items == ["line", "base", "needs", "cold"]
    assert "<span><strong>Protect it</strong>: the soil&#39;s water" in shown  # one run of text
    assert re.search(r"\.twin-chart \.twin-how:not\(\.on\) \{ ?display: none", style.CSS)


def test_the_swatches_are_the_charts_own_marks():
    # the chart's own colours, widths and dash lengths; still one svg in the figure, the chart
    css = style.CSS
    for cls, paint, size in (
        ("km-line", "linear-gradient(var(--primary), var(--primary))", "3px"),
        ("km-base", "repeating-linear-gradient(90deg, var(--muted-fg) 0 5px, transparent 5px 9px)", "1.5px"),
        ("km-base-lead", "repeating-linear-gradient(90deg, var(--primary) 0 5px, transparent 5px 9px)", "3px"),
        ("km-other", "linear-gradient(var(--muted-fg), var(--muted-fg))", "1.5px"),
        ("km-needs", "repeating-linear-gradient(90deg, var(--warn) 0 2px, transparent 2px 5px)", "1.5px"),
    ):  # fmt: skip
        rule = f".answer-page .twin-chart .key-mark.{cls} {{ background-image: {paint}; background-size: 100% {size}; }}"
        assert rule in css, cls
    assert "linear-gradient(var(--cold-fg) 0 3px, var(--cold) 3px)" in css
