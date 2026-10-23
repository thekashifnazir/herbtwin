"""The answer's plan column as text, read off the real answer page: what a rater in the
Toloka clarity test sees in place of the page (a hand copy of the template went stale)."""

import json

import pytest

from herbtwin.web.answer_text import answer_page, plan_text
from herbtwin.web.app import create_app
from tests.fakes import follow
from tests.test_web import JPEG, OBS, _client
from tests.test_web_answer_page import ALSO, _answer

# offline: Open-Meteo answers "limit reached" (tests/conftest.py), never the real one
pytestmark = pytest.mark.usefixtures("open_meteo_down")


def test_the_plan_reads_in_the_page_order_with_its_own_words(tmp_path):
    text = plan_text(_answer(tmp_path))
    order = [
        "**TODAY**",
        "## Water it.",
        "The soil is dry and no rain is due.",
        "**How sure we are:** ",
        "This week",  # the panel's label (23 Oct answer-page critique, 4)
        "### Also do",
        "**Check for pests**",
        "### Keep an eye on",
    ]
    at = [text.find(t) for t in order]
    assert -1 not in at, [t for t, i in zip(order, at, strict=True) if i == -1]
    assert at == sorted(at)


def test_the_plan_leaves_out_buttons_scripts_and_the_other_blocks(tmp_path):
    text = plan_text(_answer(tmp_path))
    assert "<" not in text and "addEventListener" not in text
    assert "I did it" not in text  # a button a rater cannot press
    assert "Tell us more" not in text and "Ref " not in text  # blocks 2 and 3


def test_a_stored_record_renders_through_the_real_answer_route(tmp_path):
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ALSO)] * 3)
    page = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")})).text
    rid = page.split('action="/answers/')[1].split("/")[0]
    rec = c.app.state.answers.get(rid).latest
    # a fresh app that never saw the upload: the same plan, no request in flight
    again = answer_page(create_app(c.app.state.deps), rec)
    assert plan_text(again) == plan_text(page)


def test_hidden_parts_and_the_make_surer_links_stay_out():
    page = (
        '<div class="plan"><p class="sure"><strong>How sure we are<span class="sr-only">:</span></strong>'
        '<span class="badge check">Not sure, check first<span class="sr-only">.</span></span></p>'
        '<p class="make-surer"><a href="#refine">Make this surer: answer 2 quick questions</a></p>'
        '<div class="i-did" hidden><p class="thanks">Thanks for looking after me.</p></div></div>'
    )
    # the screen-reader colon and full stop join the word before them (21 Oct)
    assert plan_text(page) == "**How sure we are:** Not sure, check first."


def test_a_page_with_no_plan_is_an_error_not_an_empty_item():
    with pytest.raises(ValueError, match="no plan"):
        plan_text("<main><h2>Could not form advice</h2></main>")
