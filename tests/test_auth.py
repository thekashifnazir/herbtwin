from datetime import UTC, datetime

import httpx
import pytest
import respx

from herbtwin.auth import EXPIRED_LINK, AuthError, SupabaseAuth, valid_email

URL = "https://proj.supabase.co"
SESSION = {
    "access_token": "at",
    "refresh_token": "rt",
    "expires_in": 3600,
    "user": {"id": "u1", "email": "a@b.co"},
}


def _auth(secret=None):
    return SupabaseAuth(URL, "sb_publishable_x", secret, client=httpx.Client())


@respx.mock
def test_send_link_posts_the_email_with_the_publishable_key():
    route = respx.post(f"{URL}/auth/v1/otp").mock(return_value=httpx.Response(200, json={}))
    _auth().send_link("a@b.co")
    req = route.calls.last.request
    assert req.headers["apikey"] == "sb_publishable_x"
    assert req.read() == b'{"email":"a@b.co","create_user":true}'


@respx.mock
def test_verify_spends_the_token_hash_and_returns_a_session():
    route = respx.post(f"{URL}/auth/v1/verify").mock(return_value=httpx.Response(200, json=SESSION))
    s = _auth().verify("hash123", "email")
    assert route.calls.last.request.read() == b'{"type":"email","token_hash":"hash123"}'
    assert (s.access_token, s.refresh_token, s.user_id, s.email) == ("at", "rt", "u1", "a@b.co")
    assert s.expires_at > datetime.now(UTC)


@respx.mock
def test_a_used_or_expired_link_is_reported_as_such():
    respx.post(f"{URL}/auth/v1/verify").mock(
        return_value=httpx.Response(
            403, json={"code": "otp_expired", "msg": "Token has expired or is invalid"}
        )
    )
    with pytest.raises(AuthError) as e:
        _auth().verify("old", "email")
    assert e.value.expired and str(e.value) == EXPIRED_LINK


@respx.mock
def test_an_unreachable_server_is_an_auth_error_not_a_crash():
    respx.post(f"{URL}/auth/v1/otp").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(AuthError) as e:
        _auth().send_link("a@b.co")
    assert not e.value.expired


@respx.mock
def test_refresh_and_user():
    respx.post(f"{URL}/auth/v1/token", params={"grant_type": "refresh_token"}).mock(
        return_value=httpx.Response(200, json=SESSION)
    )
    respx.get(f"{URL}/auth/v1/user").mock(
        side_effect=lambda r: (
            httpx.Response(200, json={"id": "u1", "email": "a@b.co"})
            if r.headers["authorization"] == "Bearer at"
            else httpx.Response(401, json={})
        )
    )
    a = _auth()
    assert a.refresh("rt").access_token == "at"
    assert a.user("at") == ("u1", "a@b.co") and a.user("stale") is None


@respx.mock
def test_admin_calls_use_the_secret_key_and_fail_closed():
    respx.delete(f"{URL}/auth/v1/admin/users/u1").mock(return_value=httpx.Response(200, json={}))
    looks = respx.get(f"{URL}/auth/v1/admin/users/u1")
    a = _auth(secret="sb_secret_x")
    a.delete_user("u1")
    looks.mock(return_value=httpx.Response(404, json={"code": "user_not_found"}))
    assert a.user_exists("u1") is False
    looks.mock(return_value=httpx.Response(500, json={}))
    with pytest.raises(AuthError):
        a.user_exists("u1")  # a failed lookup is not an answer
    with pytest.raises(AuthError):
        _auth().delete_user("u1")  # no secret key configured


def test_valid_email():
    assert valid_email("  A@B.co ") == "a@b.co"
    for bad in ("", "nope", "a@b", "a b@c.co", "x" * 250 + "@b.co"):
        with pytest.raises(ValueError):
            valid_email(bad)


@respx.mock
def test_only_a_refused_refresh_token_means_signed_out():
    route = respx.post(f"{URL}/auth/v1/token", params={"grant_type": "refresh_token"})
    route.mock(return_value=httpx.Response(400, json={"code": "refresh_token_not_found"}))
    with pytest.raises(AuthError) as e:
        _auth().refresh("rt")
    assert e.value.expired
    route.mock(return_value=httpx.Response(503, json={}))
    with pytest.raises(AuthError) as e:
        _auth().refresh("rt")
    assert not e.value.expired  # an outage is not a sign-out


def test_token_subject_reads_the_user_id_from_a_jwt():
    import base64
    import json

    body = base64.urlsafe_b64encode(json.dumps({"sub": "u-123"}).encode()).decode().rstrip("=")
    assert SupabaseAuth.token_subject(f"h.{body}.sig") == "u-123"
    assert SupabaseAuth.token_subject("not-a-jwt") is None
    assert SupabaseAuth.token_subject("a.!!!.c") is None
