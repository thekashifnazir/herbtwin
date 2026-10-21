"""The judges' code (spec D59): a signed cookie that skips the caps, 10 tries a day."""

from datetime import date

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from herbtwin.adapters.mock import MockAdapter
from herbtwin.config import load_settings
from herbtwin.pipeline import Deps
from herbtwin.tracing import TraceStore
from herbtwin.web.app import create_app
from herbtwin.web.judge import COOKIE, Attempts, is_judge, judge_token

CODE = "letmein42"


def _client(tmp_path, env: dict[str, str] | None = None) -> TestClient:
    deps = Deps(
        observe_adapter=MockAdapter([]),
        advise_adapter=MockAdapter([]),
        settings=load_settings({"HERBTWIN_JUDGE_CODE": CODE} if env is None else env),
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "p",
        workers=1,
    )
    return TestClient(create_app(deps))


def test_judge_page_shows_the_form(tmp_path):
    r = _client(tmp_path).get("/judge")
    assert r.status_code == 200 and 'name="code"' in r.text


def test_right_code_sets_an_http_only_cookie(tmp_path):
    c = _client(tmp_path)
    r = c.post("/judge", data={"code": CODE})
    assert r.status_code == 200 and "You're in" in r.text
    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}={judge_token(CODE)}")
    assert "HttpOnly" in cookie and "Max-Age=5184000" in cookie  # 60 days
    assert "Secure" not in cookie  # the test site is not https
    assert CODE not in cookie


def test_wrong_code_gets_the_form_back_and_no_cookie(tmp_path):
    r = _client(tmp_path).post("/judge", data={"code": "nope"})
    assert "That code didn't work" in r.text and 'name="code"' in r.text
    assert "set-cookie" not in r.headers


def test_eleventh_try_refused_even_with_the_right_code(tmp_path):
    c = _client(tmp_path)
    for _ in range(10):
        assert "That code didn't work" in c.post("/judge", data={"code": "nope"}).text
    r = c.post("/judge", data={"code": CODE})
    assert r.status_code == 429 and "Too many tries today" in r.text
    assert "set-cookie" not in r.headers


def test_a_right_code_never_uses_a_try(tmp_path):
    # judges on one venue Wi-Fi share an IP: twelve of them signing in must all get in,
    # and the wrong tries left are still ten
    c = _client(tmp_path)
    for _ in range(12):
        r = c.post("/judge", data={"code": CODE})
        assert r.status_code == 200 and "You're in" in r.text
    for _ in range(10):
        assert "That code didn't work" in c.post("/judge", data={"code": "nope"}).text
    assert c.post("/judge", data={"code": "nope"}).status_code == 429


def test_attempts_count_only_what_is_counted():
    a, day = Attempts(), date(2026, 10, 12)
    assert all(a.allow(day, "v", count=False) for _ in range(50))
    assert all(a.allow(day, "v") for _ in range(10))
    assert not a.allow(day, "v")
    assert not a.allow(day, "v", count=False)  # blocked stays blocked, right code or not


def test_no_code_configured_has_no_judge_page(tmp_path):
    c = _client(tmp_path, {})
    assert c.get("/judge").status_code == 404
    assert c.post("/judge", data={"code": "x"}).status_code == 404


def _judge_app(code: str | None) -> TestClient:
    app = FastAPI()

    @app.get("/me")
    def me(request: Request) -> dict:
        return {"judge": is_judge(request, code)}

    return TestClient(app)


def test_is_judge_with_the_right_cookie():
    c = _judge_app(CODE)
    c.cookies.set(COOKIE, judge_token(CODE))
    assert c.get("/me").json()["judge"] is True


def test_is_judge_false_for_a_tampered_cookie():
    c = _judge_app(CODE)
    c.cookies.set(COOKIE, judge_token(CODE)[:-1] + "0")
    assert c.get("/me").json()["judge"] is False
    c.cookies.set(COOKIE, judge_token("another"))
    assert c.get("/me").json()["judge"] is False


def test_is_judge_false_when_no_code_configured():
    c = _judge_app(None)
    c.cookies.set(COOKIE, judge_token(""))
    assert c.get("/me").json()["judge"] is False


def test_attempts_ten_a_day_per_visitor():
    a, day = Attempts(), date(2026, 10, 12)
    assert all(a.allow(day, "v") for _ in range(10))
    assert not a.allow(day, "v")
    assert a.allow(day, "w")  # another visitor
    assert a.allow(date(2026, 10, 13), "v")  # a new day


def test_cookie_is_secure_on_an_https_site(tmp_path):
    deps = Deps(
        observe_adapter=MockAdapter([]),
        advise_adapter=MockAdapter([]),
        settings=load_settings({"HERBTWIN_JUDGE_CODE": CODE}),
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "p",
        workers=1,
    )
    c = TestClient(create_app(deps, site_url="https://herbtwin.example"))
    cookie = c.post("/judge", data={"code": CODE}).headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=") and "Secure" in cookie and "HttpOnly" in cookie


def test_in_the_judge_is_sent_to_the_home_page_for_the_full_visit(tmp_path):
    # 21 Oct, Kash: make it clear they can go back to the home page and get the full
    # experience from the start; the samples are a shortcut
    page = _client(tmp_path).post("/judge", data={"code": CODE}).text
    home = page.split('<div class="judge-home">', 1)[1].split("</div>", 1)[0]
    assert '<a class="button primary" href="/">Start from the home page</a>' in home
    assert "The full visit, as anyone sees it" in home
    assert page.index("judge-home") < page.index("Or a quick look: one tap each")
    main = page.split("<main", 1)[1]
    assert main.count("primary") == 1  # one green button
    # before the code, the code's own button is the green one, and no home button jumps the queue
    (tmp_path / "b").mkdir()
    first = _client(tmp_path / "b").get("/judge").text
    assert 'class="judge-home"' not in first
