"""The twin front and centre (23 Oct, Kash: "we should give it a more prominent role … It's
the whole point of the website, being the twin and what happens"; he picked mocks A and C).

A: a twin strip in the main card under the headline, the real Leave-it line against one
other choice and the needs-water line, captioned by the card's own twin line, with a link to
C. C: a "Your plant's twin" section after the card: what the twin is, its finding, the twin
pictures when the answer has them, then Compare (its chart, hint and table), which moved
here out of How we worked it out."""

import re
from pathlib import Path

from herbtwin import twin_bank
from herbtwin.answer import HEADLINES
from herbtwin.schemas import AnalysisRecord, CompareRow
from herbtwin.twin_bank import TwinFigure
from herbtwin.twin_chart import (
    _needs_label,
    _pts,
    starting_on,
    strip_pick,
    twin_chart,
    twin_strip,
)
from herbtwin.web import style
from herbtwin.web.answer_text import plan_text
from tests.test_web_answer_page import _render
from tests.test_web_answer_reveal import _rules
from tests.test_web_twin_chart import _cold_basil, _record

LABELS = {"leave_normal": "Leave it", "water": "Water it", "shelter": "Protect it"}
WHAT = (
    "Your plant's <strong>twin</strong> is a simple model of its soil water and frost risk. "
    "Each choice is tried on it against the next 2 weeks of weather."
)
SHEET = Path(__file__).parents[1] / "src/herbtwin/web/static/pages/answer_twin.css"


def _outdoor(tmp_path) -> AnalysisRecord:
    """Basil outdoors on a cold fortnight: the twin ran and its chart has data. The card's
    main job is "Water it", its line tested on the twin, and the twin rates watering better
    than leaving it (sheltering too): the twin backs the card."""
    rec = _cold_basil(_record(tmp_path))
    assert rec.observation is not None and rec.answer is not None
    rec.observation.setting = "outdoor"
    rec.answer.compare = [
        CompareRow(action="leave_normal", vs_leaving_it="same", why="baseline"),
        CompareRow(action="water", vs_leaving_it="better", why="less drying than leaving it"),
        CompareRow(action="shelter", vs_leaving_it="better", why="cold risk Monday"),
    ]
    first = rec.answer.do[0]
    assert first.action == "water" and first.if_you_do_from == "plant_model"
    first.if_you_do = "less drying than leaving it"
    return rec


def _leave(rec: AnalysisRecord, verdict: str = "same") -> AnalysisRecord:
    """The same record with "Leave it" as the card's job and line, the others rated `verdict`."""
    rec.answer.do[0].action = "leave_normal"
    rec.answer.headline = "Leave it for now and keep an eye on it."
    for r in rec.answer.compare:
        if r.action != "leave_normal":
            r.vs_leaving_it = verdict
    return rec


def _strip(page: str) -> str:
    return page.split('<div class="twin-strip"', 1)[1].split("</div>\n", 1)[0]


def _card(page: str) -> str:
    return page.split('<section class="card main-action"', 1)[1].split("</section>", 1)[0]


def _sec(page: str) -> str:
    """The twin section, to its own closing tag (it holds the pictures' section)."""
    start = page.index('<section class="twin-sec"')
    depth = 0
    for m in re.finditer(r"<section\b|</section>", page[start:]):
        depth += 1 if m.group() != "</section>" else -1
        if not depth:
            return page[start : start + m.end()]
    raise AssertionError("twin section not closed")


def _ys(points: str) -> list[float]:
    return [float(p.split(",")[1]) for p in points.split()]


def _figure() -> TwinFigure:
    pair = twin_bank.for_photo(next(iter(twin_bank._bank())))
    assert pair is not None
    return TwinFigure(
        pair=pair,
        do_label="If you water it",
        dont_label="If you don't",
        model_line="leaving it, dry by Thursday",
    )


# ---------- the picker: which one choice the strip draws against leaving it ----------
# review of the strip (23 Oct): the green line is always the card's own job, under its own
# caption; only a "Leave it" card picks another line to draw against it


def test_the_strip_draws_the_cards_own_job_against_leaving_it(tmp_path):
    rec = _outdoor(tmp_path)
    chart = twin_chart(rec, LABELS)
    assert chart is not None
    # sheltering is rated better too, and comes first in Compare's order of better ones…
    rec.answer.compare = [rec.answer.compare[0], rec.answer.compare[2], rec.answer.compare[1]]
    # …but the card says "Water it.": the strip draws watering, green, never another job
    assert strip_pick(chart, rec.answer) == "water"
    s = twin_strip(chart, rec.answer)
    assert s is not None and (s.base.action, s.other.action, s.lead) == (
        "leave_normal",
        "water",
        "water",
    )


def test_a_leave_it_card_draws_the_better_choice_against_it(tmp_path):
    rec = _leave(_outdoor(tmp_path))
    rec.answer.compare[2].vs_leaving_it = "better"  # sheltering
    chart = twin_chart(rec, LABELS)
    assert strip_pick(chart, rec.answer) == "shelter"
    assert twin_strip(chart, rec.answer).lead == "leave_normal"  # leaving it is the green line


def test_a_leave_it_card_with_none_better_draws_the_line_most_unlike_it(tmp_path):
    rec = _leave(_outdoor(tmp_path))
    chart = twin_chart(rec, LABELS)
    assert chart is not None
    base = _ys(next(ln.points for ln in chart.lines if ln.action == "leave_normal"))
    gap = {
        ln.action: sum(abs(a - b) for a, b in zip(_ys(ln.points), base, strict=True))
        for ln in chart.lines
        if ln.action != "leave_normal"
    }
    want = max(gap, key=lambda k: gap[k])
    assert gap[want] > min(gap.values())  # the fixture does tell them apart
    assert strip_pick(chart, rec.answer) == want


def test_no_strip_when_the_cards_job_has_no_line_or_there_is_no_leave_it_line(tmp_path):
    rec = _outdoor(tmp_path)
    chart = twin_chart(rec, LABELS)
    rec.answer.do[0].action = "prune"  # a job the twin does not draw
    rec.answer.compare.append(CompareRow(action="prune", vs_leaving_it="better", why="x"))
    assert strip_pick(chart, rec.answer) is None and twin_strip(chart, rec.answer) is None
    rec = _outdoor(tmp_path)
    rec.answer.compare = [r for r in rec.answer.compare if r.action != "leave_normal"]
    chart = twin_chart(rec, LABELS)
    assert chart is not None and strip_pick(chart, rec.answer) is None
    assert twin_strip(chart, rec.answer) is None and twin_strip(None, rec.answer) is None


def test_the_green_line_is_the_cards_job_whenever_the_strip_shows(tmp_path):
    seen = 0
    for main in ("water", "shelter", "leave_normal"):
        for verdicts in (
            ("better", "better"),
            ("better", "same"),
            ("same", "better"),
            ("same", "same"),
        ):
            rec = _outdoor(tmp_path)
            rec.answer.do[0].action = main
            rec.answer.headline = (  # the card's line is its job's own
                "Leave it for now and keep an eye on it."
                if main == "leave_normal"
                else HEADLINES[main]
            )
            rec.answer.compare[1].vs_leaving_it, rec.answer.compare[2].vs_leaving_it = verdicts
            s = twin_strip(twin_chart(rec, LABELS), rec.answer)
            if s is None:
                continue
            seen += 1
            assert s.lead == main, (main, verdicts)
            green = s.base if main == "leave_normal" else s.other
            assert green.action == main
            page = _render(rec)
            svg = _strip(page).split("<svg", 1)[1].split("</svg>", 1)[0]
            # leaving it's line is dashed as well when it is the job (25 Oct final walk)
            cls = "lead leave" if main == "leave_normal" else "lead"
            assert f'<polyline class="{cls}" points="{green.points}"/>' in svg, (main, verdicts)
    assert seen >= 6


def test_the_strip_shows_only_when_the_twin_backs_the_card(tmp_path):
    # "Water it." that the twin rates the same as leaving it (the parsley sample): no strip,
    # the card as it was with its twin line in its body; the twin's section stays
    rec = _outdoor(tmp_path)
    rec.answer.compare[1].vs_leaving_it = "same"
    page = _render(rec)
    assert twin_strip(twin_chart(rec, LABELS), rec.answer) is None
    assert '<div class="twin-strip"' not in page and '<section class="twin-sec"' in page
    body = _card(page)
    assert body.count('<p class="ifdo">') == 1
    assert body.index('class="because"') < body.index('<p class="ifdo">')
    # rated worse: no strip either
    rec.answer.compare[1].vs_leaving_it = "worse"
    assert '<div class="twin-strip"' not in _render(rec)
    # rated better, or a "Leave it" card: the strip
    rec.answer.compare[1].vs_leaving_it = "better"
    assert '<div class="twin-strip"' in _render(rec)
    assert '<div class="twin-strip"' in _render(_leave(_outdoor(tmp_path)))


def test_the_strip_is_cropped_to_its_lines(tmp_path):
    rec = _outdoor(tmp_path)
    chart = twin_chart(rec, LABELS)
    s = twin_strip(chart, rec.answer)
    assert s is not None and chart is not None
    x, y, w, h = s.view
    ys = _ys(s.base.points) + _ys(s.other.points) + [s.needs_y]
    assert y < min(ys) and y + h > max(ys)  # every line and the needs-water line inside
    assert h < chart.height  # shorter than the full chart: a strip


def test_the_strip_says_soil_water_and_names_its_two_lines(tmp_path):
    # the chart's own title names cold nights; the strip draws soil water alone
    rec = _outdoor(tmp_path)
    chart = twin_chart(rec, LABELS)
    assert chart.title.startswith("Soil water and cold nights")
    s = twin_strip(chart, rec.answer)
    assert s.title == "Soil water over the next 2 weeks: Water it and Leave it"
    assert (
        'role="img" aria-label="Soil water over the next 2 weeks: Water it and Leave it"'
        in _strip(_render(rec))
    )
    rec = _leave(_outdoor(tmp_path))
    assert twin_strip(twin_chart(rec, LABELS), rec.answer).title.endswith(": Leave it and Water it")


# ---------- A: the strip in the main card ----------


def test_the_strip_sits_in_the_card_under_the_headline_when_the_twin_ran(tmp_path):
    page = _render(_outdoor(tmp_path))
    card = _card(page)
    assert card.count('<div class="twin-strip"') == 1
    assert card.index("</h2>") < card.index("twin-strip") < card.index('class="because"')
    strip = _strip(page)
    assert "Your plant's twin" in strip and "2 weeks" in strip
    svg = strip.split("<svg", 1)[1].split("</svg>", 1)[0]
    assert 'role="img"' in svg and 'class="needs"' in svg
    assert len(re.findall(r"<polyline ", svg)) == 2  # leave it and one other, no more
    assert ">Leave it</text>" in svg and ">Water it</text>" in svg


def test_the_cards_twin_line_is_the_strips_caption_said_once(tmp_path):
    rec = _outdoor(tmp_path)
    page = _render(rec)
    card, strip = _card(page), _strip(page)
    line = rec.answer.do[0].if_you_do
    assert "Tested on your plant&#39;s twin:" in strip and line in strip
    assert card.count('<p class="ifdo">') == 1  # the caption, not a second line in the body


def test_the_strip_links_to_the_twin_section(tmp_path):
    page = _render(_outdoor(tmp_path))
    assert '<a class="strip-go" href="#twin-sec">' in _strip(page)
    assert 'id="twin-sec"' in page


def test_no_strip_when_the_twin_did_not_run(tmp_path):
    # indoors: no forecast, no twin
    rec = _outdoor(tmp_path)
    rec.observation.setting = "indoor"
    assert '<div class="twin-strip"' not in _render(rec)
    # a record saved before the days carried soil water: no chart to draw
    rec = _outdoor(tmp_path)
    for s in rec.state.strips:
        for d in s.days:
            d.soil_water_mm = None
    page = _render(rec)
    assert '<div class="twin-strip"' not in page
    assert _card(page).count('<p class="ifdo">') == 1  # the card as it was: its line in the body
    # the card's line is not the twin's (a job the twin does not compare): the card as it was
    rec = _outdoor(tmp_path)
    rec.answer.do[0].if_you_do_from = "outcome_table"
    assert '<div class="twin-strip"' not in _render(rec)
    # the setting not known to be outdoors: the brief's "outdoor" only
    rec = _outdoor(tmp_path)
    rec.observation.setting = "unknown"
    assert '<div class="twin-strip"' not in _render(rec)


# ---------- C: the twin's own section ----------


def test_the_twin_section_says_what_the_twin_is_and_what_it_found(tmp_path):
    rec = _outdoor(tmp_path)
    page = _render(rec)
    sec = _sec(page)
    assert '<h2 class="ts-h" id="twin-sec-h">Your plant\'s twin</h2>' in sec
    assert f'<p class="ts-what">{WHAT}</p>' in sec
    find = sec.split('<p class="ts-find">', 1)[1].split("</p>", 1)[0]
    # the Compare fold's own finding, its title and its quiet line, now the section's
    assert find == "<strong>Watering beats leaving it.</strong> Protecting it helps too."
    # straight after the card and where it came from
    card = page.index('<section class="card main-action"')
    assert page.index("</section>", card) < page.index('<section class="twin-sec"')
    assert page.index('<section class="twin-sec"') < page.index('<div class="this-week"')


def test_compare_lives_in_the_twin_section_once(tmp_path):
    page = _render(_outdoor(tmp_path))
    sec = _sec(page)
    for once in ('id="twin-chart"', 'class="compare-table"', 'id="twin-chart-words"'):
        assert page.count(once) == 1 and once in sec, once
    assert '<details class="compare' not in page  # no Compare fold left in How we worked it out
    details = page.split('<section class="details"', 1)[1]
    assert "twin-chart" not in details and "compare-table" not in details
    # the chart still draws itself as it arrives
    assert (
        '<figure class="twin-chart" id="twin-chart" data-shown="water" data-reveal="draw">' in sec
    )


def test_the_chart_starts_on_the_choice_the_strip_drew(tmp_path):
    # a "Leave it" card with none rated better: the chart alone would start on leaving it; it
    # starts on the strip's choice, so the card and the section draw the same pair
    rec = _leave(_outdoor(tmp_path))
    chart = twin_chart(rec, LABELS)
    pick = strip_pick(chart, rec.answer)
    assert chart.shown == "leave_normal" and pick != "leave_normal"
    sec = _sec(_render(rec))
    assert f'data-shown="{pick}"' in sec
    assert re.findall(r'class="twin-pick" data-line="(\w+)"[^>]*aria-pressed="true"', sec) == [pick]
    # "needs water" is placed clear of the line drawn first, not the one it would have been
    lines = {ln.action: _pts(ln.points) for ln in chart.lines}
    drawn = [lines[pick], lines["leave_normal"]]
    rest = [p for a, p in lines.items() if a not in (pick, "leave_normal")]
    x, y = _needs_label(chart.needs_y, chart.today, drawn, rest)
    assert f'<text class="axis needs-label" x="{x}" y="{y}">needs water</text>' in sec
    assert starting_on(chart, pick).needs_label == (x, y)
    assert starting_on(chart, chart.shown) is chart
    # and the panel says what it is, where the strip's link lands
    assert '<p class="ts-kind">Compare all choices · next 2 weeks</p>' in sec


def test_the_twin_pictures_open_the_section_and_show_nowhere_else(tmp_path):
    page = _render(_outdoor(tmp_path), twin=_figure())
    sec = _sec(page)
    assert page.count('<section class="twin"') == 1 and '<section class="twin"' in sec
    assert sec.index("ts-find") < sec.index('<section class="twin"') < sec.index('id="twin-chart"')
    # without pictures the section goes straight to the choices
    assert '<section class="twin"' not in _render(_outdoor(tmp_path))


def test_a_no_cure_answer_keeps_its_folded_line_and_has_no_twin_section(tmp_path):
    from herbtwin.answer import NO_CURE_HEADLINE

    rec = _outdoor(tmp_path)
    rec.answer.compare, rec.answer.headline = [], NO_CURE_HEADLINE
    page = _render(rec)
    assert '<section class="twin-sec"' not in page and '<div class="twin-strip"' not in page
    assert '<details class="compare fold fold-twin">' in page
    assert "Not compared: there is no cure, so the choices don't apply." in page


# ---------- the page as a whole ----------


def _filled_green(page: str) -> int:
    """Buttons and links filled in the press green: class "primary" on an <a> or <button>.
    Kash's decided exception, "Check the advice again", may be green too, so not counted."""
    tags = re.findall(r"<(?:a|button)\b[^>]*>([^<]*)", page)
    full = re.findall(r"<(?:a|button)\b[^>]*>", page)
    return sum(
        1
        for t, words in zip(full, tags, strict=True)
        if re.search(r'class="[^"]*\bprimary\b', t) and words.strip() != "Check the advice again"
    )


def test_one_filled_green_on_the_page(tmp_path):
    rec = _outdoor(tmp_path)
    rec.answer.level = "not_sure"
    page = _render(rec, twin=_figure())
    # at most one (24 Oct): "Make this surer" is outlined since the Toloka study, as a green
    # button under the headline read as the instruction; with the place known, none is green
    assert _filled_green(page) <= 1
    assert _filled_green(_strip(page) + _sec(page)) == 0
    assert '<a class="button quiet" href="#refine">Make this surer' in page


def test_the_rater_text_keeps_the_twin_line_once_and_skips_the_twin_parts(tmp_path):
    rec = _outdoor(tmp_path)
    text = plan_text(_render(rec, twin=_figure()))
    assert text.count("*Tested on your plant's twin:*") == 1
    for gone in ("today to", "Compare all choices", "Each choice is tried", "Watering beats"):
        assert gone not in text, gone
    for gone in ("Starting point", "Try each choice", "Leave it"):
        assert gone not in text, gone  # the chart's names and the table are not advice
    # pinned: the card's twin line now comes right after the headline (it captions the
    # strip there), and the pictures' block keeps its words. Nothing else moved
    assert text == PINNED


PINNED = """**TODAY**

## Water it.

*Tested on your plant's twin:* less drying than leaving it

The soil is dry and no rain is due.

**How sure we are:** Our best read. Right about half the time in our tests.

### Your plant in ~7 days

**Twin** leaving it, dry by Thursday.

Illustration for our sample photo, not a prediction. · Photo credits

This week

### Keep an eye on

- Yellow patches between leaf veins with grey-purple fuzz on the leaf underside

- Leaves yellowing between the veins or blackening in a mild spell before any cold night

Seen either? Send a new photo."""


# ---------- the sheet ----------


def test_the_twin_sheet_is_inlined_scoped_and_uses_tokens_only():
    sheet = SHEET.read_text("utf-8")
    assert style._minify(sheet) in style.CSS
    for _, sel, body in _rules(sheet):
        for part in re.split(r",(?![^()]*\))", sel):
            assert part.strip().startswith(".answer-page"), sel
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", body), sel


def test_the_chart_line_draws_in_its_new_home_and_the_phone_puts_the_section_after_the_card():
    css = style.CSS
    # the draw no longer waits for a fold to open: the chart is never in one now
    assert ".answer-page .twin-chart .twin-line.on polyline { animation: line-draw" in css
    assert "details[open] .twin-line.on polyline" not in css
    phone = (
        Path(__file__).parents[1] / "src/herbtwin/web/static/pages/answer_phone.css"
    ).read_text()
    rules = {s: b for at, s, b in _rules(phone)}
    assert rules[".answer-page .answer-cols > .plan > :is(.seen-problem, .twin-sec)"] == "order: 3;"
    assert "details.compare" not in phone


def test_leave_it_but_protect_it_gets_no_strip(tmp_path):
    # review of #511: "Leave it, but protect it before the cold night on …" leads with
    # leave_normal, so the strip drew Leave it green with Protect dashed; its advice is to
    # protect. That headline gets no strip; the card keeps its twin line, the section stays
    from herbtwin.answer import LEAVE_BUT_PROTECT

    rec = _leave(_outdoor(tmp_path))
    rec.answer.headline = LEAVE_BUT_PROTECT.format(day="Monday")
    assert twin_strip(twin_chart(rec, LABELS), rec.answer) is None
    page = _render(rec)
    assert '<div class="twin-strip"' not in page and '<section class="twin-sec"' in page


def test_the_pictures_heading_sits_under_the_twin_sections_heading(tmp_path):
    # review of #511: "Your plant in ~7 days" was an h2 inside the "Your plant's twin" h2
    # section; it is an h3 now, and raters still read it as a heading. The section takes focus
    # from the strip's "Compare all choices" link
    rec = _outdoor(tmp_path)
    page = _render(rec, twin=_figure())
    sec = _sec(page)
    assert '<h3 id="twin">Your plant in ~7 days</h3>' in sec and '<h2 id="twin"' not in page
    assert 'id="twin-sec" tabindex="-1"' in sec
    assert "### Your plant in ~7 days" in plan_text(page)
