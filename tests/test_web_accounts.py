from herbtwin.history import MemoryHistory
from tests.fakes import FakeAuth, fake_accounts, follow
from tests.test_web import _client


def _accounts_client(tmp_path, observe=(), advise=()):
    hist, auth = MemoryHistory(), FakeAuth()
    c = _client(tmp_path, list(observe), list(advise), accounts=fake_accounts(hist, auth))
    return c, hist, auth


def _sign_in(c, auth, uid="u1", email="a@b.co"):
    h = auth.issue(uid, email)
    r = c.post("/auth/callback", data={"token_hash": h, "type": "email"}, follow_redirects=False)
    assert r.status_code == 303
    return r


def test_no_accounts_means_no_account_surfaces(tmp_path):
    c = _client(tmp_path, [], [])
    assert "Sign in" not in c.get("/").text
    assert c.get("/auth/sign-in").status_code == 404
    assert c.get("/plants").status_code == 404


def test_sign_in_page_has_the_consent_line(tmp_path):
    c, _, _ = _accounts_client(tmp_path)
    page = c.get("/auth/sign-in").text
    # 19 Oct walk: short, true to the keep flow (you keep a plant; signing in alone keeps none)
    assert "the plants you keep stay with their answers and chat" in page
    assert "Delete them any time." in page and '<a href="/privacy">Privacy</a>' in page
    assert 'href="/auth/sign-in"' in c.get("/").text


def test_sending_a_link(tmp_path):
    c, _, auth = _accounts_client(tmp_path)
    r = c.post("/auth/sign-in", data={"email": " A@B.co "})
    assert r.status_code == 200 and "Check your email" in r.text and auth.links == ["a@b.co"]
    bad = c.post("/auth/sign-in", data={"email": "nope"})
    assert bad.status_code == 400 and "valid email" in bad.text


def test_callback_sets_http_only_cookies_and_signs_in(tmp_path):
    c, _, auth = _accounts_client(tmp_path)
    r = _sign_in(c, auth)
    cookies = r.headers.get_list("set-cookie")
    assert any(
        x.startswith("herbtwin_at=") and "HttpOnly" in x and "SameSite=lax" in x for x in cookies
    )
    assert "Sign out" in c.get("/").text  # the nav says it; home no longer names the email


def test_a_used_link_says_so(tmp_path):
    c, _, auth = _accounts_client(tmp_path)
    h = auth.issue("u1", "a@b.co")
    c.post("/auth/callback", data={"token_hash": h, "type": "email"}, follow_redirects=False)
    again = c.post("/auth/callback", data={"token_hash": h, "type": "email"})
    assert again.status_code == 400
    assert "That link has expired or was already used. Send a new one." in again.text
    err = c.get("/auth/callback?error=access_denied&error_code=otp_expired")
    assert err.status_code == 400 and "already used" in err.text


def test_an_expired_access_token_is_refreshed(tmp_path):
    c, _, auth = _accounts_client(tmp_path)
    _sign_in(c, auth)
    auth.expire(c.cookies["herbtwin_at"])
    r = c.get("/")
    assert "Sign out" in r.text and any(
        x.startswith("herbtwin_at=") for x in r.headers.get_list("set-cookie")
    )


def test_a_bad_refresh_signs_out_cleanly(tmp_path):
    c, _, auth = _accounts_client(tmp_path)
    _sign_in(c, auth)
    auth.expire(c.cookies["herbtwin_at"])
    auth.refreshes.clear()
    r = c.get("/")
    assert r.status_code == 200 and 'href="/auth/sign-in"' in r.text


def test_sign_out_clears_the_cookies(tmp_path):
    c, _, auth = _accounts_client(tmp_path)
    _sign_in(c, auth)
    r = c.post("/auth/sign-out", follow_redirects=False)
    assert r.status_code == 303 and 'href="/auth/sign-in"' in c.get("/").text


def test_sign_in_while_auth_is_down_says_so(tmp_path):
    c, _, auth = _accounts_client(tmp_path)
    auth.down = True
    r = c.post("/auth/sign-in", data={"email": "a@b.co"})
    assert r.status_code == 503 and "not available right now" in r.text


def test_opening_the_link_does_not_spend_it(tmp_path):
    # mail scanners open links before the person does: only the button press signs in
    c, _, auth = _accounts_client(tmp_path)
    h = auth.issue("u1", "a@b.co")
    page = c.get(f"/auth/callback?token_hash={h}&type=email")
    assert page.status_code == 200 and h in auth.hashes
    assert 'method="post" action="/auth/callback"' in page.text and f'value="{h}"' in page.text
    assert "herbtwin_at" not in page.headers.get("set-cookie", "")


def test_a_sign_in_posted_from_another_site_is_refused(tmp_path):
    c, _, auth = _accounts_client(tmp_path)
    h = auth.issue("u1", "a@b.co")
    r = c.post(
        "/auth/callback",
        data={"token_hash": h, "type": "email"},
        headers={"origin": "https://evil.example"},
    )
    assert r.status_code == 403 and h in auth.hashes


def test_an_auth_outage_keeps_the_cookies_and_says_history_is_down(tmp_path):
    import json

    import httpx
    import respx

    from herbtwin.stages.environment import OPEN_METEO_URL
    from tests.test_web import ADV, JPEG, OBS, SAMPLE

    with respx.mock:
        respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
        c, _, auth = _accounts_client(tmp_path, [json.dumps(OBS)], [json.dumps(ADV)] * 3)
        _sign_in(c, auth)
        auth.down = True
        raw = c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")})
        r = follow(c, raw)
    assert r.status_code == 200 and "Water it." in r.text
    assert "History is not available right now." in r.text
    assert not any(
        x.startswith('herbtwin_at=""') or "Max-Age=0" in x
        for x in raw.headers.get_list("set-cookie")
    )
