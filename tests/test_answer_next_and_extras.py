"""The answer page's end, part B of the 23 Oct redesign (Kash: "boxes after boxes", as About):
What next as a line of stops, the shops as a lilac Tavily strip, What could grow here as one
sky line. The functions stay: the photo picker, "I did it" and the sign-in."""

from herbtwin.web import style
from tests.test_web_answer_page import _full_plan, _render


def _next(page: str) -> str:
    return page.split('<section class="next-step"', 1)[1].split("</section>", 1)[0]


def test_what_next_is_a_line_of_three_stops_in_order(tmp_path):
    rec = _full_plan(tmp_path)
    rec.answer.do[0] = rec.answer.do[0].model_copy(update={"action": "water"})
    nxt = _next(_render(rec, more_photos_on=True, accounts=True))
    line = nxt.split('<ol class="next-line">', 1)[1].split("</ol>", 1)[0]
    stops = ["Today", "In a few days", "For a surer answer"]
    at = [line.index(f'<p class="next-when">{s}</p>') for s in stops]
    assert at == sorted(at)
    # each function in its stop: "I did it", a new photo, the more-photos picker
    assert line.index('id="i-did"') < at[1] < line.index('href="/"') < at[2]
    assert line.index('class="more-photos"') > at[2] and 'type="file"' in line
    # Today's stop waits for the script, as "I did it" does: no empty stop without one
    assert '<li class="next-today" hidden>' in line and "stop.hidden = false" in nxt
    # the sign-in is one plain line after the stops, not inside them
    assert nxt.index("</ol>") < nxt.index('<p class="keep">')
    assert "ink" not in nxt.split(">", 1)[0]  # no card round it


def test_i_did_it_is_a_secondary_button_not_lime():
    css = style.CSS
    assert (
        ".answer-page .next-step .i-did > button { background: var(--soft-strong); color: var(--fg);"
        " border-color: var(--soft-line); }" in css
    )
    # the later rule wins its tie with answer.css's lime one
    assert css.index("background: var(--lime); color: var(--lime-fg)") < css.index(
        ".answer-page .next-step .i-did > button { background: var(--soft-strong)"
    )


def test_the_shops_are_a_lilac_strip_and_grow_here_a_sky_line():
    css = style.CSS
    assert (
        ".answer-page .extras { padding: 14px 18px; border: 0; box-shadow: none; background: var(--lilac); }"
        in css
    )
    assert (
        ".answer-page .extras h2 { margin: 0 0 6px; font-size: 18px; color: var(--lilac-fg); }"
        in css
    )
    assert "background: var(--sky); color: var(--fg); text-decoration: none; }" in css
    assert ".answer-page .extras a:not(.button) { color: var(--fg); }" in css  # AA on lilac
    # each shop row: the thing, an arrow (an escape, never the character), the page, the shop
    assert '.answer-page .extras .shop-links > li > .shop-what::after { content: " \\2192";' in css
