"""Refines and chat against the live budget, the per-answer refine limit, and the health
check's view of the usage store (spec D60; review of D1b)."""

import json
import logging

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from herbtwin.adapters.mock import MockAdapter
from herbtwin.config import load_settings
from herbtwin.pipeline import Deps
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.tracing import TraceStore
from herbtwin.usage import MemoryUsage, UsageError
from herbtwin.web.app import OUT_OF_BUDGET, REFINE_LIMIT, REFINE_LIMIT_TEXT, create_app
from herbtwin.web.judge import COOKIE, judge_token
from tests.test_web import ADV, HOLD, JPEG, OBS, OCT_4, SAMPLE

CODE = "judge-code"
WET = {"soil_feel": "wet"}
# a photo read uses the whole budget: whatever comes next finds it spent
SPENT = {"HERBTWIN_LIVE_BUDGET_USD": "0.005", "HERBTWIN_READ_COST_USD": "0.005"}


@pytest.fixture(autouse=True)
def _weather():
    with respx.mock:
        respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
        yield


def _client(
    tmp_path, env=None, usage=None, mail=None, advice=3, accounts=None, observe=OBS
) -> TestClient:
    deps = Deps(
        observe_adapter=MockAdapter([json.dumps(observe)]),
        advise_adapter=MockAdapter([json.dumps(ADV)] * 3 + [HOLD] * advice),
        settings=load_settings({"HERBTWIN_JUDGE_CODE": CODE, **(env or {})}),
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "p",
        workers=1,
    )
    app = create_app(deps, clock=lambda: OCT_4, accounts=accounts, usage=usage, mail=mail)
    return TestClient(app)


def _first(c: TestClient) -> str:
    r = c.post("/api/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")})
    assert r.status_code == 200, r.text
    return r.json()["record_id"]


def test_sixth_refine_of_an_answer_is_refused(tmp_path):
    c = _client(tmp_path, advice=3 * REFINE_LIMIT)
    rid = _first(c)
    for _ in range(REFINE_LIMIT):
        assert c.post(f"/api/answers/{rid}/refine", json=WET).status_code == 200
    r = c.post(f"/api/answers/{rid}/refine", json=WET)
    assert r.status_code == 429 and r.json() == {"detail": REFINE_LIMIT_TEXT}
    page = c.post(f"/answers/{rid}/refine", data=WET)
    assert page.status_code == 429 and "the most it can be" in page.text


def test_refine_is_charged_to_the_budget(tmp_path):
    store = MemoryUsage()
    c = _client(tmp_path, usage=store)
    rid = _first(c)
    assert c.post(f"/api/answers/{rid}/refine", json=WET).status_code == 200
    assert float(store.spent) == pytest.approx(0.005 + 0.003)


def test_refine_refused_once_the_budget_is_spent(tmp_path):
    c = _client(tmp_path, SPENT, usage=MemoryUsage(), mail=lambda s, t: None)
    rid = _first(c)
    r = c.post(f"/api/answers/{rid}/refine", json=WET)
    assert r.status_code == 429 and r.json() == {"detail": OUT_OF_BUDGET}
    page = c.post(f"/answers/{rid}/refine", data=WET)
    assert page.status_code == 429 and "paused for now" in page.text


def test_a_judge_can_refine_past_the_budget(tmp_path):
    store = MemoryUsage()
    c = _client(tmp_path, SPENT, usage=store, mail=lambda s, t: None)
    rid = _first(c)
    c.cookies.set(COOKIE, judge_token(CODE))
    assert c.post(f"/api/answers/{rid}/refine", json=WET).status_code == 200
    assert float(store.spent) == pytest.approx(0.008)  # still counted


def test_an_empty_refine_costs_nothing(tmp_path):
    store = MemoryUsage()
    c = _client(tmp_path, usage=store)
    rid = _first(c)
    assert c.post(f"/api/answers/{rid}/refine", json={}).status_code == 400
    assert float(store.spent) == pytest.approx(0.005)


def test_refine_crossing_eighty_percent_sends_the_warning(tmp_path):
    sent: list[str] = []
    env = {"HERBTWIN_LIVE_BUDGET_USD": "0.01", "HERBTWIN_READ_COST_USD": "0.005"}
    store = MemoryUsage()
    c = _client(tmp_path, env, usage=store, mail=lambda s, t: sent.append(s))
    rid = _first(c)
    assert sent == []
    c.post(f"/api/answers/{rid}/refine", json=WET)  # 0.008 of 0.01
    assert len(sent) == 1 and store.warned


def test_chat_is_charged_and_refused_once_spent(tmp_path):
    store = MemoryUsage()
    env = {"HERBTWIN_LIVE_BUDGET_USD": "0.0055", "HERBTWIN_READ_COST_USD": "0.005"}
    deps_advice = 1  # one chat reply
    c = _client(tmp_path, env, usage=store, mail=lambda s, t: None, advice=deps_advice)
    rid = _first(c)
    assert c.post(f"/api/answers/{rid}/chat", json={"message": "is it ok?"}).status_code == 200
    assert float(store.spent) == pytest.approx(0.006)
    r = c.post(f"/api/answers/{rid}/chat", json={"message": "and now?"})
    assert r.status_code == 429 and r.json() == {"detail": OUT_OF_BUDGET}


class DownUsage(MemoryUsage):
    def charge(self, cost, limits, *, judge):
        raise UsageError("charge_spend: HTTP 500")

    def ping(self):
        raise UsageError("usage_ping: HTTP 500")


def test_store_down_lets_refine_and_chat_through_and_logs(tmp_path, caplog):
    c = _client(tmp_path, usage=DownUsage(), advice=4)
    rid = _first(c)
    with caplog.at_level(logging.ERROR):
        assert c.post(f"/api/answers/{rid}/refine", json=WET).status_code == 200
        assert c.post(f"/api/answers/{rid}/chat", json={"message": "ok?"}).status_code == 200
    assert "usage store unavailable" in caplog.text


def test_healthz_says_usage_off_without_a_store(tmp_path):
    assert _client(tmp_path).get("/healthz").json() == {"ok": True, "usage": "off"}


def test_healthz_says_usage_ok(tmp_path):
    r = _client(tmp_path, usage=MemoryUsage()).get("/healthz")
    assert r.json() == {"ok": True, "usage": "ok"}


def test_healthz_says_usage_down(tmp_path, caplog):
    with caplog.at_level(logging.ERROR):
        r = _client(tmp_path, usage=DownUsage()).get("/healthz")
    assert r.status_code == 200 and r.json() == {"ok": True, "usage": "down"}
    assert "usage store" in caplog.text


# --- only a call that reaches the model is charged (no counted spend from junk requests) ---


def test_chat_to_an_unknown_answer_charges_nothing(tmp_path):
    store = MemoryUsage()
    c = _client(tmp_path, usage=store)
    r = c.post("/api/answers/" + "f" * 32 + "/chat", json={"message": "hi"})
    assert r.status_code == 404 and store.spent == 0


def test_chat_past_its_limit_charges_nothing(tmp_path):
    from herbtwin.chat import LIMIT, MAX_MESSAGES

    store = MemoryUsage()
    c = _client(tmp_path, usage=store, advice=MAX_MESSAGES)
    rid = _first(c)
    for _ in range(MAX_MESSAGES):
        assert c.post(f"/api/answers/{rid}/chat", json={"message": "ok?"}).status_code == 200
    before = store.spent
    r = c.post(f"/api/answers/{rid}/chat", json={"message": "one more"})
    assert r.status_code == 429 and r.json()["detail"] == LIMIT
    assert store.spent == before


def test_an_expired_refine_charges_nothing(tmp_path):
    store = MemoryUsage()
    c = _client(tmp_path, usage=store)
    assert c.post("/api/answers/" + "f" * 32 + "/refine", json=WET).status_code == 404
    assert c.post("/answers/" + "f" * 32 + "/refine", data=WET).status_code == 404
    assert store.spent == 0


def test_a_refine_past_its_limit_charges_nothing(tmp_path):
    store = MemoryUsage()
    c = _client(tmp_path, usage=store, advice=3 * REFINE_LIMIT)
    rid = _first(c)
    for _ in range(REFINE_LIMIT):
        c.post(f"/api/answers/{rid}/refine", json=WET)
    before = store.spent
    assert c.post(f"/api/answers/{rid}/refine", json=WET).status_code == 429
    assert store.spent == before


def test_a_budget_refused_refine_keeps_its_slot(tmp_path):
    c = _client(tmp_path, SPENT, usage=MemoryUsage(), mail=lambda s, t: None)
    rid = _first(c)
    for _ in range(REFINE_LIMIT + 1):
        r = c.post(f"/api/answers/{rid}/refine", json=WET)
        assert r.json() == {"detail": OUT_OF_BUDGET}
    c.cookies.set(COOKIE, judge_token(CODE))  # past the budget now: the slots are all there
    assert c.post(f"/api/answers/{rid}/refine", json=WET).status_code == 200


# --- signed in: refine_stored charges and limits too, from the cache or the stored row ---


def _signed_in(tmp_path, usage, advice):
    from herbtwin.history import MemoryHistory
    from tests.fakes import FakeAuth, fake_accounts, follow
    from tests.test_web_history import SAGE

    hist, auth = MemoryHistory(), FakeAuth()
    c = _client(
        tmp_path, usage=usage, advice=advice, accounts=fake_accounts(hist, auth), observe=SAGE
    )
    c.post(
        "/auth/callback",
        data={"token_hash": auth.issue("u1", "a@b.co"), "type": "email"},
        follow_redirects=False,
    )
    r = c.post("/analyse", files={"photo": ("s.jpg", JPEG, "image/jpeg")}, data={"place": ""})
    assert follow(c, r).status_code == 200
    store = hist.for_user("u1")
    [plant] = store.list_plants()
    [stored] = store.answers_for(plant.id)
    return c, stored.id


def test_a_signed_in_refine_is_charged(tmp_path):
    usage = MemoryUsage()
    c, rid = _signed_in(tmp_path, usage, advice=3)
    assert c.post(f"/answers/{rid}/refine", data=WET).status_code == 200
    assert float(usage.spent) == pytest.approx(0.005 + 0.003)


def test_a_signed_in_sixth_refine_is_refused(tmp_path):
    usage = MemoryUsage()
    c, rid = _signed_in(tmp_path, usage, advice=3 * REFINE_LIMIT)
    for _ in range(REFINE_LIMIT):
        assert c.post(f"/answers/{rid}/refine", data=WET).status_code == 200
    before = usage.spent
    r = c.post(f"/answers/{rid}/refine", data=WET)
    assert r.status_code == 429 and "the most it can be" in r.text
    assert usage.spent == before


def test_a_refine_of_a_stored_answer_past_the_hour_is_charged_and_limited(tmp_path):
    usage = MemoryUsage()
    c, rid = _signed_in(tmp_path, usage, advice=3 * REFINE_LIMIT)
    c.app.state.answers._entries.clear()  # the hour is up: only the stored row is left
    assert c.post(f"/answers/{rid}/refine", data=WET).status_code == 200
    assert float(usage.spent) == pytest.approx(0.008)
    for _ in range(REFINE_LIMIT - 1):
        c.app.state.answers._entries.clear()
        assert c.post(f"/answers/{rid}/refine", data=WET).status_code == 200
    c.app.state.answers._entries.clear()
    assert c.post(f"/answers/{rid}/refine", data=WET).status_code == 429


# --- the refine slot is taken atomically, and given back when the budget refuses ---


def test_refine_counts_never_go_past_the_limit():
    from herbtwin.web.app import RefineCounts

    counts = RefineCounts(limit=2)
    assert [counts.take("a") for _ in range(3)] == [True, True, False]


def test_refine_counts_give_back_a_slot():
    from herbtwin.web.app import RefineCounts

    counts = RefineCounts(limit=1)
    assert counts.take("a")
    counts.give_back("a")
    assert counts.take("a") and not counts.take("a")
    counts.give_back("never-taken")  # harmless
    assert counts.take("never-taken")
