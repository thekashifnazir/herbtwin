"""The answer page shows the photo you sent (17 Oct review: "never shows the user's own
photo"), from the browser tab's own copy: the server keeps nothing new. Also the honest
illustration captions and the home example's autumn advice."""

import re

import pytest

from herbtwin.web.app import TEMPLATES
from tests.test_web import _client
from tests.test_web_answer_page import _answer

# offline: Open-Meteo answers "limit reached" (tests/conftest.py), never the real one
pytestmark = pytest.mark.usefixtures("open_meteo_down")


def test_the_answer_has_a_place_for_your_photo(tmp_path):
    page = _answer(tmp_path)
    rid = page.split('action="/answers/')[1].split("/")[0]
    # big, beside the main card, not in the band (21 Oct, Kash: test_answer_declutter)
    cols = page.split('<div class="answer-cols', 1)[1].split('<div class="plan">')[0]
    img = re.search(r'<img class="your-photo[^>]*>', cols)
    assert img is not None
    # hidden until the tab has a copy, so no broken image; tied to this answer's id
    assert " hidden" in img.group(0) and f'data-answer="{rid}"' in img.group(0)
    assert 'alt="Your photo"' in img.group(0)


def test_the_answer_page_claims_the_tabs_photo_for_its_own_id(tmp_path):
    page = _answer(tmp_path)
    assert '"herbtwin-photo-pending"' in page
    assert '"herbtwin-photo:" + img.dataset.answer' in page
    # only a JPEG data URL is ever shown: nothing from storage becomes a remote src
    assert 'src.startsWith("data:image/jpeg;base64,")' in page


def test_the_home_form_keeps_a_small_copy_only_for_the_plant_answer(tmp_path):
    home = _client(tmp_path, [], []).get("/").text
    assert 'sessionStorage.setItem("herbtwin-photo-pending"' in home
    # the spot button posts elsewhere and gets no answer page to show it on
    assert 'by.getAttribute("formaction")' in home


def test_the_privacy_page_says_the_photo_copy_stays_in_the_tab(tmp_path):
    page = _client(tmp_path, [], []).get("/privacy").text
    assert "small copy kept in your own browser tab" in page


def test_the_home_illustration_says_it_is_drawn_not_forecast(tmp_path):
    home = _client(tmp_path, [], []).get("/").text
    cap = home.split("<figcaption>")[1].split("</figcaption>")[0]
    # 19 Oct small-print plan: said in fewer words, but still never read as a forecast
    assert "An illustration, not a prediction" in cap
    assert "your own answer says it in words" in cap


def test_the_home_example_does_not_feed_basil_in_autumn(tmp_path):
    # the example is a cold autumn week with 3 °C nights: feeding then is wrong advice
    home = _client(tmp_path, [], []).get("/").text
    sample = home.split('class="card home-sample"')[1].split("</article>")[0]
    assert "Feed it" not in sample
    assert "Pick the best leaves now" in sample


DROP = 'try { sessionStorage.removeItem("herbtwin-photo-pending"); } catch {}'


def test_other_pages_drop_a_left_over_photo_copy(tmp_path):
    # a send abandoned part way (an error page, the privacy page, My plants) must not
    # leave the copy for an older answer opened later (review, 17 Oct)
    c = _client(tmp_path, [], [])
    assert DROP in c.get("/privacy").text and DROP in c.get("/").text
    assert DROP not in _answer(tmp_path)  # the answer page claims it instead


def test_the_plant_choice_on_the_way_to_the_answer_keeps_the_copy():
    t = TEMPLATES.get_template("choose_plant.html")
    assert "".join(t.blocks["photo_copy"](t.new_context({}))).strip() == ""
