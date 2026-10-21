"""The answer page, decluttered (21 Oct, Kash: "a lot going on… actual plant picture is
tiny"): the photo big beside the main card, each ask said once, no filler, and "Tell us
more" as one tidy panel with one green button."""

import re

from herbtwin.web import style
from tests.test_web_answer_page import _full_plan, _render, _unsure_record
from tests.test_web_answer_reveal import _rules

CSS = (style.STATIC / "pages" / "answer.css").read_text(encoding="utf-8")


def _rule(selector: str, at_part: str = "") -> str:
    found = [
        b
        for at, s, b in _rules(CSS)
        if s == selector and (at_part in " ".join(at) if at_part else not at)
    ]
    assert found, selector
    return found[-1]


def test_your_photo_is_big_beside_the_main_card_not_a_thumbnail_in_the_band(tmp_path):
    page = _render(_full_plan(tmp_path))
    band = page.split('<div class="page-band">', 1)[1].split('<div class="answer-cols', 1)[0]
    assert "your-photo" not in band
    cols = page.split('<div class="answer-cols', 1)[1]
    # first in the columns: above the main card on a phone, beside it from 960px
    assert cols.index('class="your-photo') < cols.index('<div class="plan">')
    img = re.search(r'<img class="your-photo[^>]*>', cols).group(0)
    assert " hidden" in img and 'id="your-photo"' in img and 'alt="Your photo"' in img
    phone = _rule(".answer-page .answer-cols > .your-photo")
    assert "width: 100%" in phone and "aspect-ratio" in phone and "object-fit: cover" in phone
    # on a phone the photo takes the pull-up over the band, in the plan's or (ask-up) the
    # main card's place, so the two never both pull up
    narrow = ", ".join(
        s for at, s, b in _rules(CSS) if "max-width: 959px" in " ".join(at) and "margin-top: 0" in b
    )
    assert (
        ".answer-page .answer-cols.ask-up:has(> .your-photo:not([hidden])) .main-action" in narrow
    )
    assert ".answer-page .page-band + .answer-cols:has(> .your-photo:not([hidden])) .plan" in narrow
    wide = _rule(".answer-page .answer-cols > .your-photo", "min-width: 960px")
    assert "grid-column: 2" in wide and "grid-row: 1" in wide


def test_add_where_it_is_is_asked_once(tmp_path):
    page = _render(_unsure_record(tmp_path))
    # the one ask is the band's town box (21 Oct, Kash at rev 00049); no button in the card
    # saying it again, no second link under Keep an eye on, and no sentence beside the level
    assert page.count("We don't know where this is") == 1
    assert "Add where it is" not in page
    assert "Tell us where it is below" not in page
    assert 'name="place"' in page


def test_with_no_button_the_level_still_says_where_to_answer(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.answer.tell_me_key = "soil_feel"
    page = _render(rec, asks=["question"])  # nothing quick to answer: no Make-surer button
    assert 'Answer the <a href="#refine">question below</a> and we\'ll check again.' in page


def test_send_another_photo_is_offered_once(tmp_path):
    page = _render(_full_plan(tmp_path))
    assert page.count(">Send another photo</a>") == 1
    # at the end of the plan, in What next, not again at the foot of the details
    assert ">Send another photo</a>" in page.split('id="next-step"', 1)[1].split("</section>")[0]


def test_the_two_buttons_need_no_explainer_line(tmp_path):
    page = _render(_full_plan(tmp_path))
    assert "we redo the advice" not in page and "ask-hint" not in page


def test_keep_an_eye_on_hides_when_there_is_nothing_to_watch(tmp_path):
    rec = _full_plan(tmp_path)
    rec.answer.watch = "Send a new photo if it changes."
    assert '<section class="watch"' not in _render(rec)
    rec.answer.watch = "• Grey fuzz under the leaves. Seen it? Send a new photo."
    assert '<section class="watch"' in _render(rec)


def test_tell_us_more_is_one_panel_with_one_green_button(tmp_path):
    page = _render(_unsure_record(tmp_path))
    panel = page.split('id="chat"', 1)[1].split("</section>", 1)[0]
    assert len(re.findall(r'class="[^"]*\bprimary\b', panel)) == 1
    assert (
        '<button class="big quiet ask-chat" type="button" hidden>Ask about this plant</button>'
        in panel
    )
    # one inked card, like the plan's cards
    assert "border: 1.5px solid" in _rule(
        ".answer-page :is(.main-action, .also, .dont, .watch, .ask)"
    )


def test_a_page_without_advice_still_shows_your_photo(tmp_path):
    # declutter review: the photo moved in with the plan, and the no-advice page lost it; the
    # tab copy was then dropped, so keeping the answer kept no photo
    rec = _unsure_record(tmp_path)
    rec.answer = None
    page = _render(rec, failed={"advise": "no usable reply"})
    img = re.search(r'<img class="your-photo ink solo"[^>]*>', page).group(0)
    assert 'id="your-photo"' in img and " hidden" in img


def test_the_level_line_has_no_stray_space(tmp_path):
    # #331 review: "Mostly: …. " kept its space when nothing followed it
    page = _render(_unsure_record(tmp_path))
    said = re.search(r'class="badge-line">.*?</span><span>(.*?)</span>', page, flags=re.S).group(1)
    assert said.startswith("Mostly: ") and said == said.strip() and "  " not in said
