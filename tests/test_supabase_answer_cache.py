"""Answers in Supabase for 24 hours (answer_cache.SupabaseAnswerCache, 25 Oct): the same
rules as the in-memory cache, against a fake PostgREST that follows
supabase/migrations/20261025120000_answer_cache.sql. Offline."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from herbtwin.adapters.mock import MockAdapter
from herbtwin.advice_context import WeatherFacts
from herbtwin.answer_cache import (
    KEEP,
    AnswerCache,
    SupabaseAnswerCache,
    claim_hash,
    reading_from_json,
    reading_to_json,
)
from herbtwin.config import load_settings
from herbtwin.history import ChatMessage, MemoryHistory
from herbtwin.pipeline import Deps
from herbtwin.schemas import SpeciesCandidate, StageFailure
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.tracing import TraceStore
from herbtwin.web import claims
from herbtwin.web.app import _answers_from, create_app
from tests.fakes import FakeAuth, fake_accounts, follow
from tests.test_answer_cache import _reading
from tests.test_web import ADV, JPEG, OBS, SAMPLE

T0 = datetime(2026, 10, 25, 9, tzinfo=UTC)
URL, SECRET = "https://sb.test", "sb_secret_test"
RID = "a" * 32


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now


def _at(v: str) -> datetime:
    return datetime.fromisoformat(v)


class FakeSupabase:
    """The answer_cache table and its three functions, as PostgREST serves them."""

    def __init__(self, clock):
        self.clock, self.rows, self.seen = clock, {}, []
        self.down: Exception | int | None = None

    def _fresh(self, row) -> bool:  # the functions' "created_at > now() - interval '24 hours'"
        return _at(row["created_at"]) > self.clock() - KEEP

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        assert request.headers["apikey"] == SECRET
        assert request.headers["authorization"] == f"Bearer {SECRET}"
        if isinstance(self.down, Exception):
            raise self.down
        if isinstance(self.down, int):
            return httpx.Response(self.down, json={"message": "down"})
        p, path = request.url.params, request.url.path
        body = json.loads(request.content) if request.content else None
        if path.startswith("/rest/v1/rpc/"):
            return self._rpc(path.rsplit("/", 1)[1], body)
        assert path == "/rest/v1/answer_cache"
        rid = p.get("id", "eq.")[3:]
        if request.method == "POST":
            assert "resolution=merge-duplicates" in request.headers["prefer"]
            self.rows[body["id"]] = {**self.rows.get(body["id"], {}), **body}
            return httpx.Response(201)
        row = self.rows.get(rid)
        if request.method == "GET":
            cutoff = _at(p["created_at"].removeprefix("gt."))
            got = [row] if row and _at(row["created_at"]) > cutoff else []
            return httpx.Response(200, json=got)
        if request.method == "DELETE":
            cutoff = _at(p["created_at"].removeprefix("lte."))
            if row and _at(row["created_at"]) <= cutoff:
                del self.rows[rid]
            return httpx.Response(204)
        if request.method == "PATCH":
            if row is None:
                return httpx.Response(204)
            if "owner" in p and row.get("owner") != p["owner"][3:]:
                return httpx.Response(204)
            if p.get("claim_hash") == "not.is.null" and row.get("claim_hash") is None:
                return httpx.Response(204)
            row.update(body)
            return httpx.Response(204)
        raise AssertionError(request.method)

    def _rpc(self, name, body) -> httpx.Response:
        if name == "claim_answer":
            row = self.rows.get(body["p_id"])
            ok = bool(
                row
                and row.get("owner") is None
                and row.get("claim_hash") == body["p_claim_hash"]
                and self._fresh(row)
            )
            if ok:
                row["owner"] = body["p_owner"]
            return httpx.Response(200, json=ok)
        if name == "add_answer_chat":
            row = self.rows.get(body["p_id"])
            ok = bool(row and self._fresh(row))
            if ok:
                row["chat"] = [*row["chat"], body["p_msg"]]
            return httpx.Response(200, json=ok)
        if name == "purge_answer_cache":
            old = [k for k, r in self.rows.items() if not self._fresh(r)]
            for k in old:
                del self.rows[k]
            return httpx.Response(200, json=len(old))
        raise AssertionError(name)


def _cache(clock=None):
    clock = clock or Clock()
    fake = FakeSupabase(clock)
    client = httpx.Client(transport=httpx.MockTransport(fake))
    return SupabaseAnswerCache(URL, SECRET, clock, client), fake, clock


def _rich_reading():
    r = _reading(RID)
    r.top = SpeciesCandidate(name="Ocimum basilicum", common_name="Basil", confidence=0.8)
    r.weather = WeatherFacts(12.5, 9, 14.0, 3, 4.5, "Sat 25 Oct: 6 to 13 °C, 1 mm", ["x"], [2])
    r.failures = [StageFailure(stage="research", message="timeout")]
    r.checked, r.received, r.season_missing = True, T0.date(), "outside_uk"
    return r


def test_a_reading_is_itself_after_the_trip_through_json():
    r = _rich_reading()
    back = reading_from_json(json.loads(json.dumps(reading_to_json(r))))
    assert back == r
    sparse = _reading("b" * 32)
    assert reading_from_json(json.loads(json.dumps(reading_to_json(sparse)))) == sparse


@respx.mock
def test_a_full_pipeline_reading_survives_the_trip(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    app, *_ = _app(tmp_path, AnswerCache(lambda: T0))
    rid = _upload(TestClient(app))
    entry = app.state.answers.get(rid)
    assert entry.reading is not None and entry.reading.rec.environment is not None
    trip = reading_from_json(json.loads(json.dumps(reading_to_json(entry.reading))))
    assert trip == entry.reading


def test_put_then_get_gives_the_same_entry_with_its_chat():
    cache, fake, clock = _cache()
    r = _rich_reading()
    cache.put(r, r.rec, owner=None, last_decline=4, claim="the-key")
    clock.now = T0 + timedelta(minutes=5)
    assert cache.add_chat(RID, ChatMessage(role="user", content="hi", created_at=clock.now))
    refined = r.rec.model_copy(update={"refined_from": "Water it."})
    cache.set_latest(RID, refined)
    entry = cache.get(RID)
    assert entry.reading == r and entry.latest == refined and entry.at == T0
    assert entry.last_decline == 4 and entry.owner is None and entry.first_headline is None
    assert [(m.role, m.content, m.created_at) for m in entry.chat] == [("user", "hi", clock.now)]
    assert entry.claim == claim_hash("the-key")
    later = _rich_reading()
    later.month = 11
    cache.set_reading(RID, later)
    assert cache.get(RID).reading == later
    assert cache.get("b" * 32) is None


def test_an_answer_older_than_24_hours_is_gone_and_the_purge_deletes_it():
    cache, fake, clock = _cache()
    r = _reading(RID)
    cache.put(r, r.rec)
    clock.now = T0 + timedelta(hours=23, minutes=59)
    assert cache.get(RID) is not None
    clock.now = T0 + KEEP + timedelta(seconds=1)
    assert cache.get(RID) is None and RID in fake.rows  # hidden by the read's filter
    assert [r.method for r in fake.seen].count("DELETE") == 0  # a read never deletes
    assert cache.add_chat(RID, ChatMessage(role="user", content="late")) is False
    assert cache.purge() == 1 and RID not in fake.rows


def test_the_in_memory_cache_still_keeps_an_answer_for_an_hour_only():
    clock = Clock()
    cache = AnswerCache(clock)
    r = _reading(RID)
    cache.put(r, r.rec)
    clock.now = T0 + timedelta(hours=1, seconds=1)
    assert cache.get(RID) is None


def test_get_for_hands_an_answer_only_to_its_owner():
    cache, *_ = _cache()
    r = _reading(RID)
    cache.put(r, r.rec, owner="0d1f3c3e-0000-4000-8000-000000000001")
    assert cache.get_for(RID, "0d1f3c3e-0000-4000-8000-000000000001") is not None
    assert cache.get_for(RID, "0d1f3c3e-0000-4000-8000-000000000002") is None
    assert cache.get_for(RID, None) is None


def test_a_claim_needs_the_right_key_and_sends_only_its_hash():
    cache, fake, _ = _cache()
    r = _reading(RID)
    key = "c0ffee" * 5
    cache.put(r, r.rec, claim=key)
    assert cache.claim(RID, "wrong-key", "u1") is False
    assert cache.claim(RID, key, "u1") is True
    assert cache.claim(RID, key, "u2") is False  # once only
    cache.unclaim(RID, "u1")  # a failed store write is undone
    assert cache.get(RID).owner is None and cache.claim(RID, key, "u2") is True
    assert fake.rows[RID]["claim_hash"] == claim_hash(key)
    for req in fake.seen:
        assert key not in str(req.url) and key.encode() not in req.content


def test_unclaim_leaves_an_answer_made_signed_in_alone():
    cache, fake, _ = _cache()
    r = _reading(RID)
    cache.put(r, r.rec, owner="u1")  # no claim key: never signed out
    cache.unclaim(RID, "u1")
    assert cache.get(RID).owner == "u1"


@pytest.mark.parametrize(
    "down", [503, httpx.ConnectError("down"), httpx.ReadTimeout("slow")], ids=str
)
def test_supabase_down_reads_as_not_there_and_never_raises(caplog, down):
    cache, fake, _ = _cache()
    r = _reading(RID)
    cache.put(r, r.rec, claim="k")  # written while Supabase was up
    fake.down = down
    assert cache.get(RID) is None and cache.get_for(RID, None) is None
    assert cache.claim(RID, "k", "u1") is False
    assert cache.add_chat(RID, ChatMessage(role="user", content="hi")) is False
    cache.unclaim(RID, "u1")
    cache.set_latest(RID, r.rec)
    cache.set_reading(RID, r)
    assert cache.purge() is None
    assert "answer cache: get failed" in caplog.text and SECRET not in caplog.text


def test_an_answer_whose_write_failed_is_kept_in_memory_and_used_from_there(caplog):
    cache, fake, clock = _cache()
    fake.down = httpx.ConnectError("down")
    r = _reading(RID)
    key = "c0ffee" * 5
    cache.put(r, r.rec, claim=key)
    assert "kept in memory instead" in caplog.text
    fake.down = None  # back up: the answer is still only in memory, and served from there
    asked = len(fake.seen)
    entry = cache.get(RID)
    assert entry is not None and entry.reading is r and cache.get_for(RID, None) is entry
    assert cache.add_chat(RID, ChatMessage(role="user", content="hi"))
    refined = r.rec.model_copy(update={"refined_from": "Water it."})
    cache.set_latest(RID, refined)
    cache.set_reading(RID, r)
    assert cache.claim(RID, "wrong", "u1") is False and cache.claim(RID, key, "u1") is True
    cache.unclaim(RID, "u1")
    entry = cache.get(RID)
    assert entry.latest is refined and [m.content for m in entry.chat] == ["hi"]
    assert entry.owner is None and len(fake.seen) == asked  # nothing asked of Supabase
    # a later write under the same id that lands: Supabase's copy wins, memory's goes
    newer = r.rec.model_copy(update={"refined_from": "Feed it."})
    cache.put(r, newer)
    assert RID in fake.rows and cache._memory.get(RID) is None
    asked = len(fake.seen)
    assert cache.get(RID).latest == newer and len(fake.seen) == asked + 1  # from Supabase


def test_memory_keeps_an_unwritten_answer_24_hours_and_no_longer():
    cache, fake, clock = _cache()
    fake.down = httpx.ConnectError("down")
    r = _reading(RID)
    cache.put(r, r.rec)
    clock.now = T0 + KEEP - timedelta(seconds=1)
    assert cache._memory.get(RID) is not None
    clock.now = T0 + KEEP + timedelta(seconds=1)
    assert cache._memory.get(RID) is None


def test_a_row_it_cannot_read_is_not_there():
    cache, fake, _ = _cache()
    r = _reading(RID)
    cache.put(r, r.rec)
    fake.rows[RID]["record"] = {"not": "a record"}
    assert cache.get(RID) is None


def test_the_purge_deletes_only_answers_past_their_24_hours():
    cache, fake, clock = _cache()
    old, new = _reading(RID), _reading("b" * 32)
    cache.put(old, old.rec)
    clock.now = T0 + timedelta(hours=20)
    cache.put(new, new.rec)
    clock.now = T0 + KEEP + timedelta(minutes=1)
    assert cache.purge() == 1 and list(fake.rows) == ["b" * 32]


# --- the app ---------------------------------------------------------------------------

ENV = {
    "HERBTWIN_HOME_LAT": "51.5",
    "HERBTWIN_HOME_LON": "-0.12",
    "HERBTWIN_REMINDER_SECRET": "a-test-secret",
}


def test_the_live_site_keeps_answers_in_supabase_and_local_runs_in_memory():
    live = load_settings(
        {"HERBTWIN_CAPS_ENABLED": "1", "HERBTWIN_SUPABASE_URL": URL,
         "HERBTWIN_SUPABASE_SECRET_KEY": SECRET}
    )  # fmt: skip
    chosen = _answers_from(live, lambda: T0)
    assert isinstance(chosen, SupabaseAnswerCache) and chosen.url == URL
    local = load_settings({"HERBTWIN_SUPABASE_URL": URL, "HERBTWIN_SUPABASE_SECRET_KEY": SECRET})
    assert isinstance(_answers_from(local, lambda: T0), AnswerCache)  # caps off: memory
    no_key = load_settings({"HERBTWIN_CAPS_ENABLED": "1", "HERBTWIN_SUPABASE_URL": URL})
    assert isinstance(_answers_from(no_key, lambda: T0), AnswerCache)


def test_create_app_takes_the_supabase_store_from_settings(monkeypatch):
    from herbtwin.web import app as web_app

    env = {
        "HERBTWIN_CAPS_ENABLED": "1",
        "HERBTWIN_SUPABASE_URL": URL,
        "HERBTWIN_SUPABASE_SECRET_KEY": SECRET,
    }
    monkeypatch.setattr(web_app, "load_settings", lambda: load_settings(env))
    app = create_app(accounts=None, usage=None, mail=None, reminder_admin=None)
    assert isinstance(app.state.answers, SupabaseAnswerCache)


def _app(tmp_path, answers):
    hist, auth = MemoryHistory(), FakeAuth()
    deps = Deps(
        observe_adapter=MockAdapter([json.dumps(OBS)] * 4),
        advise_adapter=MockAdapter([json.dumps(ADV)] * 12),
        settings=load_settings(ENV),
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "p",
        workers=1,
    )
    app = create_app(deps, clock=lambda: T0, accounts=fake_accounts(hist, auth), answers=answers)
    return app, hist, auth


def _upload(c) -> str:
    import re

    page = follow(c, c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}))
    return re.search(r'data-answer="([0-9a-f]{32})"', page.text).group(1)


@respx.mock
def test_an_answer_in_supabase_opens_and_is_kept_on_signing_in(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    cache, fake, _ = _cache(Clock())
    app, hist, auth = _app(tmp_path, cache)
    c = TestClient(app)
    rid = _upload(c)
    assert rid in fake.rows and fake.rows[rid]["reading"] is not None
    assert c.get(f"/answers/{rid}").status_code == 200  # the link opens from Supabase
    key = c.cookies[claims.KEY_COOKIE].rsplit(".", 1)[0]
    c.get(f"/auth/sign-in?next=/answers/{rid}", headers={"sec-fetch-site": "same-origin"})
    c.post(
        "/auth/callback",
        data={"token_hash": auth.issue("u1", "u1@b.co"), "type": "email"},
        follow_redirects=False,
    )
    kept = c.post(f"/answers/{rid}/keep", follow_redirects=False)
    assert kept.headers["location"] == f"/answers/{rid}?kept=1"
    assert hist.answers[rid][0] == "u1" and fake.rows[rid]["owner"] == "u1"
    assert fake.rows[rid]["claim_hash"] == claim_hash(key)
    for req in fake.seen:  # the browser's key never leaves the server
        assert key not in str(req.url) and key.encode() not in req.content


@respx.mock
def test_an_upload_with_supabase_down_still_shows_its_answer(tmp_path):
    # the read was paid for (the caps fail open): the answer shows from memory, not "expired"
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    cache, fake, _ = _cache(Clock())
    fake.down = httpx.ConnectError("down")
    app, *_ = _app(tmp_path, cache)
    c = TestClient(app)
    rid = _upload(c)
    page = c.get(f"/answers/{rid}")
    assert page.status_code == 200 and f'data-answer="{rid}"' in page.text
    assert fake.rows == {}


@respx.mock
def test_an_answer_page_with_supabase_down_says_expired_not_500(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    cache, fake, _ = _cache(Clock())
    app, *_ = _app(tmp_path, cache)
    c = TestClient(app, raise_server_exceptions=False)
    rid = _upload(c)
    fake.down = httpx.ConnectError("down")
    r = c.get(f"/answers/{rid}")
    assert r.status_code < 500


@respx.mock
def test_the_claim_cookie_lasts_as_long_as_the_answer(tmp_path):
    # kept 24 hours, the answer can be kept on signing in for all of them
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    app, *_ = _app(tmp_path, AnswerCache(lambda: T0))
    r = TestClient(app).post(
        "/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")}, follow_redirects=False
    )
    [cookie] = [v for v in r.headers.get_list("set-cookie") if v.startswith(claims.KEY_COOKIE)]
    assert "Max-Age=86400" in cookie
