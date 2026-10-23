"""The answer's top and its "This week" panel (23 Oct answer-page critique, parts 1 to 4,
Kash: "sounds great"): the band's switch as a small link; the headline card with its face
beside the headline, short rows and a one-line how sure; one "Where this came from" line
under the card; the twin pictures' deep-green captions; and Also do, Check first and Keep an
eye on as ruled rows of one panel, with GBIF's records as a sub-line of Keep an eye on."""

import re
from pathlib import Path

from herbtwin.web import style
from herbtwin.web.answer_text import plan_text
from herbtwin.web.app import TEMPLATES
from tests.test_web_answer_page import _full_plan, _render, _unsure_record
from tests.test_web_answer_reveal import _rules

SHEET = Path(__file__).parents[1] / "src/herbtwin/web/static/pages/answer_top.css"


def _sheet() -> dict[str, str]:
    return {s: b for at, s, b in _rules(SHEET.read_text("utf-8")) if not at}


def _card(page: str) -> str:
    return page.split('<section class="card main-action"', 1)[1].split("</section>", 1)[0]


def _week(page: str) -> str:
    # up to the first thing after the panel (review: a Jinja comment never reaches the page)
    after = r'<section class="indoor-now"|<details class="by-part"|<h2 id="next-step"'
    return re.split(after, page.split('<div class="this-week">', 1)[1], maxsplit=1)[0]


# ---------- 1. the band's switch ----------


def test_the_switch_is_a_small_link_when_the_read_gave_a_setting(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.observation.setting = "outdoor"
    switch = _render(rec).split('<form class="note setting-switch"', 1)[1].split("</form>", 1)[0]
    assert '<button type="submit" class="switch as-link">Indoors? Switch' in switch
    link = _sheet()[".answer-page .page-band .setting-switch .switch.as-link"]
    for say in (
        "background: none",
        "border: 0",
        "text-decoration: underline",
        "color: var(--band-fg)",
    ):
        assert say in link, say
    assert int(re.search(r"min-height: (\d+)px", link)[1]) >= 44  # still a thumb's tap


def test_with_no_setting_read_the_two_choices_stay_buttons(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.observation.setting = "unknown"
    switch = _render(rec).split('<form class="note setting-switch"', 1)[1].split("</form>", 1)[0]
    assert switch.count('class="switch"') == 2 and "as-link" not in switch


# ---------- 2. the headline card ----------


def test_the_face_sits_beside_the_headline(tmp_path):
    head = _card(_render(_full_plan(tmp_path))).split('<div class="head">', 1)[1]
    row = head.split('<div class="headline">', 1)[1]
    assert row.index('<h2 id="main-action">') < row.index('<p class="plant-mood" id="plant-mood">')
    assert _card(_render(_full_plan(tmp_path))).count('id="plant-mood"') == 1
    rules = _sheet()
    assert "display: flex" in rules[".answer-page .main-action .headline"]


def test_with_the_voice_on_the_face_stays_with_its_button(tmp_path):
    card = _card(_render(_full_plan(tmp_path), voice=True))
    assert 'id="plant-mood"' not in card and '<div class="voice" id="voice"' in card


def test_the_twin_line_is_its_own_ruled_row():
    rules = _sheet()
    assert "border-top: 1px solid var(--border)" in rules[".answer-page .main-action > .ifdo"]
    assert "display: block" in rules[".answer-page .main-action > .ifdo .lead"]


def test_how_sure_never_says_the_base_doubt_nor_anything_in_its_place(tmp_path):
    # Kash: cut "Mostly: advice of this kind is right less often"; the badge's line already
    # says how often it is right
    page = _render(_unsure_record(tmp_path))
    sure = page.split('<p class="sure">', 1)[1].split("</p>", 1)[0]
    assert "less often" not in sure and "Mostly" not in sure and "See why below" not in sure
    assert "Right about 1 in 3 times in our tests." in sure
    # on one line with its chip: the heading no longer takes a line of its own
    assert "flex-basis: auto" in _sheet()[".answer-page .main-action > .sure > strong"]


def test_where_it_came_from_is_one_quiet_line_under_the_card(tmp_path):
    page = _render(_full_plan(tmp_path), advised_by="NVIDIA Nemotron 3 Super")
    card = _card(page)
    assert "sources-line" not in card.replace("sources-line trusted-quote", "")
    assert "decided-by" not in card
    after = page.split('<section class="card main-action"', 1)[1].split("</section>", 1)[1]
    line = after.lstrip().split("</div>", 1)[0]
    assert line.startswith('<div class="came-from"><p class="came-from-h">Where this came from</p>')
    assert '<p class="sources-line">Sources: ' in line
    assert (
        '<p class="decided-by">Decided by NVIDIA Nemotron 3 Super on Nebius Token Factory' in line
    )
    assert "display: inline" in _sheet()[".answer-page .came-from > p"]
    # nothing to say: no empty line
    rec = _full_plan(tmp_path)
    rec.pack = None
    assert 'class="came-from"' not in _render(rec)


def test_on_a_phone_the_line_stays_under_its_card():
    # with the card, in every phone order (answer_phone.css since 23 Oct)
    phone = SHEET.with_name("answer_phone.css").read_text("utf-8")
    rules = {s: b for at, s, b in _rules(phone) if at == ("@media (max-width: 959px)",)}
    sel = ".answer-page .answer-cols .main-action, .answer-page .answer-cols > .plan > .came-from"
    assert "order: 1" in rules[sel]


def test_the_rater_text_keeps_the_line_and_the_panel(tmp_path):
    page = _render(_full_plan(tmp_path), advised_by="NVIDIA Nemotron 3 Super")
    text = plan_text(page)
    assert "Where this came from" in text and "Decided by NVIDIA Nemotron 3 Super" in text
    assert text.index("Where this came from") < text.index("This week") < text.index("### Also do")


# ---------- 3. the twin pictures ----------


def test_the_twin_captions_are_deep_green_chips():
    cap = _sheet()[".answer-page .twin figcaption"]
    assert "background: var(--band)" in cap and "color: var(--band-fg)" in cap
    assert "position: absolute" in cap and "border-radius: var(--pill)" in cap


# ---------- 4. This week ----------


def test_this_week_is_one_panel_of_rows_in_the_plans_order(tmp_path):
    rec = _full_plan(tmp_path)
    page = _render(rec, reported_on=True)
    week = _week(page)
    assert week.startswith('<p class="this-week-h">This week</p>')
    at = [
        week.index('<section class="also"'),
        week.index('<section class="dont"'),
        week.index('<section class="watch"'),
        week.index('<section class="reported"'),
    ]
    assert at == sorted(at)
    # under "This week" a THIS WEEK tag said it twice; other times stay
    also = week.split('<section class="also"', 1)[1].split("</section>", 1)[0]
    assert "THIS WEEK" not in also
    # ...and any other time keeps its tag (review)
    rec.answer.do[1].when = "today"
    also = _week(_render(rec)).split('<section class="also"', 1)[1].split("</section>", 1)[0]
    assert '<span class="tag later">TODAY</span>' in also


def test_each_rows_heading_is_a_tag_in_its_colour():
    rules = _sheet()
    for part, bg, fg in (
        ("also", "--soft", "--primary"),
        ("dont", "--clay-bg", "--clay"),
        ("watch", "--warn-bg", "--warn"),
    ):
        tag = rules[f".answer-page .this-week > .{part} > h2"]
        assert f"background: var({bg})" in tag and f"color: var({fg})" in tag, part
    # the rows lose their own card: one inked panel holds them
    row = rules[".answer-page .this-week > :is(.also, .dont, .watch, .reported)"]
    assert "box-shadow: none" in row and "border-top: 1px solid var(--border)" in row
    assert "box-shadow: 5px 5px 0 var(--ink-shadow)" in rules[".answer-page .this-week"]


def test_without_a_row_there_is_no_panel_and_the_records_stand_alone(tmp_path):
    rec = _full_plan(tmp_path)
    rec.answer.do = rec.answer.do[:1]
    rec.answer.dont = None
    rec.answer.watch = None
    page = _render(rec, reported_on=True)
    assert 'class="this-week"' not in page and '<section class="reported"' in page


def test_the_records_are_a_sub_line_of_keep_an_eye_on_led_by_a_clay_gbif_tag():
    got = TEMPLATES.get_template("_reported.html").render(
        sightings=[{"url": "https://www.gbif.org/x", "text": "Aphids: 4 UK records", "scientific": "Aphidoidea"}],
        reports=[],
    )  # fmt: skip
    assert got.lstrip().startswith(
        '<div class="reported-gbif"><span class="tag gbif">GBIF</span><ul'
    )
    rules = _sheet()
    assert "padding-top: 0" in rules[".answer-page .this-week > .watch + .reported"]
    tag = rules[".answer-page .reported-gbif .tag.gbif"]
    assert "background: var(--clay-bg)" in tag and "color: var(--clay)" in tag


def test_answer_top_css_is_inlined_scoped_and_uses_tokens_only():
    sheet = SHEET.read_text("utf-8")
    assert style._minify(sheet) in style.CSS  # inlined by style.py, no <link>
    for _, sel, body in _rules(sheet):
        for part in re.split(r",(?![^()]*\))", sel):  # not the commas inside :is()
            assert part.strip().startswith(".answer-page"), sel
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", body), sel
