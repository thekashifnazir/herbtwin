"""The signed-in answer page's history reads (23 Oct audit): the stored answer read once,
the chat, the check-up and the reminder box read side by side, one failed read never
taking the page down, one kept-open Supabase client per app, and the sign-in check made
once per request."""

import asyncio
import json
import threading
import time
from dataclasses import dataclass, field, replace
from datetime import timedelta

import httpx
import pytest
import respx
from fastapi import Request
from fastapi.testclient import TestClient

from herbtwin import scoring
from herbtwin.adapters import supabase_store
from herbtwin.adapters.mock import MockAdapter
from herbtwin.answer_cache import AnswerCache
from herbtwin.config import load_settings
from herbtwin.history import ChatMessage, HistoryError, MemoryHistory
from herbtwin.pipeline import Deps
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.tracing import TraceStore
from herbtwin.web.accounts import ACCESS, accounts_from, signed_in, supabase_client
from herbtwin.web.app import create_app
from tests.fakes import FakeAuth, fake_accounts, follow
from tests.test_web import ADV, JPEG, OBS, OCT_4, SAMPLE
from tests.test_web_checkup import PASSED

DELAY = 0.1  # seconds per fake round trip
ASK = "On 4 Oct we suggested watering it. Did you do it?"
BOX = "Email me when it's time to check again"


@dataclass
class Calls:
    """Every history and sign-in call the fakes saw, and how many ran at once."""

    delay: float = 0.0
    fail: set[str] = field(default_factory=set)
    names: list[str] = field(default_factory=list)
    running: int = 0
    most: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)
    together: set[str] = field(default_factory=set)  # these wait for each other
    barrier: threading.Barrier | None = None

    def call(self, name: str, fn, *a, **kw):
        with self.lock:
            self.names.append(name)
            self.running += 1
            self.most = max(self.most, self.running)
        try:
            if name in self.together and self.barrier is not None:
                # breaks (and the page fails) unless all of them are running at once
                self.barrier.wait(timeout=5)
            time.sleep(self.delay)
            if name in self.fail:
                raise HistoryError("History is not available right now.")
            return fn(*a, **kw)
        finally:
            with self.lock:
                self.running -= 1

    def reset(self, delay: float = 0.0) -> None:
        self.names.clear()
        self.most, self.delay = 0, delay


class SlowStore:
    """The memory store with a round trip's delay on every call."""

    def __init__(self, inner, calls: Calls) -> None:
        self.inner, self.calls = inner, calls

    def __getattr__(self, name):
        fn = getattr(self.inner, name)
        return lambda *a, **kw: self.calls.call(name, fn, *a, **kw)


@dataclass
class SlowAuth(FakeAuth):
    calls: Calls = field(default_factory=Calls)

    def user(self, access_token):
        return self.calls.call("auth.user", super().user, access_token)


@pytest.fixture(autouse=True)
def _gate(monkeypatch):
    monkeypatch.setattr(scoring, "load_gate", lambda: PASSED)


@pytest.fixture(autouse=True)
def _weather():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
        yield


def signed_in_answer(tmp_path):
    """A signed-in person's second photo of a plant: a check-up due, a chat under it and
    a reminder ticked. Returns the client, the answer id and the call log."""
    calls = Calls()
    hist, auth = MemoryHistory(), SlowAuth(calls=calls)
    accounts = fake_accounts(hist, auth)
    accounts = replace(accounts, store_for=lambda uid, token: SlowStore(hist.for_user(uid), calls))
    now = [OCT_4]
    deps = Deps(
        observe_adapter=MockAdapter([json.dumps(OBS)] * 2),
        advise_adapter=MockAdapter([json.dumps(ADV)] * 9),
        settings=load_settings(
            {
                "HERBTWIN_HOME_LAT": "51.5",
                "HERBTWIN_HOME_LON": "-0.12",
                "HERBTWIN_REMINDER_SECRET": "rs",
            }
        ),
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "p",
        workers=1,
    )
    app = create_app(deps, clock=lambda: now[0], accounts=accounts, site_url="https://x.test")
    c = TestClient(app, base_url="https://x.test")
    c.post(
        "/auth/callback",
        data={"token_hash": auth.issue("u1", "u1@b.co"), "type": "email"},
        follow_redirects=False,
    )
    upload = {"files": {"photo": ("s.jpg", JPEG, "image/jpeg")}, "data": {"place": ""}}
    follow(c, c.post("/analyse", **upload))
    now[0] = OCT_4 + timedelta(days=3)
    chooser = follow(c, c.post("/analyse", **upload))
    rid = chooser.text.split('action="/answers/')[1].split("/plant")[0]
    store = hist.for_user("u1")
    c.post(f"/answers/{rid}/plant", data={"plant_id": store.list_plants()[0].id})
    store.add_chat(rid, ChatMessage(role="user", content="Is it thirsty?"))
    store.add_chat(rid, ChatMessage(role="assistant", content="Yes: water it today."))
    assert c.post(f"/answers/{rid}/reminder", data={"on": "1"}).status_code == 200
    return c, rid, calls


def _timed(c, path: str, calls: Calls):
    calls.reset(DELAY)
    t = time.perf_counter()
    page = c.get(path)
    return page, time.perf_counter() - t


def _shows_everything(page) -> None:
    assert page.status_code == 200
    assert ASK in page.text and BOX in page.text and "Is it thirsty?" in page.text


@pytest.mark.parametrize("cached", [True, False])
def test_the_answer_page_reads_the_answer_once(tmp_path, cached):
    c, rid, calls = signed_in_answer(tmp_path)
    if not cached:  # a visit from an earlier day: only stored history has it
        c.app.state.answers = AnswerCache(lambda: OCT_4 + timedelta(days=3))
    page, _ = _timed(c, f"/answers/{rid}", calls)
    _shows_everything(page)
    assert calls.names.count("get_answer") == 1
    assert calls.names.count("auth.user") == 1
    # the sign-in check, the answer, then chat, visits, scores, plants and the reminder
    assert len(calls.names) <= 7, calls.names


def test_the_answer_page_reads_side_by_side(tmp_path):
    """The first read of the chat, the check-up and the reminder box wait for each other:
    read one after another, the first would wait alone and the page would fail."""
    c, rid, calls = signed_in_answer(tmp_path)
    calls.together = {"chat_for", "answers_for", "list_plants"}
    calls.barrier = threading.Barrier(3)
    page, _ = _timed(c, f"/answers/{rid}", calls)
    _shows_everything(page)
    assert not calls.barrier.broken and calls.most >= 3


@pytest.mark.parametrize(
    ("down", "gone", "kept"),
    [
        ("chat_for", "Is it thirsty?", [ASK, BOX]),
        ("answers_for", ASK, ["Is it thirsty?", BOX]),
        ("scores_for", ASK, ["Is it thirsty?", BOX]),
        ("list_plants", BOX, ["Is it thirsty?", ASK]),
        ("get_reminder", BOX, ["Is it thirsty?", ASK]),
    ],
)
def test_one_failed_read_still_shows_the_answer(tmp_path, down, gone, kept):
    c, rid, calls = signed_in_answer(tmp_path)
    calls.fail = {down}
    page, _ = _timed(c, f"/answers/{rid}", calls)
    assert page.status_code == 200
    assert '<h2 id="main-action">Water it.</h2>' in page.text
    assert gone not in page.text
    assert all(k in page.text for k in kept)


def test_a_failed_answer_read_still_shows_a_cached_answer(tmp_path):
    c, rid, calls = signed_in_answer(tmp_path)
    calls.fail = {"get_answer"}
    page, _ = _timed(c, f"/answers/{rid}", calls)
    assert page.status_code == 200
    assert '<h2 id="main-action">Water it.</h2>' in page.text
    assert ASK not in page.text and BOX not in page.text
    assert calls.names.count("get_answer") == 1


def test_a_failed_answer_read_of_an_uncached_answer_says_history_is_down(tmp_path):
    c, rid, calls = signed_in_answer(tmp_path)
    c.app.state.answers = AnswerCache(lambda: OCT_4 + timedelta(days=3))
    calls.fail = {"get_answer"}
    page, _ = _timed(c, f"/answers/{rid}", calls)
    assert page.status_code == 503


def test_one_kept_open_client_serves_every_supabase_call(monkeypatch):
    """Sign-in, every person's store and the photo sweep share one pooled client, made
    once per app, so the page's reads reuse open connections."""
    settings = load_settings(
        {
            "HERBTWIN_SUPABASE_URL": "https://sb.test",
            "HERBTWIN_SUPABASE_PUBLISHABLE_KEY": "pk",
            "HERBTWIN_SUPABASE_SECRET_KEY": "sk",
        }
    )
    seen = []
    monkeypatch.setattr(supabase_store, "delete_folder", lambda *a: seen.append(a) or 0)
    acc = accounts_from(settings)
    http = acc.auth.http
    assert acc.store_for("u1", "t1").http is http and acc.store_for("u2", "t2").http is http
    acc.delete_folder("u1")
    assert seen[0][-1] is http


def test_the_sign_in_check_is_made_once_per_request(tmp_path):
    """However often a request asks who is signed in, Supabase Auth is asked once."""
    c, _, calls = signed_in_answer(tmp_path)
    token = c.cookies.get(ACCESS)
    request = Request({"type": "http", "headers": [(b"cookie", f"{ACCESS}={token}".encode())]})
    calls.reset()

    async def twice():
        return await signed_in(request, c.app.state.accounts), await signed_in(
            request, c.app.state.accounts
        )

    first, again = asyncio.run(twice())
    assert first[0] is again[0] and first[1] is again[1] and first[0].user_id == "u1"
    assert calls.names == ["auth.user"]


def _shared_settings():
    return load_settings(
        {"HERBTWIN_SUPABASE_URL": "https://sb.test", "HERBTWIN_SUPABASE_PUBLISHABLE_KEY": "pk"}
    )


def test_two_people_on_the_shared_client_each_send_their_own_token():
    acc = accounts_from(_shared_settings())
    sent: list[tuple[str, str]] = []

    def answer(request):
        time.sleep(0.02)  # overlap the two people's reads
        sent.append(
            (request.url.params["answer_id"].removeprefix("eq."), request.headers["authorization"])
        )
        return httpx.Response(200, json=[])

    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://sb.test/rest/v1/chat_messages").mock(side_effect=answer)
        a, b = acc.store_for("u1", "token-a"), acc.store_for("u2", "token-b")
        threads = [
            threading.Thread(target=s.chat_for, args=(aid,))
            for s, aid in [(a, "a1"), (b, "b1"), (a, "a2"), (b, "b2")] * 3
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    assert len(sent) == 12
    assert all(tok == f"Bearer token-{aid[0]}" for aid, tok in sent)


def test_the_shared_client_keeps_no_cookies_between_people():
    """A cookie a response sets (Cloudflare's, say) is never replayed to someone else."""
    http = supabase_client()
    with respx.mock() as mock:
        route = mock.get("https://sb.test/x").mock(
            return_value=httpx.Response(200, headers={"set-cookie": "__cf_bm=abc; Path=/"})
        )
        http.get("https://sb.test/x")
        http.get("https://sb.test/x")
    assert "cookie" not in route.calls[1].request.headers
    assert len(http.cookies) == 0


def test_the_shared_client_is_closed_when_the_app_stops(tmp_path):
    http = supabase_client()
    accounts = replace(fake_accounts(MemoryHistory(), FakeAuth()), http=http)
    deps = Deps(
        observe_adapter=MockAdapter([]),
        advise_adapter=MockAdapter([]),
        settings=load_settings({}),
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "p",
    )
    with TestClient(create_app(deps, accounts=accounts)):
        assert not http.is_closed
    assert http.is_closed
