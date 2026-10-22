"""19 Oct home pass (the private working repo's `2026-10-19-judge-home-pass.md`), PR 1: the home page's
order and words. The samples sit by the photo card, the question waits for a photo, and the
example reads as rows."""

import re

from herbtwin.web import style
from tests.test_web_home import _home
from tests.test_web_spot import _client as _spot_client


def _spot_home(tmp_path) -> str:
    return _spot_client(tmp_path)[0].get("/").text


def test_the_samples_are_chips_right_under_the_photo_card(tmp_path):
    home = _spot_home(tmp_path)
    form = home.split('<form class="home-form"', 1)[1].split("</form>", 1)[0]
    at = [form.index(x) for x in ('class="home-photo"', 'class="home-chips"', 'class="home-where"')]
    assert at == sorted(at)
    chips = form.split('class="home-chip-row"', 1)[1].split("</div>", 1)[0]
    labels = re.findall(
        r'<a class="home-pick"[^>]*><img [^>]*alt=""[^>]*><span>([^<]+)</span>', chips
    )
    assert labels == [
        "Parsley", "Basil flowering", "Rosemary beetles", "Coriander", "Basil mildew", "Raised bed",
    ]  # fmt: skip
    assert "No herb to hand? Try one of ours:" in form
    # the big grid at the foot is gone: one place for the samples
    assert 'class="home-samples"' not in home and "home-sample-row" not in style.CSS


def test_the_chips_scroll_sideways_on_a_phone_and_wrap_on_a_wide_screen():
    css = style.CSS
    assert ".home-page .home-chip-row { display: flex; flex-wrap: wrap;" in css
    phone = css.split("@media (max-width: 720px) {", 1)[1]
    assert "home-chip-row { flex-wrap: nowrap; overflow-x: auto;" in phone


def test_home_asks_no_question_before_the_photo_goes(tmp_path):
    # 19 Oct, Kash's walk: photo first, no questions; the answer page's chat takes them
    # (the server still takes a `question` field, so an old form still works: test_web.py)
    home = _spot_home(tmp_path)
    form = home.split('<form class="home-form"', 1)[1].split("</form>", 1)[0]
    assert 'name="question"' not in form and "Anything to ask" not in home
    assert "home-question" not in home and "home-question" not in style.CSS


def test_the_example_reads_as_3_rows_and_the_twin_is_named_once(tmp_path):
    home = _home(tmp_path)
    more = home.split('<ul class="home-sample-more">', 1)[1].split("</ul>", 1)[0]
    rows = re.findall(r'<li><span class="tag[^"]*">([^<]+)</span> <span>([^<]+)</span></li>', more)
    assert [t.replace("&#39;", "'") for t, _ in rows] == ["Also do", "Don't", "Keep an eye on"]
    assert "Water it late in the day." in more
    # the twin is named once, in the hero's lead (the How it works cards went, 22 Oct walk)
    assert home.count("plant's <strong>twin</strong>") == 1


def test_home_drops_its_sign_in_line_and_the_long_hints(tmp_path):
    home = _home(tmp_path)
    assert "to remember your plants" not in home and "Signed in as" not in home
    assert "A herb or garden plant, close up. JPEG or PNG." in home
    where = home.split('<fieldset class="home-where">', 1)[1].split("</fieldset>", 1)[0]
    where = where.replace("&#39;", "'")
    assert "Or we use your photo's own location" not in where  # the page now says which
