"""The answer page's end, part B of the 23 Oct redesign (Kash: "boxes after boxes", as About):
What next as a line of stops, the shops as a lilac Tavily strip, What could grow here as one
sky line. The functions stay: the photo picker, "I did it" and the sign-in."""

from herbtwin.web import style
from tests.test_web_answer_page import _full_plan, _render


def _next(page: str) -> str:
    return page.split('<section class="next-step"', 1)[1].split("</section>", 1)[0]


def test_what_next_is_a_line_of_three_numbered_steps_each_with_its_button(tmp_path):
    # 24 Oct (Kash: "pulling people in to click it", then the page as a whole): the 23 Oct
    # line of stops kept, each button under its own step; the photo picker behind its button
    rec = _full_plan(tmp_path)
    rec.answer.do[0] = rec.answer.do[0].model_copy(update={"action": "water"})
    nxt = _next(_render(rec, more_photos_on=True, accounts=True))
    line = nxt.split('<ol class="next-line">', 1)[1].split("</ol>", 1)[0]
    stops = ["Today", "In a few days", "For a surer answer"]
    at = [line.index(f'<p class="next-when">{s}</p>') for s in stops]
    assert at == sorted(at)
    # each function in its step: "I did it", a new photo, the picker behind its button
    assert line.index('id="i-did"') < at[1] < line.index('href="/"') < at[2]
    picker = line.split('<details class="next-more"><summary>Add 1 or 2 photos</summary>', 1)[1]
    assert 'class="more-photos"' in picker and 'type="file"' in picker
    # Today's step waits for the script, as "I did it" does: no empty step without one
    assert '<li class="next-today" hidden>' in line and "stop.hidden = false" in nxt
    assert 'box.closest(".next-step").querySelector(".next-today")' in nxt
    # the sign-in is one plain line after the steps, not inside them; no card round it
    assert nxt.index("</ol>") < nxt.index('<p class="keep">')
    assert "ink" not in nxt.split(">", 1)[0]


def test_the_steps_are_numbered_and_the_heading_matches_how_we_worked_it_out():
    css = style.CSS
    assert "counter-reset: step;" in css and "content: counter(step);" in css
    assert ".answer-page .next-line > li[hidden] { display: none; }" in css
    assert (
        ".answer-page .next-step h2 { margin: 8px 0 16px; font: 700 26px/1.12 var(--display);"
        " letter-spacing: -0.015em; color: var(--fg); }" in css
    )
    assert ".answer-page .next-step { padding: 0; border: 0;" in css  # no box: after the answer


def test_what_next_buttons_share_one_secondary_style_not_lime():
    # 24 Oct, the page as a whole: three button styles side by side became one, the photo
    # button's green outline; the later rule wins its tie with answer.css's lime one
    css = style.CSS
    rule = (
        ".answer-page .next-step :is(.i-did > button, a.button.quiet) { background: var(--card);"
        " color: var(--primary); border: 1.5px solid var(--primary); font-weight: 700; }"
    )
    assert rule in css
    assert css.index("background: var(--lime); color: var(--lime-fg)") < css.index(rule)
    # on What next, not only its line: a remove-it answer has no line (review of #521); with
    # its own hover, which the rule above would otherwise mask
    assert (
        ".answer-page .next-step :is(.i-did > button, a.button.quiet):hover { background: var(--soft); }"
        in css
    )


def test_the_photo_button_is_no_fold_box_and_the_month_card_clears_the_questions():
    # 24 Oct review of the screenshots: the generic details box drew round the button, and
    # the month's card, moved beside the plan, touched the questions' card above it
    css = style.CSS
    assert (
        ".answer-page .next-step .next-more { margin: 0; padding: 0; border: 0; border-radius: 0;"
        " background: none; box-shadow: none; }" in css
    )
    assert ".answer-page .side > :is(.indoor-now, .outdoor-now) { margin-top: 20px; }" in css
