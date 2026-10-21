"""The same photo, place and question today gets the same answer (replays.py, 17 Oct):
the three advisor asks changed the headline in 10 of 50 repeats, and judges re-upload the
samples."""

import json
from datetime import date, datetime

import httpx
import respx

from herbtwin.replays import ReplayCache, replay_key
from herbtwin.schemas import AnalysisRecord, StageFailure, Told
from herbtwin.stages.environment import OPEN_METEO_URL
from tests.test_web import ADV, JPEG, OBS, SAMPLE, _client

DAY = date(2026, 10, 17)


def test_the_key_changes_with_anything_the_person_said():
    base = replay_key("abc", (51.5, -0.12), "London", None, DAY)
    assert replay_key("abc", (51.5, -0.12), " london ", None, DAY) == base  # case, spaces
    assert replay_key("abd", (51.5, -0.12), "London", None, DAY) != base  # another photo
    assert replay_key("abc", (51.26, -0.31), "London", None, DAY) != base
    assert replay_key("abc", (51.5, -0.12), "Leeds", None, DAY) != base
    assert replay_key("abc", (51.5, -0.12), "London", Told(question="why?"), DAY) != base
    assert replay_key("abc", (51.5, -0.12), "London", None, date(2026, 10, 18)) != base


def _rec(**kw) -> AnalysisRecord:
    # the cache reads only failures and answer
    return AnalysisRecord.model_construct(**{"failures": [], "answer": None, **kw})


def test_a_new_day_or_a_failed_step_is_never_replayed():
    now = {"t": datetime(2026, 10, 17, 9)}
    cache = ReplayCache(lambda: now["t"])
    failed = _rec(failures=[StageFailure(stage="environment", message="503")], answer="x")
    cache.put("k1", None, failed)
    assert cache.get("k1") is None  # a failed step gets a fresh chance next time
    cache.put("k2", None, _rec())  # no answer at all: not kept either
    assert cache.get("k2") is None
    cache.put("k3", None, _rec(answer="x"))
    assert cache.get("k3") is not None
    now["t"] = datetime(2026, 10, 18, 9)  # a new forecast day
    assert cache.get("k3") is None


@respx.mock
def test_a_repeat_upload_gets_the_same_answer_with_no_model_calls(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    # one photo read and one panel of replies only: a second read would exhaust the mock
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    send = {"photo": ("b.jpg", JPEG, "image/jpeg")}
    here = {"lat": "51.50", "lon": "-0.12"}
    first = c.post("/api/analyse", files=send, data=here).json()
    again = c.post("/api/analyse", files=send, data=here).json()
    assert first["answer"]["headline"] == again["answer"]["headline"]
    assert first["answer"]["do"] == again["answer"]["do"]
    assert again["record_id"] != first["record_id"]  # its own id: no shared chat
    assert not again["failures"]
    # a different question is a different read: the empty mock now fails it
    other = c.post("/api/analyse", files=send, data={**here, "question": "why?"})
    assert other.json()["failures"]
    # the copy is a full answer of its own: it opens, and its refine has a reading
    assert c.get(f"/answers/{again['record_id']}").status_code == 200
    assert c.app.state.answers.get(again["record_id"]).reading is not None


def test_a_later_change_to_the_callers_record_never_reaches_a_replay():
    # app.py appends a sign-in note to the record after storing it (review, 17 Oct)
    now = datetime(2026, 10, 17, 9)
    cache = ReplayCache(lambda: now)
    rec = _rec(answer="x", notes=[])
    cache.put("k", None, rec)
    rec.notes.append("Sign-in is down: this answer is not saved.")
    copy, _ = cache.get("k").copy("new-id")
    assert copy.notes == [] and copy.record_id == "new-id"


@respx.mock
def test_the_same_pixels_with_other_photo_data_are_a_fresh_read(tmp_path):
    # the read takes place, date and light from the photo's own metadata, so a file that
    # differs only there must not get another visitor's answer
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c = _client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
    here = {"lat": "51.50", "lon": "-0.12"}
    c.post("/api/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}, data=here)
    other = JPEG + b"\x00"  # same picture, different file bytes
    r = c.post("/api/analyse", files={"photo": ("b.jpg", other, "image/jpeg")}, data=here)
    assert r.json()["failures"]  # it ran fresh, and the one-read mock is empty
