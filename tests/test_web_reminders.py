"""The reminder box under a signed-in answer and the unsubscribe page (spec section 7)."""

import json
from datetime import timedelta

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from herbtwin import reminders, scoring
from herbtwin.adapters.mock import MockAdapter
from herbtwin.config import load_settings
from herbtwin.history import MemoryHistory
from herbtwin.pipeline import Deps
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.tracing import TraceStore
from herbtwin.web.app import create_app
from tests.fakes import FakeAuth, fake_accounts, follow
from tests.test_web import ADV, JPEG, OBS, OCT_4, SAMPLE
from tests.test_web_checkup import PASSED

BOX = "Email me when it's time to check again"
SECRET = "rs"


@pytest.fixture(autouse=True)
def _gate(monkeypatch):
    monkeypatch.setattr(scoring, "load_gate", lambda: PASSED)


@pytest.fixture(autouse=True)
def _weather():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
        yield


class MemoryAdmin:
    """The job's view of the memory history: what the unsubscribe page turns off."""

    def __init__(self, hist: MemoryHistory):
        self.hist = hist

    def turn_off(self, answer_id, reason, now):
        owner, r = self.hist.reminders.get(answer_id, (None, None))
        if r is None or r.sent_at or r.off_at:
            return False
        self.hist.reminders[answer_id] = (owner, r.model_copy(update={"off_at": now}))
        return True


def _client(tmp_path, advice=ADV, secret=SECRET, user="u1", later=()):
    hist, auth = MemoryHistory(), FakeAuth()
    env = {"HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "-0.12"}
    if secret:
        env["HERBTWIN_REMINDER_SECRET"] = secret
    deps = Deps(
        observe_adapter=MockAdapter([json.dumps(OBS)] * 3),
        advise_adapter=MockAdapter([json.dumps(advice)] * 3 + [json.dumps(a) for a in later] * 3),
        settings=load_settings(env),
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "p",
        workers=1,
    )
    app = create_app(
        deps,
        clock=lambda: OCT_4,
        accounts=fake_accounts(hist, auth),
        reminder_admin=MemoryAdmin(hist),
        site_url="https://x.test",
    )
    c = TestClient(app)
    if user:
        _sign_in(c, user)
    return c, hist


def _sign_in(c, user):
    c.post(
        "/auth/callback",
        data={"token_hash": c.app.state.accounts.auth.issue(user, f"{user}@b.co"), "type": "email"},
        follow_redirects=False,
    )


def _upload(c):
    r = c.post("/analyse", files={"photo": ("s.jpg", JPEG, "image/jpeg")}, data={"place": ""})
    page = follow(c, r)
    return page, page.url.path.split("/answers/")[1]


def test_a_signed_in_answer_offers_the_box_unticked_and_ticking_keeps_a_reminder(tmp_path):
    c, hist = _client(tmp_path)
    page, rid = _upload(c)
    assert BOX in page.text and f'action="/answers/{rid}/reminder"' in page.text
    assert "checked" not in page.text.split(BOX)[0].rsplit("<form", 1)[1]
    ticked = c.post(f"/answers/{rid}/reminder", data={"on": "1"})
    assert ticked.status_code == 200 and ticked.url.path == f"/answers/{rid}"
    assert " checked" in ticked.text.split(BOX)[0].rsplit("<form", 1)[1]
    r = hist.for_user("u1").get_reminder(rid)
    taken = hist.for_user("u1").get_answer(rid).taken_at
    assert r is not None and r.action == "water it"
    assert r.due_on == taken.astimezone(reminders.UK).date() + timedelta(days=4)


def test_unticking_removes_the_reminder(tmp_path):
    c, hist = _client(tmp_path)
    _, rid = _upload(c)
    c.post(f"/answers/{rid}/reminder", data={"on": "1"})
    page = c.post(f"/answers/{rid}/reminder", data={})
    assert page.status_code == 200
    assert hist.for_user("u1").get_reminder(rid) is None


def test_the_pages_own_script_gets_a_204_not_the_whole_page_again(tmp_path):
    # a failing reload after a good save must never undo the tick on screen
    c, hist = _client(tmp_path)
    page, rid = _upload(c)
    assert '"X-Herbtwin-Fetch": "1"' in page.text  # the tick's script asks for the 204
    r = c.post(f"/answers/{rid}/reminder", data={"on": "1"}, headers={"X-Herbtwin-Fetch": "1"})
    assert r.status_code == 204 and r.content == b""
    assert hist.for_user("u1").get_reminder(rid) is not None


def test_signed_out_answers_have_no_box_and_the_post_is_not_found(tmp_path):
    c, hist = _client(tmp_path, user=None)
    page, rid = _upload(c)
    assert BOX not in page.text
    assert c.post(f"/answers/{rid}/reminder", data={"on": "1"}).status_code == 404
    assert hist.reminders == {}


def test_no_box_without_the_reminder_secret(tmp_path):
    c, hist = _client(tmp_path, secret=None)
    page, rid = _upload(c)
    assert BOX not in page.text
    assert c.post(f"/answers/{rid}/reminder", data={"on": "1"}).status_code == 404
    assert c.get("/reminders/unsubscribe", params={"a": rid, "t": "x"}).status_code == 404


def test_no_box_when_the_main_action_has_no_check_window(tmp_path):
    repot = {**ADV, "actions": ["repot"], "primary": "repot", "answer": "Repot it."}
    c, _ = _client(tmp_path, advice=repot)
    page, rid = _upload(c)
    assert BOX not in page.text
    assert c.post(f"/answers/{rid}/reminder", data={"on": "1"}).status_code == 404


def test_someone_elses_answer_is_not_found(tmp_path):
    c, hist = _client(tmp_path)
    _, rid = _upload(c)
    c.cookies.clear()
    _sign_in(c, "u2")
    assert c.post(f"/answers/{rid}/reminder", data={"on": "1"}).status_code == 404
    assert hist.reminders == {}


def _ticked(tmp_path):
    c, hist = _client(tmp_path)
    _, rid = _upload(c)
    c.post(f"/answers/{rid}/reminder", data={"on": "1"})
    return c, hist, rid, {"a": rid, "t": reminders.sign(rid, SECRET)}


def test_opening_the_unsubscribe_link_only_asks(tmp_path):
    c, hist, rid, q = _ticked(tmp_path)
    page = c.get("/reminders/unsubscribe", params=q)
    assert page.status_code == 200 and "Stop this reminder" in page.text
    assert hist.reminders[rid][1].off_at is None  # a mail scanner opening it changes nothing


def test_pressing_stop_turns_it_off_once(tmp_path):
    c, hist, rid, q = _ticked(tmp_path)
    done = c.post("/reminders/unsubscribe", data=q)
    assert done.status_code == 200 and "Done: no reminder for this answer." in done.text
    assert hist.reminders[rid][1].off_at is not None
    again = c.post("/reminders/unsubscribe", data=q)
    assert again.status_code == 200 and "This reminder is already off." in again.text


def test_a_mail_clients_one_click_post_turns_it_off(tmp_path):
    c, hist, rid, q = _ticked(tmp_path)
    c.cookies.clear()  # the mail client is not signed in
    r = c.post(
        "/reminders/unsubscribe",
        params=q,
        content=b"List-Unsubscribe=One-Click",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200
    assert hist.reminders[rid][1].off_at is not None


@pytest.mark.parametrize(
    "q",
    [
        {"a": "RID", "t": "bad"},
        {"a": "not-an-id", "t": "TOKEN"},
        {"a": "f" * 32, "t": "TOKEN"},  # a real token, for another answer
        {"a": "RID"},
    ],
)
def test_a_bad_link_changes_nothing(tmp_path, q):
    c, hist, rid, good = _ticked(tmp_path)
    q = {k: v.replace("RID", rid).replace("TOKEN", good["t"]) for k, v in q.items()}
    for r in (c.get("/reminders/unsubscribe", params=q), c.post("/reminders/unsubscribe", data=q)):
        assert r.status_code == 400 and "This link doesn" in r.text
    assert hist.reminders[rid][1].off_at is None


def _box_form(page):
    return page.text.split(BOX)[0].rsplit("<form", 1)[1] if BOX in page.text else None


def test_after_unsubscribing_the_box_shows_unticked_and_ticking_turns_it_back_on(tmp_path):
    c, hist, rid, q = _ticked(tmp_path)
    c.post("/reminders/unsubscribe", data=q)
    page = c.get(f"/answers/{rid}")
    assert BOX in page.text and " checked" not in _box_form(page)
    again = c.post(f"/answers/{rid}/reminder", data={"on": "1"})
    assert " checked" in _box_form(again)
    assert hist.reminders[rid][1].off_at is None


def test_a_sent_reminder_is_kept_and_cannot_be_ticked_into_a_second_email(tmp_path):
    c, hist, rid, _ = _ticked(tmp_path)
    owner, r = hist.reminders[rid]
    hist.reminders[rid] = (owner, r.model_copy(update={"sent_at": OCT_4}))
    page = c.get(f"/answers/{rid}")
    assert BOX not in page.text and "We emailed you a reminder for this answer." in page.text
    for data in ({}, {"on": "1"}):
        c.post(f"/answers/{rid}/reminder", data=data)
        assert hist.reminders[rid][1].sent_at == OCT_4  # still the one sent row


REPOT = {**ADV, "actions": ["repot"], "primary": "repot", "answer": "Repot it."}
LEAVE = {**ADV, "actions": ["leave_normal"], "primary": "leave_normal", "answer": "Leave it."}


def _ticked_then_refined(tmp_path, later):
    c, hist = _client(tmp_path, later=[later])
    _, rid = _upload(c)
    c.post(f"/answers/{rid}/reminder", data={"on": "1"})
    page = c.post(f"/answers/{rid}/refine", data={"soil_feel": "wet"})
    assert page.status_code == 200
    return page, hist, rid


def test_a_refine_to_an_action_with_no_check_window_removes_the_reminder(tmp_path):
    page, hist, rid = _ticked_then_refined(tmp_path, REPOT)
    assert hist.for_user("u1").get_reminder(rid) is None
    assert BOX not in page.text


def test_a_refine_to_another_action_moves_the_reminder_to_its_window(tmp_path):
    page, hist, rid = _ticked_then_refined(tmp_path, LEAVE)
    r = hist.for_user("u1").get_reminder(rid)
    taken = hist.for_user("u1").get_answer(rid).taken_at
    assert r is not None and r.action == "leave it"
    assert r.due_on == taken.astimezone(reminders.UK).date() + timedelta(days=12)
    assert " checked" in _box_form(page)


def test_the_privacy_page_names_where_the_reminder_job_runs(tmp_path):
    c, _ = _client(tmp_path, user=None)
    text = c.get("/privacy").text
    assert "Nebius AI Cloud" in text and "reminder" in text


def test_after_choosing_the_plant_the_answer_offers_the_box_and_my_plants(tmp_path):
    c, hist = _client(tmp_path, later=[ADV])
    _upload(c)
    r = c.post("/analyse", files={"photo": ("s.jpg", JPEG, "image/jpeg")}, data={"place": ""})
    chooser = follow(c, r)
    assert "Which plant is this?" in chooser.text
    rid = chooser.text.split('action="/answers/')[1].split("/plant")[0]
    plant = hist.for_user("u1").list_plants()[0]
    done = c.post(f"/answers/{rid}/plant", data={"plant_id": plant.id})
    assert done.status_code == 200
    assert BOX in done.text and 'href="/plants"' in done.text


def test_my_plants_offers_the_box_for_the_latest_answer_and_ticking_stays_there(tmp_path):
    c, hist = _client(tmp_path)
    _, rid = _upload(c)
    plants = c.get("/plants")
    assert BOX in plants.text and f'action="/answers/{rid}/reminder"' in _box_form(plants)
    assert 'name="back" value="/plants"' in _box_form(plants)
    ticked = c.post(f"/answers/{rid}/reminder", data={"on": "1", "back": "/plants"})
    assert ticked.status_code == 200 and ticked.url.path == "/plants"
    assert " checked" in _box_form(ticked)
    assert hist.for_user("u1").get_reminder(rid) is not None


@pytest.mark.parametrize("back", ["https://evil.test/", "//evil.test", "/auth/sign-out", ""])
def test_any_other_back_goes_to_the_answer(tmp_path, back):
    c, _ = _client(tmp_path)
    _, rid = _upload(c)
    page = c.post(f"/answers/{rid}/reminder", data={"on": "1", "back": back})
    assert page.url.path == f"/answers/{rid}" and page.url.host == "testserver"


def test_my_plants_shows_a_sent_reminder_as_a_line_not_a_box(tmp_path):
    c, hist, rid, _ = _ticked(tmp_path)
    owner, r = hist.reminders[rid]
    hist.reminders[rid] = (owner, r.model_copy(update={"sent_at": OCT_4}))
    plants = c.get("/plants")
    assert BOX not in plants.text and "We emailed you a reminder" in plants.text


def test_my_plants_without_the_reminder_secret_has_no_box(tmp_path):
    c, _ = _client(tmp_path, secret=None)
    _upload(c)
    assert BOX not in c.get("/plants").text


def test_unticking_on_my_plants_removes_the_reminder_and_shows_the_box_unticked(tmp_path):
    c, hist = _client(tmp_path)
    _, rid = _upload(c)
    c.post(f"/answers/{rid}/reminder", data={"on": "1", "back": "/plants"})
    page = c.post(f"/answers/{rid}/reminder", data={"back": "/plants"})
    assert page.url.path == "/plants" and " checked" not in _box_form(page)
    assert hist.for_user("u1").get_reminder(rid) is None
