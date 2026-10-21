import json

import httpx
import respx

from herbtwin.auth import AuthError
from herbtwin.stages.environment import OPEN_METEO_URL
from tests.test_web import ADV, SAMPLE
from tests.test_web_history import SAGE, _signed_in, _upload


@respx.mock
def test_delete_account_removes_photos_rows_and_sign_in(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, hist, auth = _signed_in(tmp_path, [json.dumps(SAGE)], [json.dumps(ADV)] * 3)
    _upload(c, place="")
    r = c.post("/account/delete", data={"confirm": "delete"})
    assert r.status_code == 200 and "Your account and everything in it are deleted." in r.text
    assert "u1" not in auth.users and not any(k.startswith("u1/") for k in hist.photos)
    assert 'href="/auth/sign-in"' in c.get("/").text  # signed out


@respx.mock
def test_delete_fails_closed_when_it_cannot_confirm(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, hist, auth = _signed_in(tmp_path, [json.dumps(SAGE)], [json.dumps(ADV)] * 3)
    _upload(c, place="")
    real_delete = auth.delete_user
    auth.delete_user = lambda uid: None  # the delete call "succeeds" but nothing happened
    r = c.post("/account/delete", data={"confirm": "delete"})
    assert r.status_code == 503 and "Could not" in r.text
    auth.delete_user = real_delete
    auth.down = True  # and a lookup that fails is not an answer either
    assert c.post("/account/delete", data={"confirm": "delete"}).status_code == 503


def test_delete_needs_the_secret_key(tmp_path):
    from herbtwin.history import MemoryHistory
    from tests.fakes import FakeAuth, fake_accounts
    from tests.test_web import _client

    hist, auth = MemoryHistory(), FakeAuth()
    acc = fake_accounts(hist, auth)
    acc.delete_folder = None  # no secret key on this server
    c = _client(tmp_path, [], [], accounts=acc)
    c.post(
        "/auth/callback",
        data={"token_hash": auth.issue("u1", "a@b.co"), "type": "email"},
        follow_redirects=False,
    )
    r = c.post("/account/delete", data={"confirm": "delete"})
    assert r.status_code == 503 and "not set up" in r.text and "u1" in auth.users


@respx.mock
def test_a_retried_delete_reports_success_and_sweeps_again(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, hist, auth = _signed_in(tmp_path, [json.dumps(SAGE)], [json.dumps(ADV)] * 3)
    _upload(c, place="")
    real_exists = auth.user_exists

    def lookup_times_out(uid):
        raise AuthError("Could not confirm the account is gone. Try again.")

    auth.user_exists = lookup_times_out  # the user is deleted, then the check times out
    assert c.post("/account/delete", data={"confirm": "delete"}).status_code == 503
    assert "u1" not in auth.users
    hist.photos["u1/straggler.jpg"] = b"late"  # a photo stored between sweep and delete
    auth.user_exists = real_exists
    again = c.post("/account/delete", data={"confirm": "delete"})
    assert again.status_code == 200 and "already deleted" in again.text
    assert not any(k.startswith("u1/") for k in hist.photos)


@respx.mock
def test_deleting_the_account_needs_the_word_typed(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    c, hist, auth = _signed_in(tmp_path, [json.dumps(SAGE)], [json.dumps(ADV)] * 3)
    _upload(c, place="")
    page = c.get("/account/delete")
    assert page.status_code == 200 and 'name="confirm"' in page.text
    r = c.post("/account/delete")  # one tap, nothing typed
    assert r.status_code == 400 and "u1" in auth.users
    assert hist.for_user("u1").list_plants() != []
