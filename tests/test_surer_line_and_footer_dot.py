"""Two small fixes (23 Oct): How sure's "What makes it surer" no longer asks how the soil
feels once it was told (on the wait page, say), and the footer keeps its middle dot with the
Open-Meteo link when the line wraps on a phone (Kash at 390: "© 2026 Kashif Nazir ·" ended
the first line)."""

import re

from herbtwin.schemas import Told
from tests.test_web_answer_page import _full_plan, _render


def _surer(page: str) -> str:
    line = page.split("What makes it surer:</strong>", 1)[1].split("</p>", 1)[0]
    return re.sub(r"<[^>]+>", "", line).strip()


def test_with_no_question_left_it_asks_for_the_soil_only_until_told(tmp_path):
    rec = _full_plan(tmp_path)
    ask = _surer(_render(rec, asks=["question"]))
    assert (
        ask
        == "tell us what you see, or how the soil feels, in Tell us more and we'll check the advice again."
    )
    rec.told = Told(soil_feel="damp")
    told = _surer(_render(rec, asks=["question"]))
    assert told == "tell us what you see in Tell us more and we'll check the advice again."


def test_the_footer_dot_goes_with_the_link():
    from herbtwin.web.app import TEMPLATES

    footer = TEMPLATES.get_template("_maker.html").render()
    assert (
        '© 2026 Kashif Nazir <span class="foot-credit">· <a href="https://open-meteo.com/"'
        in footer
    )
    assert footer.split('<span class="foot-credit">', 1)[1].split("</span>", 1)[0].endswith("</a>")
    from herbtwin.web import style

    # one box that doesn't break: the link is inline-flex (a 44px tap), so a no-break space
    # before it was not enough
    assert ".foot-credit { white-space: nowrap; }" in style.CSS
