"""Add photos for a surer answer (21 Oct, Kash on the live site: "not an option in the results
screen to ask us for more photos to help improve it"). The first photo, held as the model saw
it for the answer's hour, is read again with 1 or 2 more in one call: a fresh answer at a new
id, one photo read for the caps, and the first answer kept."""

import json
from datetime import timedelta

import httpx
import respx
from fastapi.testclient import TestClient

from herbtwin.adapters.mock import MockAdapter
from herbtwin.config import load_settings
from herbtwin.pipeline import Deps
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.tracing import TraceStore
from herbtwin.usage import MemoryUsage
from herbtwin.web.app import MORE_PHOTOS_GONE, MORE_PHOTOS_NONE, TOO_MANY_PHOTOS, create_app
from herbtwin.where import exif_gps
from tests.fakes import follow
from tests.test_more_photos import Recording, _more
from tests.test_web import ADV, JPEG, OBS, PNG, SAMPLE, _client
from tests.test_web_accounts import _accounts_client, _sign_in
from tests.test_web_caps import BUSY
from tests.test_where import LONDON, _jpeg


def _answer(c, photo=JPEG) -> str:
    r = follow(c, c.post("/analyse", files={"photo": ("a.jpg", photo, "image/jpeg")}))
    assert r.status_code == 200 and "Water it." in r.text
    return r.url.path.rsplit("/", 1)[1]


def _add(c, rid, *photos, **told):
    return c.post(f"/answers/{rid}/photos", files=_more(*photos), data=told)


@respx.mock
def test_more_photos_read_the_first_again_with_them_for_a_fresh_answer(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [], [json.dumps(ADV)] * 6)
    seen = Recording([json.dumps(OBS)] * 2)
    c.app.state.deps.observe_adapter = seen
    first = _answer(c)
    r = follow(c, _add(c, first, JPEG, PNG, soil_feel="dry"))
    assert r.status_code == 200 and "Water it." in r.text
    fresh = r.url.path.rsplit("/", 1)[1]
    assert fresh != first
    # one call with all three photos: the held first photo leads
    assert [len(images) for images in seen.images] == [1, 3]
    assert seen.images[1][0] == (c.app.state.held.get(first).data, "image/jpeg")
    new = c.app.state.answers.get(fresh).latest
    old = c.app.state.answers.get(first).latest
    assert new.location == old.location and new.taken_at == old.taken_at
    assert new.told is not None and new.told.soil_feel == "dry"
    assert c.get(f"/answers/{first}").status_code == 200  # the first answer stays


@respx.mock
def test_the_held_photo_is_the_model_copy_without_its_location(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    held = c.app.state.held.get(_answer(c, _jpeg(LONDON)))
    assert held is not None and exif_gps(held.data) is None


@respx.mock
def test_more_photos_need_one_or_two_and_a_first_photo_still_held(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    rid = _answer(c)
    calls = len(c.app.state.deps.observe_adapter.calls)
    none = c.post(f"/answers/{rid}/photos", data={"soil_feel": "dry"})
    assert none.status_code == 400 and MORE_PHOTOS_NONE in none.text
    three = _add(c, rid, JPEG, JPEG, JPEG)
    assert three.status_code == 400 and TOO_MANY_PHOTOS in three.text
    gone = _add(c, "0" * 32, JPEG)
    assert gone.status_code == 404 and MORE_PHOTOS_GONE in gone.text
    assert len(c.app.state.deps.observe_adapter.calls) == calls  # no read for any of them


@respx.mock
def test_the_first_photo_goes_with_the_answers_hour(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    rid = _answer(c)
    now = c.app.state.held._clock()
    c.app.state.held._clock = lambda: now + timedelta(hours=1, seconds=1)
    r = _add(c, rid, JPEG)
    assert r.status_code == 404 and MORE_PHOTOS_GONE in r.text


@respx.mock
def test_more_photos_count_as_one_read_against_the_caps(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    deps = Deps(
        observe_adapter=MockAdapter([json.dumps(OBS)] * 3),
        advise_adapter=MockAdapter([json.dumps(ADV)] * 9),
        settings=load_settings(
            {"HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "-0.12", "HERBTWIN_DAILY_READS": "2"}
        ),
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "p",
        workers=1,
    )
    c = TestClient(create_app(deps, usage=MemoryUsage()))
    rid = _answer(c)
    assert follow(c, _add(c, rid, JPEG, PNG)).status_code == 200  # read 2 of 2
    refused = _add(c, rid, JPEG)
    assert refused.status_code == 429 and BUSY in refused.text


@respx.mock
def test_signed_in_the_stored_photo_is_read_again_with_the_new_ones(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, _, auth = _accounts_client(tmp_path, [], [json.dumps(ADV)] * 6)
    seen = Recording([json.dumps(OBS)] * 2)
    c.app.state.deps.observe_adapter = seen
    _sign_in(c, auth)
    first = _answer(c)
    r = follow(c, _add(c, first, PNG))
    assert r.status_code == 200 and "Water it." in r.text
    assert [len(images) for images in seen.images] == [1, 2]


@respx.mock
def test_the_page_offers_more_photos_only_while_the_first_is_held(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    rid = _answer(c)
    assert c.get(f"/answers/{rid}").context["more_photos_on"] is True
    now = c.app.state.held._clock()
    c.app.state.held._clock = lambda: now + timedelta(hours=1, seconds=1)
    assert c.get(f"/answers/{rid}").context["more_photos_on"] is False


def test_the_privacy_page_says_the_photo_stays_for_the_hour(tmp_path):
    page = _client(tmp_path, [], []).get("/privacy").text
    assert "the photo as the AI\n    saw it (no location data), stay in the server's memory" in page


def test_a_held_photo_is_dropped_after_its_hour_even_if_never_asked_for():
    # #352 review: privacy.html says "then they are gone", so an unvisited photo goes too
    from datetime import UTC, datetime

    from herbtwin.web.held_photos import HeldPhotos

    now = [datetime(2026, 10, 21, 9, tzinfo=UTC)]
    held = HeldPhotos(lambda: now[0])
    held.put("a" * 32, b"first", "image/jpeg")
    now[0] += timedelta(hours=1, seconds=1)
    held.put("b" * 32, b"second", "image/jpeg")
    assert list(held._held) == ["b" * 32]


@respx.mock
def test_signed_in_an_unkept_answer_that_stops_early_is_never_read_twice(tmp_path):
    # #356 review: read while signed out, then signed in; the re-read finds no plant, so
    # its record is the answer, never a second, unpaid read without the first answer's place
    from tests.test_web_caps import NOT_A_PLANT

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    # a spare reply: a second re-read would succeed and be counted
    replies = [json.dumps(OBS), NOT_A_PLANT, json.dumps(OBS)]
    c, _, auth = _accounts_client(tmp_path, replies, [json.dumps(ADV)] * 6)
    first = _answer(c)
    _sign_in(c, auth)
    r = follow(c, _add(c, first, JPEG))
    assert r.status_code == 200 and "No plant found" in r.text
    reads = [call for call in c.app.state.deps.observe_adapter.calls if call["stage"] == "observe"]
    assert len(reads) == 2  # the first read and the one re-read


@respx.mock
def test_signed_in_a_small_png_first_photo_is_stored_as_jpeg(tmp_path):
    # #356 review: a first photo under 1600 px is held as it came (a PNG stays a PNG)
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, hist, auth = _accounts_client(tmp_path, [json.dumps(OBS)] * 2, [json.dumps(ADV)] * 6)
    _sign_in(c, auth)
    first = _answer(c, PNG)
    assert c.app.state.held.get(first).mime == "image/png"
    r = follow(c, _add(c, first, JPEG))
    fresh = r.url.path.rsplit("/", 1)[1]
    store = hist.for_user("u1")
    assert store.get_photo(store.get_answer(fresh).photo_path).startswith(b"\xff\xd8")


@respx.mock
def test_another_visitor_cannot_add_photos_to_a_signed_in_answer(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, _, auth = _accounts_client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    _sign_in(c, auth)
    rid = _answer(c)
    calls = len(c.app.state.deps.observe_adapter.calls)
    c.cookies.clear()  # the same answer id from a browser that is not signed in as its owner
    r = _add(c, rid, JPEG)
    assert r.status_code == 404 and MORE_PHOTOS_GONE in r.text
    assert len(c.app.state.deps.observe_adapter.calls) == calls


def test_held_photos_drop_the_oldest_past_the_byte_cap():
    from datetime import UTC, datetime

    from herbtwin.web.held_photos import HeldPhotos

    held = HeldPhotos(lambda: datetime(2026, 10, 21, 9, tzinfo=UTC), max_bytes=10)
    held.put("a" * 32, b"123456", "image/jpeg")
    held.put("b" * 32, b"123456", "image/jpeg")
    assert held.get("a" * 32) is None and held.get("b" * 32) is not None
    held.put("c" * 32, b"x" * 20, "image/jpeg")  # one over the cap alone is still held
    assert list(held._held) == ["c" * 32]
