"""The compass and squeeze questions under a plant answer (spot spec section 8, D73):
shown and used only with HERBTWIN_SPOT_ENABLED; the sensor angles are worked out on the
server and a bad reading is a 400 page, never a stored answer."""

import json
import logging

import httpx
import respx
from fastapi.testclient import TestClient

from herbtwin.adapters.mock import MockAdapter
from herbtwin.config import load_settings
from herbtwin.pipeline import Deps
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.tracing import TraceStore
from herbtwin.web.app import create_app
from tests.fakes import follow
from tests.test_web import JPEG, LEAVE, MINT, OCT_4, SAMPLE

HOME = {"HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "-0.12"}


def _client(tmp_path, spot: bool, advice: int = 6):
    env = {**HOME, "HERBTWIN_SPOT_ENABLED": "1"} if spot else HOME
    deps = Deps(
        observe_adapter=MockAdapter([json.dumps(MINT)]),
        advise_adapter=MockAdapter([json.dumps(LEAVE)] * advice),
        settings=load_settings(env),
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "p",
        workers=1,
    )
    return TestClient(create_app(deps, clock=lambda: OCT_4)), deps


def _answer(c):
    r = follow(c, c.post("/analyse", files={"photo": ("m.jpg", JPEG, "image/jpeg")}))
    rid = r.url.path.rsplit("/", 1)[1]
    return r, rid


@respx.mock
def test_off_the_plant_answer_is_unchanged(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, _ = _client(tmp_path, spot=False)
    r, rid = _answer(c)
    assert "data-compass" not in r.text and "which way it faces" not in r.text
    again = c.post(f"/answers/{rid}/refine", data={"direction": "S", "question": "ok?"})
    assert again.status_code == 200  # the direction is ignored, the question refines


@respx.mock
def test_off_the_api_drops_the_spot_answers(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, _ = _client(tmp_path, spot=False)
    _, rid = _answer(c)
    body = {"squeeze": "sticky", "heading": {"direction": "S"}, "question": "ok?"}
    got = c.post(f"/api/answers/{rid}/refine", json=body).json()
    assert got["told"]["squeeze"] is None and got["told"]["heading"] is None


@respx.mock
def test_on_the_direction_is_asked_and_a_tap_still_refines_with_no_vision_call(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, deps = _client(tmp_path, spot=True)
    r, rid = _answer(c)
    assert "which way it faces" in r.text and "data-compass" in r.text
    # step 0 found the phone compass 143 deg out: the 8-way pick is the question
    assert '<button type="button" data-compass-tap>' not in r.text and "Pick a direction" in r.text
    assert "data-compass-fallback hidden" not in r.text
    tap = {"sensor": "absolute", "alpha": "0", "beta": "100", "gamma": "0"}  # due north, 10 up
    again = c.post(f"/answers/{rid}/refine", data=tap)
    assert again.status_code == 200
    assert 'name="heading" value="0.0"' in again.text  # carried for the next refine
    assert [x["kind"] for x in deps.observe_adapter.calls] == ["image"]


@respx.mock
def test_bad_readings_are_400_pages(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, deps = _client(tmp_path, spot=True)
    _, rid = _answer(c)
    advised = len(deps.advise_adapter.calls)
    for bad in (
        {"sensor": "relative", "alpha": "0", "beta": "90", "gamma": "0"},
        {"sensor": "absolute", "alpha": "x", "beta": "90", "gamma": "0"},
        {"heading": "361"},
        {"direction": "UP"},
        {"squeeze": "wet"},
    ):
        r = c.post(f"/answers/{rid}/refine", data=bad)
        assert r.status_code == 400 and '<p class="lead">' in r.text, bad
    assert len(deps.advise_adapter.calls) == advised  # refused before any refine


@respx.mock
def test_a_bad_direction_is_refused_in_our_words(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="herbtwin.web.app")
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, _ = _client(tmp_path, spot=True)
    _, rid = _answer(c)
    for bad in ({"direction": "<b>UP"}, {"heading": "361"}):
        r = c.post(f"/answers/{rid}/refine", data=bad)
        assert r.status_code == 400, bad
        assert "Could not use that compass reading. Pick a direction and try again." in r.text
        assert "&lt;b&gt;UP" not in r.text and "Input should be" not in r.text, bad
    logged = "\n".join(caplog.messages)  # the messages only: a line number can hold "361"
    assert "<b>UP" not in logged and "361" not in logged
    # herbtwin.compass's own sentence still shows: it is ours and names no input
    tap = {"sensor": "relative", "alpha": "17", "beta": "90", "gamma": "0"}
    r = c.post(f"/answers/{rid}/refine", data=tap)
    assert "Could not use that compass reading: this phone gave no compass direction" in r.text


def test_the_compass_script_falls_back_on_a_null_reading_and_waits_for_one():
    from herbtwin.web.app import TEMPLATES

    src = TEMPLATES.env.loader.get_source(TEMPLATES.env, "_spot_questions.html")[0]
    # a desktop with no sensors, or a phone with no magnetometer, sends nulls: show the
    # 8-way picker rather than a 400 page; one listener per tap, removed on timeout
    assert "e.beta === null || (!ios && e.alpha === null)" in src
    assert "tap.disabled = true" in src and "removeEventListener(kind, read)" in src


def test_the_compass_first_layout_survives_as_a_fallback():
    from herbtwin.web.app import TEMPLATES

    macro = TEMPLATES.env.get_template("_spot_questions.html").module.compass_field
    first = str(macro(compass_first=True))
    assert "data-compass-tap>Point and tap" in first and "data-compass-fallback hidden" in first
    eight = str(macro(compass_first=False))
    assert "data-compass-tap>" not in eight and "Pick a direction" in eight


def test_the_questions_are_labelled_radio_tiles():
    """Tap targets, not dropdowns: the 8-way pick is a compass rose of radios (each named in
    full for a screen reader) and the squeeze test a radio per answer, the given one checked."""
    from herbtwin.web.app import TEMPLATES

    module = TEMPLATES.env.get_template("_spot_questions.html").module
    eight = str(module.compass_field(compass_first=False))
    assert eight.count('type="radio" name="direction"') == 9  # 8 ways and "Not sure"
    assert '<span class="vh">south-west</span>' in eight and "<select" not in eight
    assert 'value="" checked><span>Not sure</span>' in eight  # nothing picked yet
    rose = str(module.direction_rose("SE", unsure=False))
    assert rose.count('name="direction"') == 8 and 'value="SE" checked' in rose
    squeeze = str(module.squeeze_field({"gritty": "gritty", "sticky": "sticky"}, "sticky"))
    assert squeeze.count('type="radio" name="squeeze"') == 3 and "<legend>" in squeeze
    assert 'value="sticky" checked' in squeeze and 'value="" checked' not in squeeze
