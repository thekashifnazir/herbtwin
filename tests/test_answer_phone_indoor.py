"""The answer page's integration pass (23 Oct answer-page critique, 8, 10 and 11, Kash:
"sounds great"): on a phone the chat sits right after This week and Compare right after the
twin pictures; after a check again the "Changed… Was:" note is a small strip above the
headline; indoors one line under how sure (the windows, chips here until 25 Oct, are now
asked in Tell us more);
and with no This-week row, GBIF's records keep a card of their own."""

import html
import re
from pathlib import Path

from herbtwin.schemas import WINDOW, WINDOW_TEXT, Told
from herbtwin.web import style
from herbtwin.web.answer_text import plan_text
from tests.test_web_answer_page import _full_plan, _render
from tests.test_web_answer_reveal import _rules

PAGES = Path(__file__).parents[1] / "src/herbtwin/web/static/pages"
PHONE = PAGES / "answer_phone.css"
INDOOR = PAGES / "answer_indoor.css"


def _phone() -> dict[str, str]:
    """answer_phone.css's rules under 960px, selector to body."""
    rules = _rules(PHONE.read_text("utf-8"))
    return {s: b for at, s, b in rules if at == ("@media (max-width: 959px)",)}


def _order(rules: dict[str, str], sel: str) -> int:
    return int(re.search(r"order: (\d+)", rules[sel]).group(1))


# ---------- 8 and 10: the phone order ----------


def test_on_a_phone_compare_follows_the_twin_and_the_chat_follows_this_week():
    # since 23 Oct Compare is in the twin's section with the twin pictures: one place
    rules = _phone()
    order = [
        _order(rules, ".answer-page .answer-cols .main-action, .answer-page .answer-cols > .plan > .came-from"),
        _order(rules, ".answer-page .answer-cols > :is(.your-photo, .your-more)"),
        _order(rules, ".answer-page .answer-cols > .plan > :is(.seen-problem, .twin-sec)"),
        _order(rules, ".answer-page .answer-cols > .plan > :is(.this-week, .reported)"),
        _order(rules, ".answer-page .answer-cols > .side > #chat"),
        _order(rules, ".answer-page .answer-cols > .plan > *"),  # the rest of the plan
        _order(rules, ".answer-page .answer-cols > .side > *, .answer-page .answer-cols > .side > .details > *"),
    ]  # fmt: skip
    assert order == sorted(order) and len(set(order)) == len(order), order


def test_the_columns_and_how_we_worked_it_out_open_into_one_list_only_on_a_phone():
    rules = _phone()
    flat = rules[
        ".answer-page .answer-cols > :is(.plan, .side), .answer-page .answer-cols > .side > .details"
    ]
    assert "display: contents" in flat
    assert "flex-direction: column" in rules[".answer-page .answer-cols"]
    # nothing in the sheet outside the phone width: the desktop columns are as they were
    outside = [s for at, s, _ in _rules(PHONE.read_text("utf-8")) if not at]
    assert outside == []


def test_asked_low_the_questions_stay_under_the_card():
    rules = _phone()
    assert _order(rules, ".answer-page .answer-cols.ask-up > .side > #chat") == 1


def test_the_card_still_pulls_up_over_the_band_without_its_column():
    # the plan's pull-up is lost when it opens into the list: the card takes it
    rules = _phone()
    card = rules[".answer-page .page-band + .answer-cols .main-action"]
    assert "margin-top: -48px" in card and "position: relative" in card


def test_compare_is_in_the_plan_and_the_chat_in_the_side_column_in_the_markup():
    # the chat's move is the phone's order only: on a desktop it stays in the side column.
    # Compare moved in the markup (23 Oct, Kash: the twin front and centre): in the plan, in
    # the twin's section; only a no-cure answer's folded line stays in How we worked it out
    src = (Path(__file__).parents[1] / "src/herbtwin/web/templates/result.html").read_text()
    side = src.index('<div class="side">')
    assert side < src.index('<section class="ask chat" id="chat"')
    assert src.index('<div class="compare ts-panel">') < side
    assert side < src.index('<section class="details"') < src.index('<details class="compare')


# ---------- 11: the strip and the window chips ----------


def test_changed_after_a_check_again_is_a_small_strip_above_the_headline(tmp_path):
    rec = _full_plan(tmp_path)
    rec.refined_from = "Bring it indoors."
    rec.told = Told(setting="indoor")
    head = _render(rec).split('<div class="head">', 1)[1].split('<h2 id="main-action">', 1)[0]
    assert (
        '<p class="checked">Changed after what you told us. Was: <s>Bring it indoors.</s></p>'
        in head
    )
    strip = {s: b for _, s, b in _rules(INDOOR.read_text("utf-8"))}[
        ".answer-page .main-action .head .checked"
    ]
    for say in ("display: inline-block", "background: var(--card)", "font: 600 16px"):
        assert say in strip, say


def _indoor(tmp_path):
    rec = _full_plan(tmp_path)
    rec.observation.setting = "indoor"
    rec.answer.compare = []
    return rec


def test_indoors_the_windows_are_picks_in_tell_us_more(tmp_path):
    # 25 Oct, Kash: out of the card and into Tell us more, under Where it is, as outdoors
    # asks which way it faces; the same `window` field of the one refine form
    rec = _indoor(tmp_path)
    rec.told = Told(setting="indoor", soil_feel="dry")
    page = _render(rec, asks=["soil_feel", "last_watered", "window", "question"])
    card = page.split('<section class="card main-action"', 1)[1].split("</section>", 1)[0]
    assert "window-chip" not in page and 'name="window"' not in card
    form = page.split('<form class="refine"', 1)[1].split("</form>", 1)[0]
    assert (
        f'action="/answers/{rec.record_id}/refine">'
        in page.split('<form class="refine"', 1)[1][:80]
    )
    picks = re.findall(
        r'<input type="radio" name="window" value="([a-z_]+)"><span>([^<]+)</span>', form
    )
    assert [v for v, _ in picks] == list(WINDOW)  # every window, in the questions' order
    assert [html.unescape(t) for _, t in picks] == list(WINDOW_TEXT.values())
    # what else was told rides along in the same form
    assert '<input type="hidden" name="setting" value="indoor">' in form
    # quiet picks, never a second green press: the answer chips' own look
    assert '<fieldset class="picks"><legend>Pick the nearest</legend>' in form
    assert "indoor-light .window-chip" not in INDOOR.read_text("utf-8")


def test_the_rater_text_never_reads_the_chips(tmp_path):
    text = plan_text(_render(_indoor(tmp_path)))
    for words in WINDOW_TEXT.values():
        assert words not in text, words


# ---------- the solo GBIF card (review of #489) ----------


def test_with_no_this_week_row_the_records_keep_their_own_card(tmp_path):
    rec = _full_plan(tmp_path)
    rec.answer.do = rec.answer.do[:1]
    rec.answer.dont = None
    rec.answer.watch = None
    page = _render(rec, reported_on=True)
    assert 'class="this-week"' not in page and '<section class="reported"' in page
    card = next(
        b for at, s, b in _rules((PAGES / "answer.css").read_text("utf-8"))
        if s == ".answer-page .reported" and not at
    )  # fmt: skip
    for say in (
        "border: 1.5px solid var(--fg)",
        "box-shadow: 5px 5px 0 var(--ink-shadow)",
        "background: var(--card)",
    ):
        assert say in card, say
    # the panel's flattening applies inside the panel only
    flat = [
        s
        for _, s, b in _rules((PAGES / "answer_top.css").read_text("utf-8"))
        if "box-shadow: none" in b
    ]
    assert flat and all(".this-week >" in s for s in flat), flat


def test_the_new_sheets_are_inlined_scoped_and_use_tokens_only():
    for sheet in (PHONE, INDOOR):
        text = sheet.read_text("utf-8")
        assert style._minify(text) in style.CSS, sheet.name  # no <link>
        for _, sel, body in _rules(text):
            for part in re.split(r",(?![^()]*\))", sel):
                assert part.strip().startswith(".answer-page"), (sheet.name, sel)
            assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", body), (sheet.name, sel)
