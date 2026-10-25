"""19 Oct (Kash): the site should say plainly that the forecast and the twin test are for
outdoor plants, and that an indoor answer is for room conditions."""

import json
import re

import httpx
import respx

from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.web import style
from tests.test_web import ADV, OBS, SAMPLE, _client, _first
from tests.test_web_answer_page import _unsure_record
from tests.test_web_home import _home
from tests.test_web_plant_face import _page

# the band's note until 25 Oct; the card's one indoor line says why there is less now
OLD_NOTE = "Indoors: advice for room conditions, without the forecast test."
WHY = "Indoor herbs get a simpler answer: there's no weather to test choices against."


def test_home_leaves_indoors_or_out_to_the_photo(tmp_path):
    # 19 Oct, Kash's walk: the form's "Outdoors: ... / Indoors: ..." lines went; indoors or
    # out is read from the photo (observe's `setting`), and the answer page says which
    home = _home(tmp_path)
    where = home.split('<fieldset class="home-where">', 1)[1].split("</fieldset>", 1)[0]
    assert "<strong>Outdoors:</strong>" not in where and "<strong>Indoors:</strong>" not in where
    assert "home-in-out" not in home and "home-in-out" not in style.CSS


def test_an_indoor_answer_says_so_under_where_it_grows(tmp_path):
    rec = _unsure_record(tmp_path)
    assert rec.observation is not None and rec.answer is not None
    rec.observation.setting = "indoor"
    rec.answer.compare = []
    page = _page(rec)
    # 25 Oct, Kash ("understand why they have less"): said once, in the card's indoor line
    # (test_web_indoor_light_ask), not again on the band
    assert "indoor-note" not in page and OLD_NOTE not in page
    card = page.split('<section class="card main-action"', 1)[1].split("</section>", 1)[0]
    assert page.count(WHY) == 1 and WHY in card
    # judge walk of #272: an empty Compare that opened to "Not compared" is hidden; the card's
    # indoor line already says there is no weather to test choices against
    assert "Compare all choices" not in page and "Not compared" not in page


def test_an_outdoor_answer_has_no_indoor_note(tmp_path):
    rec = _unsure_record(tmp_path)
    assert rec.observation is not None and rec.answer is not None
    for setting in ("outdoor", "unknown"):
        rec.observation.setting = setting
        rec.answer.compare = []
        page = _page(rec)
        assert "indoor-note" not in page and "it is indoors" not in page, setting
        # no place, no forecast: no empty Compare; the band asks where it is instead
        assert "Compare all choices" not in page and "No 2-week forecast" not in page
        assert "We don't know where this is: add a town for weather-checked advice." in page


@respx.mock
def test_the_switch_reruns_the_advice_indoors_then_outdoors(tmp_path):
    # 19 Oct (Kash): the read can call a pot on a sill outdoors; the switch re-runs the
    # advice with the setting forced, and indoors skips the forecast (pipeline weather_missing)
    weather = respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps({**OBS, "setting": "outdoor"})], [json.dumps(ADV)] * 9)
    rid = _first(c)
    page = c.get(f"/answers/{rid}").text
    switch = page.split('<form class="note setting-switch"', 1)[1].split("</form>", 1)[0]
    assert '<span class="chip setting">Outdoors</span>' in page
    assert 'name="setting" value="indoor"' in switch
    assert ">Redo for indoors</button>" in switch
    fetched = weather.call_count
    r = c.post(f"/answers/{rid}/refine", data={"setting": "indoor"})
    assert r.status_code == 200
    assert WHY in r.text and "Compare all choices" not in r.text
    assert weather.call_count == fetched  # indoors: no forecast asked for
    switch = r.text.split('<form class="note setting-switch"', 1)[1].split("</form>", 1)[0]
    assert '<span class="chip setting">Indoors (you said)</span>' in r.text
    assert 'name="setting" value="outdoor"' in switch
    # the next refine keeps it: the setting rides along with what else was told
    refine = r.text.split('<form class="refine"', 1)[1].split("</form>", 1)[0]
    assert '<input type="hidden" name="setting" value="indoor">' in refine
    r = c.post(f"/answers/{rid}/refine", data={"setting": "outdoor"})
    assert r.status_code == 200 and WHY not in r.text and "it is indoors" not in r.text
    assert "Outdoors (you said)" in r.text


@respx.mock
def test_the_window_picked_in_tell_us_more_checks_the_advice_again(tmp_path):
    # 25 Oct, Kash: the window is asked in Tell us more, not the card; picked, it goes with
    # the refine, shows as picked, and Make this surer stops counting it
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps({**OBS, "setting": "indoor"})], [json.dumps(ADV)] * 9)
    rid = _first(c)
    page = c.get(f"/answers/{rid}").text
    refine = page.split('<form class="refine"', 1)[1].split("</form>", 1)[0]
    assert "<strong>Which window is it by?</strong>" in refine and " checked" not in refine
    assert WHY in page
    r = c.post(f"/answers/{rid}/refine", data={"window": "south_close", "setting": "indoor"})
    assert r.status_code == 200
    refine = r.text.split('<form class="refine"', 1)[1].split("</form>", 1)[0]
    assert '<input type="radio" name="window" value="south_close" checked>' in refine
    assert r.text.count(WHY) == 1 and "leans on your photo" not in r.text
    assert 0 < _quick(page) and _quick(r.text) < _quick(page)


def _quick(page: str) -> int:
    """The card's "Make this surer: answer N quick questions", 0 when it is not there."""
    card = page.split('<section class="card main-action"', 1)[1].split("</section>", 1)[0]
    m = re.search(r"Make this surer: answer (\d+) quick question", card)
    return int(m.group(1)) if m else 0


def test_told_says_where_it_grows_when_the_person_corrected_it():
    from herbtwin.advice_context import told_lines
    from herbtwin.schemas import Told

    assert not Told(setting="indoor").is_empty()
    assert told_lines(Told(setting="indoor")) == [
        "where it grows: indoors (the person corrected the photo read)"
    ]


@respx.mock
def test_a_bad_setting_is_refused_in_our_words(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps({**OBS, "setting": "outdoor"})], [json.dumps(ADV)] * 3)
    rid = _first(c)
    r = c.post(f"/answers/{rid}/refine", data={"setting": "<b>garage"})
    assert r.status_code == 400
    assert "Could not use indoors or outdoors. Check it and try again." in r.text
    assert "garage" not in r.text and "Input should be" not in r.text


def test_the_switch_keeps_what_else_was_told(tmp_path):
    from herbtwin.schemas import HeadingTap, Told

    rec = _unsure_record(tmp_path)
    assert rec.observation is not None
    rec.observation.setting = "outdoor"
    rec.told = Told(soil_feel="wet", question="Is it ok?", heading=HeadingTap(direction="S"))
    switch = _page(rec).split('<form class="note setting-switch"', 1)[1].split("</form>", 1)[0]
    for kept in (
        '<input type="hidden" name="soil_feel" value="wet">',
        '<input type="hidden" name="question" value="Is it ok?">',
        '<input type="hidden" name="direction" value="S">',
        '<input type="hidden" name="setting" value="indoor">',
    ):
        assert kept in switch, kept
