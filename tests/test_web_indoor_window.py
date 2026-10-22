"""22 Oct (a gardener: "how do you tell light levels indoors?"): we can't, light indoors is
not measured (herbtwin.light). So an indoor answer asks where the plant sits, by which window
and how close, as quiet answer chips under "Tell us more"; indoors this takes the place of
the compass question, which only makes sense outdoors. The answer is kept in what was told
and said back on the refined answer; the advice reading it comes in its own PR."""

import json

import httpx
import pytest
import respx
from pydantic import ValidationError

from herbtwin.asks import questions_for
from herbtwin.note_facts import told_echo
from herbtwin.schemas import WINDOW_TEXT, Told
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.web.answer_text import plan_text
from tests.test_web import ADV, OBS, SAMPLE, _client, _first
from tests.test_web_answer_page import _render, _unsure_record
from tests.test_web_spot_questions import _answer
from tests.test_web_spot_questions import _client as _spot_client

LABELS = {
    "south_close": "South window, close",
    "east_west_close": "East or west window, close",
    "north_or_far": "North window, or a metre or more back",
    "no_window": "Away from any window",
}
FIELDSET = '<fieldset class="picks"><legend>Where is it?</legend>'


def _fieldset(page: str) -> str:
    return page.split(FIELDSET, 1)[1].split("</fieldset>", 1)[0]


def _refine_form(page: str) -> str:
    return page.split('<form class="refine"', 1)[1].split("</form>", 1)[0]


def test_told_takes_the_four_window_answers_and_nothing_else():
    assert WINDOW_TEXT == LABELS
    for v in LABELS:
        assert Told(window=v).window == v
        assert not Told(window=v).is_empty()  # a window alone is something to refine with
    for bad in ("south", "west", "", "South window, close"):
        with pytest.raises(ValidationError):
            Told(window=bad)
    assert Told().window is None


def test_indoors_asks_the_window_in_place_of_the_compass(tmp_path):
    rec = _unsure_record(tmp_path)
    assert rec.answer is not None and rec.observation is not None
    rec.answer.tell_me_key = "aspect"
    rec.observation.setting = "indoor"
    asks = questions_for(rec.answer, rec.observation, spot=True)
    assert "window" in asks and "aspect" not in asks
    # outdoors unchanged: the compass, and no window
    rec.observation.setting = "outdoor"
    asks = questions_for(rec.answer, rec.observation, spot=True)
    assert "aspect" in asks and "window" not in asks
    rec.observation.setting = "unknown"
    assert "window" not in questions_for(rec.answer, rec.observation, spot=True)


def _indoor(tmp_path):
    rec = _unsure_record(tmp_path)
    assert rec.answer is not None and rec.observation is not None
    rec.observation.setting = "indoor"
    return rec


def test_an_indoor_card_asks_where_it_is_with_four_quiet_chips_none_picked(tmp_path):
    rec = _indoor(tmp_path)
    page = _render(rec, asks=["window", "question"], spot_on=True)
    form = _refine_form(page)
    assert '<div class="part where' in form and FIELDSET in form
    chips = _fieldset(form)
    for v, text in LABELS.items():
        assert f'<input type="radio" name="window" value="{v}"><span>{text}</span>' in chips
    assert "checked" not in chips  # no default pick
    assert "data-compass" not in page  # no compass indoors
    # the shut line names it as a quick tap
    assert "1 quick tap: where it sits" in page


def test_a_told_window_shows_checked_on_the_next_render(tmp_path):
    rec = _indoor(tmp_path)
    rec.told = Told(window="east_west_close")
    chips = _fieldset(_render(rec, asks=["window", "question"]))
    assert 'value="east_west_close" checked>' in chips
    assert chips.count("checked") == 1


def test_the_window_does_not_change_the_rater_text(tmp_path):
    # the card sits outside .plan; the main card counts it as a quick question since the
    # advice reads it (tests/test_window_words.py)
    rec = _indoor(tmp_path)
    before = _render(rec, asks=["question"])
    after = _render(rec, asks=["window", "question"])
    assert plan_text(after) == plan_text(before)


@respx.mock
def test_the_outdoor_card_still_asks_the_compass_and_not_the_window(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, _ = _spot_client(tmp_path, spot=True)
    first, _ = _answer(c)
    assert "data-compass" in first.text
    assert 'name="window"' not in first.text and "Where is it?</legend>" not in first.text


def test_each_window_is_said_back_in_plain_words():
    def said(**kw):
        return told_echo(Told(**kw))

    assert said(window="south_close") == "You told us: by a south window, close"
    assert said(window="east_west_close") == "You told us: by an east or west window, close"
    assert said(window="north_or_far") == (
        "You told us: by a north window, or a metre or more back"
    )
    assert said(window="no_window") == "You told us: away from any window"
    # next to indoors, before the place and the soil
    assert said(setting="indoor", window="south_close", soil_feel="dry") == (
        "You told us: indoors; by a south window, close; soil dry"
    )


@respx.mock
def test_a_refine_with_a_window_keeps_it_says_it_back_and_shows_it_picked(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps({**OBS, "setting": "indoor"})], [json.dumps(ADV)] * 9)
    rid = _first(c)
    page = c.get(f"/answers/{rid}").text
    assert FIELDSET in page and "checked" not in _fieldset(page)
    r = c.post(f"/answers/{rid}/refine", data={"window": "south_close"})
    assert r.status_code == 200
    assert '<p class="told-echo">You told us: by a south window, close</p>' in r.text
    assert 'value="south_close" checked>' in _fieldset(r.text)
    # kept with what else is told on the next refine
    r = c.post(f"/answers/{rid}/refine", data={"window": "south_close", "soil_feel": "dry"})
    assert r.status_code == 200
    assert "You told us: by a south window, close; soil dry" in r.text


@respx.mock
def test_a_window_answer_we_do_not_know_is_refused_in_our_words(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps({**OBS, "setting": "indoor"})], [json.dumps(ADV)] * 6)
    rid = _first(c)
    r = c.post(f"/answers/{rid}/refine", data={"window": "west"})
    assert r.status_code == 400
    assert "Could not use where it sits. Check it and try again." in r.text


def test_the_window_question_reads_in_full_colour_not_the_bands_grey():
    # "Where it is" carries .where, which the band's muted chip row also uses
    from pathlib import Path

    from tests.test_web_answer_reveal import _rules

    css = Path("src/herbtwin/web/static/pages/answer.css").read_text()
    legend = [
        b for at, sel, b in _rules(css) if not at and sel == ".answer-page .refine .picks legend"
    ]
    assert legend and "color: var(--fg)" in legend[0]


def test_more_photos_keeps_the_window_told(tmp_path):
    rec = _indoor(tmp_path)
    rec.told = Told(window="north_or_far")
    page = _render(rec, asks=["window", "question"], more_photos_on=True)
    more = page.split('action="/answers/' + rec.record_id + '/photos"', 1)[1].split("</form>", 1)[0]
    assert '<input type="hidden" name="window" value="north_or_far">' in more


def test_no_window_question_beside_a_retake_or_a_no_cure_answer(tmp_path):
    # review: "Send a sharper photo" or a remove-it answer is not helped by the window
    from herbtwin.answer import NO_CURE_HEADLINE

    rec = _indoor(tmp_path)
    rec.answer.photo_issue = "blurry"
    assert "window" not in questions_for(rec.answer, rec.observation)
    rec.answer.photo_issue = None
    rec.answer.headline = NO_CURE_HEADLINE
    assert "window" not in questions_for(rec.answer, rec.observation)


def test_the_switch_never_carries_the_window(tmp_path):
    # Indoors to Outdoors drops the pick, so the echo never says "outdoors; by a window"
    rec = _indoor(tmp_path)
    rec.told = Told(window="south_close")
    page = _render(rec, asks=["window", "question"], spot_on=True)
    switch = page.split('<form class="note setting-switch"', 1)[1].split("</form>", 1)[0]
    assert 'name="window"' not in switch
