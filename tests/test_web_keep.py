"""Signing in from a signed-out answer keeps THAT answer (web/claims.py, 19 Oct)."""

import json
import re
from datetime import UTC, datetime, timedelta

import httpx
import respx
from fastapi.testclient import TestClient

from herbtwin.adapters.mock import MockAdapter
from herbtwin.config import load_settings
from herbtwin.history import MemoryHistory
from herbtwin.pipeline import Deps
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.tracing import TraceStore
from herbtwin.web import claims
from herbtwin.web.app import KEEP_ELSEWHERE, NOT_KEPT_EXPIRED, create_app
from tests.fakes import FakeAuth, fake_accounts, follow
from tests.test_web import ADV, JPEG, OBS, SAMPLE

ENV = {
    "HERBTWIN_HOME_LAT": "51.5",
    "HERBTWIN_HOME_LON": "-0.12",
    "HERBTWIN_REMINDER_SECRET": "a-test-secret",
}
NOW = datetime(2026, 10, 19, 10, tzinfo=UTC)
KEEP_LINE = "Sign in to keep this plant; you can then ask for an email when it's time to"


EVIL = {"origin": "https://evil.example"}


def _app(tmp_path, env=ENV, site_url=None):
    hist, auth, now = MemoryHistory(), FakeAuth(), [NOW]
    deps = Deps(
        observe_adapter=MockAdapter([json.dumps(OBS)] * 4),
        advise_adapter=MockAdapter([json.dumps(ADV)] * 12),
        settings=load_settings(env),
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "p",
        workers=1,
    )
    app = create_app(
        deps, clock=lambda: now[0], accounts=fake_accounts(hist, auth), site_url=site_url
    )
    return app, deps, hist, auth, now


def _answer(c) -> tuple[str, str]:
    """A signed-out upload in this browser: (answer id, the answer page)."""
    page = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    rid = re.search(r'data-answer="([0-9a-f]{32})"', page.text).group(1)
    return rid, page.text


SAME = {"sec-fetch-site": "same-origin"}  # the sign-in link tapped on the answer itself


def _sign_in(c, auth, rid: str | None, uid="u1"):
    """The sign-in round trip: the sign-in page from the answer, then the emailed link."""
    if rid is not None:
        c.get(f"/auth/sign-in?next=/answers/{rid}", headers=SAME)
    return c.post(
        "/auth/callback",
        data={"token_hash": auth.issue(uid, f"{uid}@b.co"), "type": "email"},
        follow_redirects=False,
    )


def _keep(c, rid: str):
    return c.post(f"/answers/{rid}/keep", follow_redirects=False)


@respx.mock
def test_signing_in_brings_you_back_and_one_tap_keeps_it_exactly_as_shown(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    app, deps, hist, auth, _ = _app(tmp_path)
    c = TestClient(app)
    rid, page = _answer(c)
    assert KEEP_LINE in page and f'href="/auth/sign-in?next=/answers/{rid}"' in page
    shown = app.state.answers.get(rid).latest
    asked = len(deps.advise_adapter.calls), len(deps.observe_adapter.calls)
    r = _sign_in(c, auth, rid)
    # signing in only brings you back: nothing is kept until the tap that names the account
    assert r.status_code == 303 and r.headers["location"] == f"/answers/{rid}"
    assert hist.answers == {} and hist.plants == {}
    back = c.get(f"/answers/{rid}").text
    assert f'action="/answers/{rid}/keep"' in back and "Signed in as u1@b.co." in back
    kept = _keep(c, rid)
    assert kept.status_code == 303 and kept.headers["location"] == f"/answers/{rid}?kept=1"
    # no model call: keeping only sets the owner and links the plant
    assert (len(deps.advise_adapter.calls), len(deps.observe_adapter.calls)) == asked
    [(owner, plant)] = hist.plants.values()
    owner_a, stored = hist.answers[rid]
    assert owner == owner_a == "u1" and stored.plant_id == plant.id and stored.photo_path is None
    # byte-identical to what was shown, but for the owner and plant fields
    assert stored.answer.model_dump_json() == shown.answer.model_dump_json()
    assert stored.observation.model_dump_json() == shown.observation.model_dump_json()
    assert stored.told == shown.told and stored.taken_at == shown.taken_at
    page = c.get(kept.headers["location"]).text
    assert 'id="kept"' in page and "Kept in My plants." in page
    assert hist.photos == {}  # the photo is only ever sent by the "Add my photo" tap


@respx.mock
def test_an_answer_is_kept_once(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    app, _, hist, auth, _ = _app(tmp_path)
    c = TestClient(app)
    rid, _ = _answer(c)
    _sign_in(c, auth, rid)
    _keep(c, rid)
    assert _keep(c, rid).headers["location"] == f"/answers/{rid}"  # already yours: just back
    assert len(hist.plants) == 1 and len(hist.answers) == 1
    _sign_in(c, auth, rid, uid="u2")  # the same browser, someone else's account
    assert _keep(c, rid).status_code == 409
    assert {o for o, _ in hist.answers.values()} == {"u1"}


def test_the_claim_itself_is_atomic():
    from herbtwin.answer_cache import AnswerCache
    from herbtwin.schemas import AnalysisRecord

    cache = AnswerCache(lambda: NOW)
    rec = AnalysisRecord.model_construct(record_id="a" * 32, answer=None)
    cache.put(object(), rec, claim="k")
    assert cache.claim("a" * 32, "k", "u1") and not cache.claim("a" * 32, "k", "u2")
    cache.unclaim("a" * 32, "u1")  # a failed write is undone, and can be tried again
    assert not cache.claim("a" * 32, "x", "u2") and cache.claim("a" * 32, "k", "u2")


@respx.mock
def test_another_browser_cannot_keep_it_even_with_the_link(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    app, _, hist, auth, _ = _app(tmp_path)
    rid, _ = _answer(TestClient(app))
    stranger = TestClient(app)  # a shared link, or the email opened on another device
    assert "Sign in to keep this plant" not in stranger.get(f"/answers/{rid}").text
    _sign_in(stranger, auth, None, uid="u2")
    seen = stranger.get(f"/answers/{rid}").text
    assert "/keep" not in seen and KEEP_ELSEWHERE in seen
    assert _keep(stranger, rid).status_code == 409
    assert hist.answers == {} and app.state.answers.get(rid).owner is None


@respx.mock
def test_a_forged_or_odd_claim_cookie_keeps_nothing_and_breaks_nothing(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    app, _, hist, auth, _ = _app(tmp_path)
    rid, _ = _answer(TestClient(app))
    key = app.state.answers.get(rid).claim
    forger = TestClient(app)
    forger.cookies.set(claims.KEY_COOKIE, f"{key}.{'0' * 64}")  # the right key, a wrong seal
    _sign_in(forger, auth, rid, uid="u2")
    assert _keep(forger, rid).status_code == 409 and hist.answers == {}
    # a non-ASCII cookie (the server decodes bytes it was sent) is no key, never a 500
    assert claims._unsigned("claim", "\u00e9.\u00e9", "a-test-secret") is None


@respx.mock
def test_a_sign_in_someone_else_arranged_carries_nothing_off(tmp_path):
    # login CSRF (19 Oct security review): another site opens the sign-in page with a way
    # back into the victim's answer, then signs the victim into the attacker's account
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    app, _, hist, auth, _ = _app(tmp_path)
    c = TestClient(app)
    rid, _ = _answer(c)
    c.get(f"/auth/sign-in?next=/answers/{rid}", headers={"sec-fetch-site": "cross-site"})
    assert claims.NEXT_COOKIE not in c.cookies  # no way back planted from another site
    r = _sign_in(c, auth, None, uid="attacker")
    assert r.headers["location"] == "/" and hist.answers == {}  # and nothing is kept unasked


@respx.mock
def test_a_second_person_on_a_shared_browser_never_lands_in_the_first_answer(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    app, _, hist, auth, _ = _app(tmp_path)
    c = TestClient(app)
    rid, _ = _answer(c)
    c.get(f"/auth/sign-in?next=/answers/{rid}", headers=SAME)  # person A starts, gives up
    c.get("/auth/sign-in")  # person B signs in from the menu
    assert claims.NEXT_COOKIE not in c.cookies
    assert _sign_in(c, auth, None, uid="u2").headers["location"] == "/"
    assert hist.answers == {}


@respx.mock
def test_an_answer_past_its_hour_cannot_be_kept(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    app, _, hist, auth, now = _app(tmp_path)
    c = TestClient(app)
    rid, _ = _answer(c)
    _sign_in(c, auth, rid)
    now[0] = NOW + timedelta(hours=1, minutes=1)
    r = _keep(c, rid)
    assert r.status_code == 404 and NOT_KEPT_EXPIRED.replace("'", "&#39;") in r.text
    assert hist.answers == {}


def test_next_is_only_ever_an_answer_on_this_site(tmp_path):
    app, _, _, auth, _ = _app(tmp_path)
    c = TestClient(app)
    for bad in ("//evil.example", "https://evil.example/answers/" + "a" * 32, "/plants",
                "/answers/" + "a" * 31, "/answers/" + "A" * 32, f"/answers/{'a' * 32}/../x",
                f"/answers/{'a' * 32}?x=1"):  # fmt: skip
        c.cookies.clear()
        c.get("/auth/sign-in", params={"next": bad}, headers=SAME)
        assert claims.NEXT_COOKIE not in c.cookies, bad
        assert _sign_in(c, auth, None).headers["location"] == "/", bad
    assert claims.safe_next("/answers/" + "a" * 32) == "/answers/" + "a" * 32


@respx.mock
def test_check_your_email_says_to_open_the_link_on_this_device(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    app, *_ = _app(tmp_path)
    c = TestClient(app)
    rid, _ = _answer(c)
    c.get(f"/auth/sign-in?next=/answers/{rid}", headers=SAME)
    sent = c.post("/auth/sign-in", data={"email": "a@b.co"}).text
    assert "<h1>Check your email</h1>" in sent and "We sent a sign-in link to a@b.co." in sent
    assert "Open it on this device, then tap Keep on the answer to add it to My plants." in sent
    plain = TestClient(app).post("/auth/sign-in", data={"email": "a@b.co"}).text
    assert "Open it on this device" not in plain and "<h1>Check your email</h1>" in plain


@respx.mock
def test_the_photo_is_added_only_by_the_tap_and_only_by_its_owner(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    app, _, hist, auth, _ = _app(tmp_path)
    c = TestClient(app)
    rid, _ = _answer(c)
    _sign_in(c, auth, rid)
    _keep(c, rid)
    assert hist.answers[rid][1].photo_path is None and hist.photos == {}
    stranger = TestClient(app)
    _sign_in(stranger, auth, None, uid="u2")
    files = {"photo": ("p.jpg", JPEG, "image/jpeg")}
    assert stranger.post(f"/answers/{rid}/photo", files=files).status_code == 404
    cross = {"origin": "https://evil.example"}
    assert c.post(f"/answers/{rid}/photo", files=files, headers=cross).status_code == 403
    assert hist.photos == {}
    assert c.post(f"/answers/{rid}/photo", files=files).status_code == 204
    assert hist.answers[rid][1].photo_path and len(hist.photos) == 2  # the photo and its thumb
    assert c.post(f"/answers/{rid}/photo", files=files).status_code == 404  # once only


@respx.mock
def test_a_kept_answer_like_an_existing_plant_asks_which_and_still_calls_no_model(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    app, deps, hist, auth, _ = _app(tmp_path)
    first = TestClient(app)
    rid1, _ = _answer(first)
    _sign_in(first, auth, rid1)
    _keep(first, rid1)  # u1 now has a basil
    c = TestClient(app)
    rid, _ = _answer(c)
    shown = app.state.answers.get(rid).latest
    asked = len(deps.advise_adapter.calls)
    _sign_in(c, auth, rid)
    assert _keep(c, rid).headers["location"] == f"/answers/{rid}/plant"
    assert app.state.answers.get(rid).owner is None  # not kept until the plant is chosen
    assert c.get(f"/answers/{rid}/plant").status_code == 200
    [pid] = [p.id for _, p in hist.plants.values()]
    chosen = c.post(f"/answers/{rid}/plant", data={"plant_id": pid}, follow_redirects=False)
    assert chosen.headers["location"] == f"/answers/{rid}?kept=1"
    assert len(deps.advise_adapter.calls) == asked
    stored = hist.answers[rid][1]
    assert stored.plant_id == pid
    assert stored.answer.model_dump_json() == shown.answer.model_dump_json()


@respx.mock
def test_a_failed_store_leaves_no_empty_plant_and_can_be_tried_again(tmp_path, monkeypatch):
    from herbtwin.history import HistoryError, MemoryHistoryStore

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    app, deps, hist, auth, _ = _app(tmp_path)
    c = TestClient(app)
    rid, _ = _answer(c)
    _sign_in(c, auth, rid)
    real = MemoryHistoryStore.add_answer

    def down(self, a):
        raise HistoryError("down")

    monkeypatch.setattr(MemoryHistoryStore, "add_answer", down)
    asked = len(deps.advise_adapter.calls)
    assert _keep(c, rid).status_code == 503
    assert hist.plants == {} and app.state.answers.get(rid).owner is None
    assert len(deps.advise_adapter.calls) == asked  # never decided again, even on failure
    monkeypatch.setattr(MemoryHistoryStore, "add_answer", real)
    assert _keep(c, rid).headers["location"] == f"/answers/{rid}?kept=1"
    assert len(hist.plants) == 1


@respx.mock
def test_without_the_reminder_secret_nothing_is_claimed_and_the_old_line_stays(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    env = {k: v for k, v in ENV.items() if k != "HERBTWIN_REMINDER_SECRET"}
    app, _, hist, auth, _ = _app(tmp_path, env)
    c = TestClient(app)
    rid, page = _answer(c)
    assert claims.KEY_COOKIE not in c.cookies and "Sign in to keep this plant" not in page
    assert "Sign in, then send this photo again" in page
    assert _sign_in(c, auth, rid).headers["location"] == "/"
    assert _keep(c, rid).status_code == 409 and hist.answers == {}


@respx.mock
def test_your_own_answer_opened_on_another_browser_says_where_to_keep_it(tmp_path):
    # the emailed link opened on the phone, the answer made on the laptop
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    app, _, hist, auth, _ = _app(tmp_path)
    laptop, phone = TestClient(app), TestClient(app)
    rid, _ = _answer(laptop)
    laptop.get(f"/auth/sign-in?next=/answers/{rid}", headers=SAME)
    _sign_in(phone, auth, None, uid="u1")
    seen = phone.get(f"/answers/{rid}").text
    assert KEEP_ELSEWHERE in seen and f'action="/answers/{rid}/keep"' not in seen
    assert "could not be kept" not in seen  # nothing was tried, so nothing failed
    assert hist.answers == {}


@respx.mock
def test_keep_and_choose_refuse_another_sites_form_and_another_accounts_plant(tmp_path):
    # the boundaries themselves (19 Oct security review, round 2): deleting a check fails here
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    app, _, hist, auth, _ = _app(tmp_path)
    first = TestClient(app)
    rid1, _ = _answer(first)
    _sign_in(first, auth, rid1)
    _keep(first, rid1)  # u1 has a basil
    other = TestClient(app)
    rid2, _ = _answer(other)
    _sign_in(other, auth, rid2, uid="u9")
    _keep(other, rid2)  # so has u9
    u9_plant = next(p.id for o, p in hist.plants.values() if o == "u9")
    c = TestClient(app)
    rid, _ = _answer(c)
    _sign_in(c, auth, rid)
    keep = c.post(f"/answers/{rid}/keep", headers=EVIL, follow_redirects=False)
    assert keep.status_code == 403 and rid not in hist.answers
    assert _keep(c, rid).headers["location"] == f"/answers/{rid}/plant"
    pick = {"plant_id": u9_plant}
    cross = c.post(f"/answers/{rid}/plant", data=pick, headers=EVIL, follow_redirects=False)
    assert cross.status_code == 403
    foreign = c.post(f"/answers/{rid}/plant", data=pick, follow_redirects=False)
    assert foreign.status_code == 404 and rid not in hist.answers  # not one it offered
    _sign_in(c, auth, None, uid="u2")  # another account, the same browser
    u1_plant = next(p.id for o, p in hist.plants.values() if o == "u1")
    c.post(f"/answers/{rid}/plant", data={"plant_id": u1_plant}, follow_redirects=False)
    assert rid not in hist.answers and c.get(f"/answers/{rid}/plant").status_code == 404


@respx.mock
def test_without_sec_fetch_site_only_this_sites_own_answer_page_sets_the_way_back(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    app, *_ = _app(tmp_path, site_url="https://herbtwin.example")
    c = TestClient(app)
    rid, _ = _answer(c)
    for ref in (None, f"https://evil.example/answers/{rid}", "http://testserver/plants"):
        c.cookies.clear()
        c.get(f"/auth/sign-in?next=/answers/{rid}", headers={"referer": ref} if ref else {})
        assert claims.NEXT_COOKIE not in c.cookies, ref
    for ref in (f"http://testserver/answers/{rid}", f"https://herbtwin.example/answers/{rid}"):
        c.cookies.clear()
        c.get(f"/auth/sign-in?next=/answers/{rid}", headers={"referer": ref})
        assert claims.NEXT_COOKIE in c.cookies, ref  # behind the edge: the public site counts


@respx.mock
def test_signing_out_forgets_this_browsers_key_and_way_back(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    app, _, _, auth, _ = _app(tmp_path)
    c = TestClient(app)
    rid, _ = _answer(c)
    c.get(f"/auth/sign-in?next=/answers/{rid}", headers=SAME)
    r = c.post("/auth/sign-out", follow_redirects=False)
    gone = " ".join(r.headers.get_list("set-cookie"))
    assert f"{claims.KEY_COOKIE}=" in gone and f"{claims.NEXT_COOKIE}=" in gone


@respx.mock
def test_the_answer_page_is_never_framed_by_another_site(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    app, *_ = _app(tmp_path)
    c = TestClient(app)
    rid, _ = _answer(c)
    r = c.get(f"/answers/{rid}")
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


@respx.mock
def test_a_stranger_with_a_key_of_their_own_cannot_keep_someone_elses_answer(tmp_path):
    # the realistic attacker (19 Oct integrator review): has uploaded once, so holds a valid,
    # signed key, just not this answer's; signed in, with the victim's shared link
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    app, _, hist, auth, _ = _app(tmp_path)
    victim = TestClient(app)
    rid, _ = _answer(victim)
    stranger = TestClient(app)
    _answer(stranger)  # a key of their own
    assert claims._unsigned("claim", stranger.cookies.get(claims.KEY_COOKIE), "a-test-secret")
    _sign_in(stranger, auth, None, uid="u2")
    seen = stranger.get(f"/answers/{rid}").text
    assert f'action="/answers/{rid}/keep"' not in seen and KEEP_ELSEWHERE in seen
    assert _keep(stranger, rid).status_code == 409
    assert stranger.get(f"/answers/{rid}/plant").status_code == 404
    assert rid not in hist.answers and app.state.answers.get(rid).owner is None


@respx.mock
def test_the_signed_out_chat_goes_with_the_kept_answer(tmp_path):
    from herbtwin.history import ChatMessage

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    app, _, hist, auth, _ = _app(tmp_path)
    c = TestClient(app)
    rid, _ = _answer(c)
    said = ChatMessage(role="user", content="Can I move it inside?", created_at=NOW)
    assert app.state.answers.add_chat(rid, said)
    _sign_in(c, auth, rid)
    _keep(c, rid)
    assert [(o, a, m.content) for o, a, m in hist.chats] == [("u1", rid, "Can I move it inside?")]


@respx.mock
def test_a_failed_chat_copy_never_stores_the_answer_twice(tmp_path, monkeypatch):
    # 19 Oct integrator follow-up: the chat copy is best-effort once the answer is kept
    from herbtwin.history import ChatMessage, HistoryError, MemoryHistoryStore

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    app, _, hist, auth, _ = _app(tmp_path)
    c = TestClient(app)
    rid, _ = _answer(c)
    app.state.answers.add_chat(rid, ChatMessage(role="user", content="hi", created_at=NOW))
    _sign_in(c, auth, rid)

    def down(self, answer_id, msg):
        raise HistoryError("down")

    monkeypatch.setattr(MemoryHistoryStore, "add_chat", down)
    assert _keep(c, rid).headers["location"] == f"/answers/{rid}?kept=1"
    assert list(hist.answers) == [rid] and len(hist.plants) == 1
