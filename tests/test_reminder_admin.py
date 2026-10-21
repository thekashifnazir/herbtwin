"""The reminder job's view of Supabase, with the secret key (spec section 7)."""

import json
import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
import respx

from herbtwin.adapters.reminder_admin import SupabaseReminderAdmin
from herbtwin.reminders import AdminError, Reminder

URL = "https://sb.test"
NOW = datetime(2026, 10, 16, 8, tzinfo=UTC)
ROW = {
    "answer_id": "11111111-1111-1111-1111-111111111111",
    "user_id": "u1",
    "plant_id": "p1",
    "plant_name": "Basil",
    "action": "water it",
    "taken_at": "2026-10-12T10:00:00+00:00",
    "due_on": "2026-10-16",
    "last_on": "2026-10-19",
    "sent_at": None,
    "off_at": None,
}


def _admin():
    return SupabaseReminderAdmin(URL, "sb_secret_x", httpx.Client())


def _reminder():
    return Reminder.model_validate(ROW)


@respx.mock
def test_due_asks_for_unsent_reminders_up_to_today_with_the_secret_key():
    route = respx.get(f"{URL}/rest/v1/reminders").mock(return_value=httpx.Response(200, json=[ROW]))
    got = _admin().due(date(2026, 10, 16))
    req = route.calls.last.request
    assert req.headers["apikey"] == "sb_secret_x"
    assert req.headers["authorization"] == "Bearer sb_secret_x"
    q = dict(req.url.params)
    assert q["due_on"] == "lte.2026-10-16"
    assert q["sent_at"] == "is.null" and q["off_at"] == "is.null"
    assert "created_at" not in q["select"]  # the job may not read it
    assert [r.answer_id for r in got] == ["1" * 32]


@respx.mock
def test_followed_up_looks_for_a_later_photo_of_the_same_plant():
    route = respx.get(f"{URL}/rest/v1/answers").mock(
        side_effect=[httpx.Response(200, json=[{"plant_id": "p1"}]), httpx.Response(200, json=[])]
    )
    admin = _admin()
    assert admin.followed_up(_reminder()) is True
    q = dict(route.calls.last.request.url.params)
    assert q["plant_id"] == "eq.p1"
    assert q["taken_at"] == "gt.2026-10-12T10:00:00+00:00"
    assert q["select"] == "plant_id" and q["limit"] == "1"
    assert admin.followed_up(_reminder()) is False


@respx.mock
def test_email_of_reads_the_account_and_none_when_it_is_gone():
    respx.get(f"{URL}/auth/v1/admin/users/u1").mock(
        return_value=httpx.Response(200, json={"id": "u1", "email": "kash@x.test"})
    )
    respx.get(f"{URL}/auth/v1/admin/users/u2").mock(return_value=httpx.Response(404, json={}))
    admin = _admin()
    assert admin.email_of("u1") == "kash@x.test"
    assert admin.email_of("u2") is None


@respx.mock
def test_mark_sent_only_touches_an_unsent_row():
    route = respx.patch(f"{URL}/rest/v1/reminders").mock(return_value=httpx.Response(204))
    _admin().mark_sent("a1", NOW)
    req = route.calls.last.request
    q = dict(req.url.params)
    assert q == {"answer_id": "eq.a1", "sent_at": "is.null"}
    assert json.loads(req.content) == {"sent_at": NOW.isoformat()}


@respx.mock
def test_turn_off_says_whether_it_was_still_on():
    route = respx.patch(f"{URL}/rest/v1/reminders").mock(
        side_effect=[
            httpx.Response(200, json=[{"answer_id": "a1"}]),
            httpx.Response(200, json=[]),
        ]
    )
    admin = _admin()
    assert admin.turn_off("a1", "unsubscribed", NOW) is True
    req = route.calls.last.request
    q = dict(req.url.params)
    assert q["off_at"] == "is.null" and q["sent_at"] == "is.null"
    assert q["select"] == "answer_id"  # "*" is refused: the service role reads few columns
    assert req.headers["prefer"] == "return=representation"
    assert json.loads(req.content) == {"off_at": NOW.isoformat(), "off_reason": "unsubscribed"}
    assert admin.turn_off("a1", "unsubscribed", NOW) is False


@respx.mock
def test_a_refusal_or_an_outage_is_an_admin_error():
    respx.get(f"{URL}/rest/v1/reminders").mock(
        side_effect=[httpx.Response(403, json={}), httpx.ConnectTimeout("slow")]
    )
    admin = _admin()
    for _ in range(2):
        with pytest.raises(AdminError):
            admin.due(date(2026, 10, 16))


@pytest.mark.supabase
def test_due_then_marked_sent_is_no_longer_due_on_the_local_stack():
    from herbtwin.adapters.supabase_store import SupabaseHistoryStore
    from herbtwin.reminders import schedule
    from tests.supabase_local import local_env, signed_up
    from tests.test_scoring import _stored

    env = local_env()
    token, uid = signed_up(env)
    store = SupabaseHistoryStore(env["API_URL"], env["PUBLISHABLE_KEY"], token, uid)
    plant = store.create_plant("Basil", "ocimum basilicum", "ocimum", None)
    aid = uuid.uuid4().hex
    taken = datetime.now(UTC) - timedelta(days=4)
    stored = _stored(aid, taken).model_copy(update={"plant_id": plant.id})
    store.add_answer(stored)
    store.set_reminder(aid, schedule(stored, "Basil"))
    admin = SupabaseReminderAdmin(env["API_URL"], env["SECRET_KEY"], httpx.Client())
    today = datetime.now(UTC).date() + timedelta(days=1)
    mine = [r for r in admin.due(today) if r.answer_id == aid]
    assert len(mine) == 1 and mine[0].user_id == uid
    assert admin.followed_up(mine[0]) is False
    assert admin.email_of(uid)
    admin.mark_sent(aid, datetime.now(UTC))
    assert [r for r in admin.due(today) if r.answer_id == aid] == []
    assert admin.turn_off(aid, "unsubscribed", datetime.now(UTC)) is False  # already sent
