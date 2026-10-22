import json
import logging
import re
import uuid
from datetime import UTC, datetime
from html import unescape
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from herbtwin.adapters.mock import MockAdapter
from herbtwin.config import load_settings
from herbtwin.pipeline import Deps
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.tracing import TraceStore
from herbtwin.web.app import create_app
from tests.fakes import NEXT, follow

SAMPLE = json.loads((Path(__file__).parent / "fixtures" / "open_meteo_sample.json").read_text())
OBS = {
    "species": [{"name": "Ocimum basilicum", "common_name": "basil", "confidence": 0.9}],
    "is_plant": True,
    "water_stress": 2,
    "heat_light_stress": 0,
    "fine_leave_it": False,
    "symptoms": ["droop"],
    "leaf_cues": [],
    "soil_surface": "dry",
    "notes": "",
}
ADV = {
    "actions": ["water"],
    "primary": "water",
    "answer": "The soil is dry and no rain is due. Water it.",
    "ask": "How does the soil feel 2 cm down?",
    "confidence": "high",
}
MINT = {
    **OBS,
    "species": [{"name": "Mentha spicata", "common_name": "spearmint", "confidence": 0.9}],
    "decline": 2,
    "setting": "outdoor",
    "container": "pot",
    "symptoms": ["brown stems"],
}
LEAVE = {
    "actions": ["leave_normal"],
    "primary": "leave_normal",
    "answer": "This is normal autumn dieback. Leave it.",
    "ask": "",
    "confidence": "high",
}
OCT_4 = datetime(2026, 10, 4, 9, tzinfo=UTC)


def _real_jpeg() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "green").save(buf, "JPEG")
    return buf.getvalue()


JPEG = _real_jpeg()


def _real_png() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", (8, 8), (0, 128, 0, 200)).save(buf, "PNG")
    return buf.getvalue()


PNG = _real_png()


def _client(tmp_path, observe, advise, accounts=None):
    s = load_settings({"HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "-0.12"})
    deps = Deps(
        observe_adapter=MockAdapter(observe),
        advise_adapter=MockAdapter(advise),
        settings=s,
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "p",
        workers=1,
    )
    # month fixed: October; accounts only ever come from the test, never from .env
    return TestClient(create_app(deps, clock=lambda: OCT_4, accounts=accounts))


def _placeless_client(tmp_path, observe, advise):
    deps = Deps(
        observe_adapter=MockAdapter(observe),
        advise_adapter=MockAdapter(advise),
        settings=load_settings({}),
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "p",
        workers=1,
    )
    return TestClient(create_app(deps, clock=lambda: OCT_4))


def test_index_shows_upload_form(tmp_path):
    r = _client(tmp_path, [], []).get("/")
    assert r.status_code == 200 and 'name="photo"' in r.text


@respx.mock
def test_analyse_renders_result_page(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    r = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    assert r.status_code == 200
    assert "basil" in r.text and "Water it." in r.text and "TODAY" in r.text


@respx.mock
def test_api_returns_record_json(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    r = c.post("/api/analyse", files={"photo": ("b.png", PNG, "image/png")})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"]["do"][0]["action"] == "water" and body["failures"] == []


@respx.mock
def test_weather_outage_shows_caption_not_500(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(503))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    r = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    assert r.status_code == 200
    assert "weather unavailable" in r.text.lower() and "basil" in r.text
    assert "Water it." in r.text  # the answer still comes back


def test_plant_with_no_species_candidates_is_not_reported_as_no_plant(tmp_path):
    c = _client(tmp_path, [json.dumps(dict(OBS, species=[]))], [])
    r = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    assert r.status_code == 200
    assert "No plant found" not in r.text and "Unidentified plant" in r.text


def test_not_a_plant_page_says_so(tmp_path):
    c = _client(tmp_path, [json.dumps(dict(OBS, is_plant=False, species=[]))], [])
    r = follow(c, c.post("/analyse", files={"photo": ("mug.jpg", JPEG, "image/jpeg")}))
    assert r.status_code == 200 and "No plant found in this photo" in r.text


def test_a_slug_photo_with_no_plant_gets_the_slugs_seen_note(tmp_path):
    slug = dict(OBS, is_plant=False, species=[], quality_note="subject is a slug on a wall")
    c = _client(tmp_path, [json.dumps(slug)], [])
    r = follow(c, c.post("/analyse", files={"photo": ("slug.jpg", JPEG, "image/jpeg")}))
    assert r.status_code == 200
    page = unescape(r.text)
    assert "Slugs seen" in page and "No plant found" not in page
    # our curated signs and their source, not the model's words
    assert "large ragged holes in the leaves" in page
    assert 'href="https://www.rhs.org.uk/biodiversity/slugs-and-snails"' in page


def test_rejects_non_image_by_magic_bytes(tmp_path):
    c = _client(tmp_path, [], [])
    r = c.post(
        "/analyse", files={"photo": ("evil.jpg", b"MZ\x90\x00" + b"\x00" * 32, "image/jpeg")}
    )
    # a page with the sentence and a way back, never raw JSON (19 Oct site walk)
    assert r.status_code == 400 and "JPEG or PNG" in r.text and '{"detail"' not in r.text
    assert 'href="/"' in r.text and "Choose another photo" in r.text


def test_rejects_oversized_upload(tmp_path):
    c = _client(tmp_path, [], [])
    big = JPEG + b"\x00" * (12 * 1024 * 1024)
    r = c.post("/analyse", files={"photo": ("big.jpg", big, "image/jpeg")})
    assert r.status_code == 400 and "12 MB" in r.text and '{"detail"' not in r.text


def test_healthz(tmp_path):
    assert _client(tmp_path, [], []).get("/healthz").json() == {"ok": True, "usage": "off"}


@respx.mock
def test_result_page_shows_decline_and_leaf_colour(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    obs = dict(OBS, decline=2, leaf_colour="some_yellow")
    c = _client(tmp_path, [json.dumps(obs)], [json.dumps(ADV)] * 3)
    r = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    assert "From the photo: droopy, declining" in r.text and "leaves some yellow" in r.text


@respx.mock
def test_result_page_omits_leaf_colour_when_not_visible(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    r = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    assert "From the photo: droopy, healthy-looking" in r.text and "· leaves " not in r.text


def test_index_offers_location_choices(tmp_path):
    r = _client(tmp_path, [], []).get("/")
    assert 'name="place"' in r.text and "Use my location" in r.text


@respx.mock
def test_result_page_shows_layout_b(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(MINT)], [json.dumps(LEAVE)] * 3)
    r = follow(c, c.post("/analyse", files={"photo": ("m.jpg", JPEG, "image/jpeg")}))
    assert r.status_code == 200
    for text in (
        "Leave it. This is normal for October.",
        '<h2 id="main-action">Leave it. This is normal for October.</h2>',
        '<strong>How sure we are<span class="sr-only">:</span></strong>',
        "Keep an eye on",
        "Compare all choices",
        '<details class="evidence fold">',  # its title says what the weather holds (B2)
        "the photo carried no date",  # said once, under what the model assumes
    ):
        assert text in r.text, text
    # leaving it is not a job for today: no time tag on the main card
    assert "TODAY" not in r.text


@respx.mock
def test_device_location_is_used(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(MINT)], [json.dumps(LEAVE)] * 3)
    r = c.post(
        "/api/analyse",
        files={"photo": ("m.jpg", JPEG, "image/jpeg")},
        data={"lat": "53.8", "lon": "-1.55"},
    )
    assert r.json()["location"] == {
        "lat": 53.8,
        "lon": -1.55,
        "source": "device",
        "label": "your location",
    }


def test_half_a_location_is_a_400(tmp_path):
    c = _client(tmp_path, [], [])
    r = c.post("/analyse", files={"photo": ("m.jpg", JPEG, "image/jpeg")}, data={"lat": "53.8"})
    assert r.status_code == 400


@respx.mock
def test_model_text_is_escaped(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    evil = {**LEAVE, "answer": "<script>alert(1)</script> Leave it."}
    c = _client(tmp_path, [json.dumps(MINT)], [json.dumps(evil)] * 3)
    r = follow(c, c.post("/analyse", files={"photo": ("m.jpg", JPEG, "image/jpeg")}))
    assert "<script>alert(1)</script>" not in r.text and "&lt;script&gt;" in r.text


@respx.mock
def test_result_page_shows_a_fine_action(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    mulch = {**ADV, "actions": ["mulch"], "primary": "mulch", "ask": "", "answer": "Mulch it."}
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(mulch)] * 3)
    r = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    assert r.status_code == 200 and "Mulch around it." in r.text


HOLD = json.dumps(
    {
        "actions": ["dont_water"],
        "primary": "dont_water",
        "answer": "Damp below. Hold off.",
        "ask": "",
        "confidence": "high",
    }
)
EXPIRED = "This answer has expired; upload the photo again."


def _first(c):
    r = c.post("/api/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")})
    assert r.status_code == 200
    return r.json()["record_id"]


@respx.mock
def test_watering_answer_shows_the_soil_questions(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    r = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    assert 'name="soil_feel"' in r.text and "cool but not moist" in r.text
    assert 'name="last_watered"' in r.text and 'name="changed"' not in r.text
    assert 'name="question"' in r.text and "/refine" in r.text


@respx.mock
def test_leave_it_on_a_declining_plant_asks_what_changed(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    mint = json.dumps(dict(MINT, soil_surface="not_visible"))
    c = _client(tmp_path, [mint], [json.dumps(LEAVE)] * 3)
    r = follow(c, c.post("/analyse", files={"photo": ("m.jpg", JPEG, "image/jpeg")}))
    assert 'name="changed"' in r.text


@respx.mock
def test_refine_api_reruns_the_advisor_with_the_soil_feel(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3 + [HOLD] * 3)
    rid = _first(c)
    r = c.post(f"/api/answers/{rid}/refine", json={"soil_feel": "wet"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"]["do"][0]["action"] == "dont_water"
    assert body["refined_from"] == "Water it." and body["told"]["soil_feel"] == "wet"


@respx.mock
def test_refine_page_shows_what_changed(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    advice = [json.dumps(ADV)] * 3 + [HOLD] * 3 + [json.dumps(ADV)] * 3
    c = _client(tmp_path, [json.dumps(OBS)], advice)
    rid = _first(c)
    form = {"soil_feel": "wet", "last_watered": "", "changed": "", "question": ""}
    r = c.post(f"/answers/{rid}/refine", data=form)
    assert r.status_code == 200
    assert "<s>Water it.</s>" in r.text and "Hold off watering." in r.text
    # a clear line, not small grey print: the check ran and this is what it did
    assert '<p class="checked">Changed after what you told us. Was: <s>Water it.</s></p>' in r.text
    assert 'value="wet" checked' in r.text  # the form keeps what was told
    same = c.post(f"/answers/{rid}/refine", data={"soil_feel": "dry"})
    assert "Checked again: same advice, and the soil feel fits it." in same.text


@respx.mock
def test_location_uncertain_answer_can_be_refined_with_a_place(tmp_path):
    from herbtwin.schemas import ProblemSeen
    from herbtwin.where import GEOCODE_URL

    uncertain = {
        "actions": ["leave_normal"],
        "primary": "leave_normal",
        "answer": "It looks healthy for now. Leave it.",
        "ask": "Where is it?",
        "confidence": "low",
    }
    next_ask = {**uncertain, "ask": "How does the soil feel 2 cm down?"}
    respx.get(GEOCODE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "name": "Leeds",
                        "country_code": "GB",
                        "latitude": 53.8,
                        "longitude": -1.55,
                    }
                ]
            },
        )
    )
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _placeless_client(
        tmp_path,
        [json.dumps(OBS)],
        [json.dumps(uncertain)] * 3 + [json.dumps(next_ask)] * 3,
    )
    rid = _first(c)
    entry = c.app.state.answers.get_for(rid, None)
    assert entry.reading.rec.location is None
    entry.reading.rec.problem = ProblemSeen(
        name="aphids",
        looks_like="small sap-sucking insects",
        source="https://example.test/aphids",
        seen="tiny insects on leaves",
        sure=False,
    )

    r = c.post(f"/answers/{rid}/refine", data={"place": "A private garden"})
    assert r.status_code == 200
    assert '<span class="chip place">Leeds</span>' in r.text  # no ", GB" on the page
    assert "Could be aphids" in r.text
    assert 'name="place"' not in r.text
    assert c.app.state.answers.get_for(rid, None).reading.rec.location.label == "Leeds, GB"


@respx.mock
def test_refine_api_accepts_a_place(tmp_path):
    from herbtwin.where import GEOCODE_URL

    respx.get(GEOCODE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "name": "Leeds",
                        "country_code": "GB",
                        "latitude": 53.8,
                        "longitude": -1.55,
                    }
                ]
            },
        )
    )
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _placeless_client(
        tmp_path,
        [json.dumps(OBS)],
        [json.dumps(ADV)] * 3 + [json.dumps(HOLD)] * 3,
    )
    rid = _first(c)
    r = c.post(f"/api/answers/{rid}/refine", json={"place": "Leeds"})
    assert r.status_code == 200
    assert r.json()["location"]["label"] == "Leeds, GB"
    assert r.json()["told"]["place"] == "Leeds"


@respx.mock
def test_unknown_refine_place_does_not_call_the_model_or_use_a_slot(tmp_path):
    from herbtwin.where import GEOCODE_URL

    def geocode(request):
        if request.url.params["name"] == "Nowhere":
            return httpx.Response(200, json={"results": []})
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "name": "Leeds",
                        "country_code": "GB",
                        "latitude": 53.8,
                        "longitude": -1.55,
                    }
                ]
            },
        )

    lookup = respx.get(GEOCODE_URL).mock(side_effect=geocode)
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    uncertain = {
        "actions": ["leave_normal"],
        "primary": "leave_normal",
        "answer": "It looks healthy for now. Leave it.",
        "ask": "Where is it?",
        "confidence": "low",
    }
    next_ask = {**uncertain, "ask": "How does the soil feel 2 cm down?"}
    c = _placeless_client(
        tmp_path,
        [json.dumps(OBS)],
        [json.dumps(uncertain)] * 3 + [json.dumps(next_ask)] * 3,
    )
    rid = _first(c)
    for _ in range(5):
        r = c.post(f"/answers/{rid}/refine", data={"place": "Nowhere"})
        assert r.status_code == 400
        assert "We couldn't find that place. Try a UK town or postcode." in unescape(r.text)
    assert len(c.app.state.deps.advise_adapter.calls) == 3

    successful = c.post(f"/answers/{rid}/refine", data={"place": "Leeds"})
    assert successful.status_code == 200
    assert len(c.app.state.deps.advise_adapter.calls) == 6
    assert lookup.call_count == 6


def test_refine_on_an_unknown_answer_says_it_expired(tmp_path):
    c = _client(tmp_path, [], [])
    r = c.post("/api/answers/" + "f" * 32 + "/refine", json={"soil_feel": "wet"})
    assert r.status_code == 404 and r.json()["detail"] == EXPIRED
    page = c.post("/answers/" + "f" * 32 + "/refine", data={"soil_feel": "wet"})
    assert page.status_code == 404 and EXPIRED in page.text


def test_a_message_page_has_one_heading_saying_the_message(tmp_path):
    # a page with no <h1> leaves a screen-reader user with no heading to land on
    page = _client(tmp_path, [], []).post(
        "/answers/" + "f" * 32 + "/refine", data={"soil_feel": "wet"}
    )
    assert page.text.count("<h1") == 1
    # a short heading, then the sentence (17 Oct walk: the whole sentence was the h1)
    assert re.search(r"<h1[^>]*>\s*Not here any more", page.text)
    assert '<p class="lead">This answer has expired' in page.text
    assert "<title>Not here any more · herbtwin</title>" in page.text


@respx.mock
def test_refine_with_nothing_told_is_refused_and_costs_nothing(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    rid = _first(c)
    r = c.post(f"/api/answers/{rid}/refine", json={})
    assert r.status_code == 400
    assert len(c.app.state.deps.advise_adapter.calls) == 3


@respx.mock
def test_bad_refine_input_is_refused_at_the_boundary(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    rid = _first(c)
    assert c.post(f"/api/answers/{rid}/refine", json={"soil_feel": "soggy"}).status_code == 422
    long = {"question": "x" * 501}
    assert c.post(f"/api/answers/{rid}/refine", json=long).status_code == 422
    page = c.post(f"/answers/{rid}/refine", data={"question": "bad\x00text"})
    assert page.status_code == 400


@respx.mock
def test_upload_form_question_goes_to_the_advisor_fenced(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    photo = {"photo": ("b.jpg", JPEG, "image/jpeg")}
    r = follow(c, c.post("/analyse", files=photo, data={"question": "why are the tips brown?"}))
    assert r.status_code == 200
    prompt = c.app.state.deps.advise_adapter.calls[0]["prompt"]
    assert 'question: "why are the tips brown?"' in prompt
    long = c.post("/analyse", files=photo, data={"question": "x" * 501})
    assert long.status_code == 400


def test_index_asks_no_question_but_an_old_form_can_still_send_one(tmp_path):
    # 19 Oct, Kash's walk: photo first, no questions (the old form's field still works:
    # test_upload_form_question_goes_to_the_advisor_fenced)
    r = _client(tmp_path, [], []).get("/")
    assert 'name="question"' not in r.text


@respx.mock
def test_upload_without_a_question_records_nothing_told(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    r = c.post("/api/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")})
    assert r.json()["told"] is None


@respx.mock
def test_second_refine_keeps_what_was_told_when_its_question_is_hidden(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3 + [json.dumps(LEAVE)] * 3)
    rid = _first(c)
    r = c.post(f"/answers/{rid}/refine", data={"soil_feel": "damp", "last_watered": "today"})
    assert "Leave it" in r.text and 'name="soil_feel"' in r.text
    assert '<input type="hidden" name="soil_feel" value="damp">' in r.text
    assert '<input type="hidden" name="last_watered" value="today">' in r.text


@respx.mock
def test_same_advice_does_not_claim_a_clashing_soil_feel_fits(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 6)
    rid = _first(c)
    r = c.post(f"/answers/{rid}/refine", data={"soil_feel": "wet"})
    assert "Water it." in r.text and "the soil feel fits it" not in r.text
    assert "Checked again: same advice." in r.text


@respx.mock
def test_empty_refine_form_gets_a_page_not_raw_json(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    rid = _first(c)
    r = c.post(f"/answers/{rid}/refine", data={"soil_feel": "", "question": ""})
    assert r.status_code == 400 and r.headers["content-type"].startswith("text/html")
    assert "Nothing to refine with" in r.text and "go back" in r.text.lower()


@respx.mock
def test_upload_streams_progress_then_links_to_the_answer(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    r = c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "no-transform" in r.headers["cache-control"]
    steps = [  # as steps: the head's slow-line script names some of them too
        "<li>Reading the photo",
        "<li>Found basil",
        "<li>Looking up how basil likes to grow",
        "<li>Thinking about what it needs",
        'id="next"',
    ]
    at = [r.text.index(s) for s in steps]
    assert at == sorted(at)
    assert "Water it." not in r.text  # the answer has its own page
    page = follow(c, r)
    assert page.status_code == 200 and "Water it." in page.text


@respx.mock
def test_reloading_the_answer_does_not_run_the_models_again(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    r = c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")})
    url = NEXT.search(r.text).group(1)
    assert "Water it." in c.get(url).text and "Water it." in c.get(url).text
    assert len(c.app.state.deps.advise_adapter.calls) == 3
    assert len(c.app.state.deps.observe_adapter.calls) == 1


def test_an_unknown_or_malformed_answer_id_is_expired(tmp_path):
    c = _client(tmp_path, [], [])
    for path in (f"/answers/{uuid.uuid4().hex}", "/answers/not-an-id"):
        r = c.get(path)
        assert r.status_code == 404 and "expired" in r.text


@respx.mock
def test_a_plant_name_with_markup_is_escaped_in_the_progress(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    evil = {**OBS, "species": [{"name": "X y", "common_name": "<b>basil</b>", "confidence": 0.9}]}
    c = _client(tmp_path, [json.dumps(evil)], [json.dumps(ADV)] * 3)
    r = c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")})
    assert "<b>basil</b>" not in r.text and "Found &lt;b&gt;basil&lt;/b&gt;" in r.text


def test_a_crash_mid_read_says_so_and_offers_a_retry(tmp_path, monkeypatch, caplog):
    import herbtwin.web.app as web

    def boom(*a, **k):
        raise RuntimeError("boom secret")

    monkeypatch.setattr(web, "read_photo", boom)
    c = _client(tmp_path, [], [])
    r = c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")})
    assert r.status_code == 200 and "That didn't work" in r.text
    assert '<a href="/">Try again</a>' in r.text
    assert "boom secret" not in r.text and 'id="next"' not in r.text
    assert "boom secret" in caplog.text


def test_privacy_page_names_who_processes_what(tmp_path):
    r = _client(tmp_path, [], []).get("/privacy")
    assert r.status_code == 200
    for name in ("Nebius Token Factory", "Supabase", "Resend", "Open-Meteo", "Delete account"):
        assert name in r.text
    assert "LangSmith" in r.text and "no photos, email addresses or locations" in r.text
    assert "What can I grow here?" in r.text and "direction" in r.text
    assert "coldest winter nights" in r.text
    assert "postcodes.io" in r.text and "postcode you type" in r.text
    assert "https://github.com/thekashifnazir/herbtwin" in r.text


def test_home_page_links_to_privacy(tmp_path):
    assert 'href="/privacy"' in _client(tmp_path, [], []).get("/").text


@respx.mock
def test_answer_page_links_to_privacy(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    r = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    assert 'href="/privacy"' in r.text


def test_a_missing_page_is_a_page_for_a_browser_and_json_for_the_api(tmp_path):
    # was {"detail": "Not Found"} in the browser: a dead end with no menu
    c = _client(tmp_path, [], [])
    page = c.get("/no-such-page", headers={"accept": "text/html,*/*"})
    assert page.status_code == 404 and "We can&#39;t find that page" in page.text
    assert ">Check a plant</a>" in page.text  # the menu is there
    # 18 Oct judge walk: curl (Accept */*) still got the raw JSON; only a client that asks
    # for JSON alone gets it now, and the tab title is a short heading, not the sentence
    for accept in (None, "*/*"):
        bare = c.get("/no-such-page", headers={"accept": accept} if accept else {})
        assert bare.status_code == 404 and "We can&#39;t find that page" in bare.text
    assert "<title>Page not found · herbtwin</title>" in page.text
    assert "<h1>Page not found</h1>" in page.text
    wants_json = c.get("/no-such-page", headers={"accept": "application/json"})
    assert wants_json.json() == {"detail": "Not Found"}
    api = c.post("/api/answers/nope/chat", json={"message": "hi"}, headers={"accept": "text/html"})
    assert api.status_code == 404 and api.json()["detail"] == EXPIRED
    unknown = c.get("/api/no-such-thing", headers={"accept": "text/html"})
    assert unknown.status_code == 404 and unknown.json() == {"detail": "Not Found"}


def test_an_answer_for_one_of_several_plants_says_which(tmp_path):
    shared = {**OBS, "photo_quality": "poor", "quality_note": "several plants share the frame"}
    c = _client(tmp_path, [json.dumps(shared)], [json.dumps(ADV)] * 3)
    r = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    # asked which plant first (tapping.py); the whole photo still says which it answered for
    tid = re.search(r'action="/taps/([0-9a-f]+)"', r.text).group(1)
    r = follow(c, c.post(f"/taps/{tid}", data={"whole": "1"}))
    assert '<p class="note">Answering for the basil, one of several plants in this photo.' in r.text


def test_a_form_with_no_photo_gets_a_page_not_a_validation_dump(tmp_path):
    c = _client(tmp_path, [], [])
    r = c.post("/analyse", data={"place": "London"})
    assert r.status_code == 422 and "Choose a photo first." in r.text and '"loc"' not in r.text


def test_the_spot_form_gets_pages_too(tmp_path):
    from tests.test_web_spot import _client as spot_client

    c, _ = spot_client(tmp_path)
    r = c.post("/spots", data={"place": "London"})
    assert r.status_code == 422 and "Choose a photo first." in r.text
    r = c.post("/spots", files={"photo": ("x.jpg", b"not an image", "image/jpeg")})
    assert r.status_code == 400 and '{"detail"' not in r.text and "Choose another photo" in r.text


@pytest.mark.parametrize(
    ("path", "parent"),
    [
        ("/spots", "/"),
        ("/analyse", "/"),
        (f"/answers/{'a' * 32}/refine", f"/answers/{'a' * 32}"),
        (f"/answers/{'a' * 32}/did-it", f"/answers/{'a' * 32}"),
        (f"/answers/{'a' * 32}/reminder", f"/answers/{'a' * 32}"),
        ("/plants/p1/rename", "/plants"),
        ("/plants/p1/delete", "/plants"),
        (f"/answers/{'a' * 32}/photo", f"/answers/{'a' * 32}"),
        (f"/spots/{'a' * 32}/told", f"/spots/{'a' * 32}"),
        ("/auth/sign-out", "/"),
    ],
)
def test_opening_a_form_address_goes_to_its_page(tmp_path, path, parent):
    # a refresh after "Check the advice again", or a bookmark: never {"detail":"Method Not
    # Allowed"} (19 Oct site walk, also seen live)
    r = _client(tmp_path, [], []).get(path, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == parent


def test_the_json_api_keeps_json_errors(tmp_path):
    c = _client(tmp_path, [], [])
    r = c.post("/api/analyse", files={"photo": ("x.jpg", b"not an image", "image/jpeg")})
    assert r.status_code == 400 and "JPEG or PNG" in r.json()["detail"]
    assert "detail" in c.post("/api/analyse").json()  # the validation dump, for the API
    asks_json = c.post("/analyse", headers={"accept": "application/json"})
    assert asks_json.status_code == 422 and "detail" in asks_json.json()


@respx.mock
def test_an_indoor_answer_shows_no_outdoor_season_source(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    for setting, shown in (("indoor", False), ("outdoor", True)):
        (tmp_path / setting).mkdir()
        obs = {**OBS, "setting": setting}
        c = _client(tmp_path / setting, [json.dumps(obs)], [json.dumps(ADV)] * 3)
        page = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
        assert ("<p>Season in " in page.text) is shown, setting


@respx.mock
def test_form_errors_are_in_our_words_never_the_validators(tmp_path, caplog):
    # integrator nit, 19 Oct: pydantic's and the coordinate parser's wording reached the page,
    # the parser's with the raw input repeated back; the log keeps the kind, not the input
    caplog.set_level(logging.INFO, logger="herbtwin.web.app")
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    rid = _first(c)
    r = c.post(f"/answers/{rid}/refine", data={"soil_feel": "wet", "question": "hi\x07there"})
    assert r.status_code == 400 and "Could not use your question. Check it and try again." in r.text
    assert "Value error" not in r.text and "plain text" not in r.text
    r = c.post(f"/answers/{rid}/refine", data={"last_watered": "ages", "changed": "lots"})
    assert "Could not use what changed and when it was last watered." in r.text
    r = c.post(
        "/analyse",
        data={"lat": "<b>51", "lon": "0"},
        files={"photo": ("b.jpg", JPEG, "image/jpeg")},
    )
    assert r.status_code == 400 and "Could not read that location." in r.text
    assert "&lt;b&gt;51" not in r.text and "decimal degrees" not in r.text
    assert "answer refused: ValidationError question:" in caplog.text
    assert "device location refused: ValueError" in caplog.text
    for said in ("hi\x07there", "ages", "lots", "<b>51"):
        assert said not in "\n".join(caplog.messages), said


@respx.mock
def test_a_sample_sent_with_no_town_is_answered_for_london(tmp_path):
    # judge pre-walk, 19 Oct: "place unknown", no twin and no forecast for a sample
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    sample = Path(__file__).parents[1] / "src/herbtwin/web/static/samples/1-parsley-healthy.jpg"
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    page = follow(
        c, c.post("/analyse", files={"photo": ("p.jpg", sample.read_bytes(), "image/jpeg")})
    )
    assert "Sample photo · London" in page.text and "place unknown" not in page.text
