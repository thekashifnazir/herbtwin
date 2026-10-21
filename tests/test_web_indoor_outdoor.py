"""19 Oct (Kash): the site should say plainly that the forecast and the twin test are for
outdoor plants, and that an indoor answer is for room conditions."""

import json

import httpx
import respx

from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.web import style
from tests.test_web import ADV, OBS, SAMPLE, _client, _first
from tests.test_web_answer_page import _unsure_record
from tests.test_web_home import _home
from tests.test_web_plant_face import _page

NOTE = "Indoors: advice for room conditions, without the forecast test."


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
    band = page.split('<p class="where">', 1)[1]
    assert band.split("</p>", 1)[1].lstrip().startswith(f'<p class="note indoor-note">{NOTE}</p>')
    # judge walk of #272: an empty Compare that opened to "Not compared" is hidden; the band
    # above already says there is no forecast test indoors
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
    assert ">Indoors? Switch and we'll redo the advice for an indoor plant</button>" in switch
    fetched = weather.call_count
    r = c.post(f"/answers/{rid}/refine", data={"setting": "indoor"})
    assert r.status_code == 200
    assert NOTE in r.text and "Compare all choices" not in r.text
    assert weather.call_count == fetched  # indoors: no forecast asked for
    switch = r.text.split('<form class="note setting-switch"', 1)[1].split("</form>", 1)[0]
    assert '<span class="chip setting">Indoors (you said)</span>' in r.text
    assert 'name="setting" value="outdoor"' in switch
    # the next refine keeps it: the setting rides along with what else was told
    refine = r.text.split('<form class="refine"', 1)[1].split("</form>", 1)[0]
    assert '<input type="hidden" name="setting" value="indoor">' in refine
    r = c.post(f"/answers/{rid}/refine", data={"setting": "outdoor"})
    assert r.status_code == 200 and NOTE not in r.text and "it is indoors" not in r.text
    assert "Outdoors (you said)" in r.text


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
