"""A3 (22 Oct, Kash): the quick questions in "Tell us more" are quiet grey answer chips, like
the follow-up chips under a chat answer, and tapping an answer to each sends the refine.
Radios underneath, so without a script they still work, with the green "Check the advice
again" under them as on main. The shut line is a card to come to; Ask is a chat box."""

import re

from herbtwin.schemas import Told
from herbtwin.web import style
from tests.test_tell_us_more_sections import ALL_ASKS, _form, _panel
from tests.test_web_answer_page import _render, _unsure_record
from tests.test_web_answer_reveal import _rules

CSS = (style.STATIC / "pages" / "answer.css").read_text(encoding="utf-8")
GREEN = r'class="[^"]*\bprimary\b'


def _soil(tmp_path):
    rec = _unsure_record(tmp_path)
    rec.answer.tell_me_key, rec.answer.tell_me = "soil_feel", "Push a finger 2 cm into the soil."
    return rec


def test_the_quick_questions_are_answer_chips_on_radios_not_selects(tmp_path):
    rec = _soil(tmp_path)
    rec.told = Told(last_watered="1_2_days")  # what was told is picked again
    page = _render(rec, asks=ALL_ASKS)
    changed = _panel(page).split('<div class="part changed', 1)[1].split('<div class="part ', 1)[0]
    assert "<select" not in changed
    for q, legend in (
        ("soil_feel", "How does the soil feel 2 cm down?"),
        ("last_watered", "When did you last water it?"),
        ("changed", "Anything changed recently?"),
    ):
        group = changed.split(f"<legend>{legend}</legend>", 1)[1].split("</fieldset>", 1)[0]
        assert '<fieldset class="picks">' in changed.split(f"<legend>{legend}</legend>", 1)[0]
        assert re.findall(r'<label><input type="radio" name="(\w+)"', group) == [q] * len(
            re.findall("<label>", group)
        )
    assert '<input type="radio" name="last_watered" value="1_2_days" checked>' in changed
    assert '<input type="radio" name="soil_feel" value="dry"><span>dry</span></label>' in changed


def test_check_stays_green_right_under_the_chips(tmp_path):
    # as on main (22 Oct, Kash on A3 round 2): green, full width, right under the questions;
    # their taps send it too (data-picks), and the box is Ask's
    form = _form(_render(_soil(tmp_path)))
    groups, part = form.split('<div class="part chat', 1)
    assert groups.rstrip().endswith(
        '<div class="actions send" data-picks>\n'
        '        <button class="primary big" type="submit">Check the advice again</button>\n'
        "      </div>"
    )
    assert groups.index('<fieldset class="picks">') < groups.index("Check the advice again")
    assert "Check the advice again" not in part


def test_a_tap_that_answers_every_chip_question_sends_the_refine(tmp_path):
    page = _render(_soil(tmp_path))
    script = page.split('const picks = [...form.querySelectorAll("fieldset.picks")];', 1)[1]
    script = script.split("</script>", 1)[0]
    # only when the chips are the groups' only fields: with a send under them, it waits
    assert 'if (picks.length && form.querySelector(".actions.send[data-picks]")) {' in script
    assert 'if (picks.every((f) => f.querySelector("input:checked"))) check.click();' in script
    # the arrow keys move between chips without sending
    assert 'keyed = e.key.startsWith("Arrow");' in script and "if (keyed ||" in script


def _rule(selector: str) -> str:
    # a selector list counts: a picked compass chip shares the picked chip's rule (22 Oct)
    found = [b for at, s, b in _rules(CSS) if selector in s.split(", ") and not at]
    assert found, selector
    return found[-1]


def test_the_chips_are_quiet_grey_pills_and_the_picked_one_has_a_tick():
    chip = _rule(".answer-page .refine .picks label")
    assert "background: var(--muted)" in chip and "border: 1px solid var(--border)" in chip
    assert "border-radius: var(--pill)" in chip and "color: var(--fg)" in chip
    assert "shadow" not in chip and "primary" not in chip
    picked = _rule(".answer-page .refine .picks label:has(input:checked)")
    assert "var(--fg)" in picked and "primary" not in picked
    assert 'content: "\\2713"' in _rule(
        ".answer-page .refine .picks label:has(input:checked)::before"
    )
    # the radio is out of sight but still takes the keyboard; its focus shows on the chip
    assert "opacity: 0" in _rule(".answer-page .refine .picks input")
    assert "outline" in _rule(".answer-page .refine .picks label:has(input:focus-visible)")


def _summary(page: str) -> str:
    return _panel(page).split("<summary>", 1)[1].split("</summary>", 1)[0]


def test_the_shut_line_is_a_card_saying_what_it_takes(tmp_path):
    # 22 Oct, Kash on A3: "obvious as something for someone to come to"
    said = _summary(_render(_soil(tmp_path)))
    assert '<span class="tm-icon" aria-hidden="true"><svg' in said
    assert '<span class="tm-title">Want a more exact answer?</span>' in said
    sub = '<span class="tm-sub">2 quick taps: how the soil feels and when you last watered</span>'
    assert sub in said
    three = _summary(_render(_soil(tmp_path), asks=ALL_ASKS))
    assert "3 quick taps: how the soil feels, when you last watered and what&#39;s changed" in three
    alone = _summary(_render(_soil(tmp_path), asks=["question"]))
    assert "Tell us more, or ask anything about this plant" in alone
    # tinted, never a filled button: the one green stays the card's
    line = _rule(".answer-page .tell-more > summary")
    assert "background: var(--soft)" in line and "color: var(--fg)" in line
    assert "primary" not in line
    assert "font: 700" in _rule(".answer-page .tell-more .tm-title")


def test_ask_is_a_chat_box_with_its_send_inside(tmp_path):
    form = _form(_render(_soil(tmp_path)))
    box = form.split('<div class="composer">', 1)[1].split("</div>", 1)[0]
    assert '<textarea name="question"' in box and 'class="quiet ask-chat"' in box
    assert '<span class="sr-only">Ask anything about this plant' in box  # its name, unseen
    assert "Ask anything about this plant, e.g. What if I move it inside?" in box
    # the starters sit over it until the first question (25 Oct, Kash)
    assert form.index('<div class="starters" hidden>') < form.index('<div class="composer">')
    assert "border-radius: 24px" in _rule(".answer-page .refine .composer textarea")
    send = _rule(".answer-page .refine .composer .ask-chat")
    assert "position: absolute" in send and "right: 10px" in send and "bottom: 10px" in send
    # ink, not green, unless the script makes it the page's one green (data-lead)
    ink = _rule(".answer-page .refine .composer .ask-chat:not(.primary)")
    assert "background: var(--fg)" in ink and "primary" not in ink.replace(":not(.primary)", "")
