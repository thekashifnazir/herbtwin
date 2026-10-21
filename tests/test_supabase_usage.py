"""The site usage migration on the local stack (`supabase start`, then `supabase db reset`
or `supabase migration up`): the increment function caps a visitor, and only the server's
secret key may call it."""

import uuid
from datetime import date

import httpx
import pytest

from tests.supabase_local import local_env, signed_up

pytestmark = pytest.mark.supabase


def _call(env: dict[str, str], key: str, visitor: str) -> httpx.Response:
    return httpx.post(
        f"{env['API_URL']}/rest/v1/rpc/count_photo_read",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        json={
            "p_day": date(2026, 10, 12).isoformat(),
            "p_visitor": visitor,
            "p_cost": 0.000001,
            # the local database keeps earlier runs' counts: only the visitor cap may bite
            "p_day_cap": 1_000_000_000,
            "p_visitor_cap": 2,
            "p_budget": 1_000_000_000,
            "p_judge": False,
        },
        timeout=15,
    )


def test_count_photo_read_refuses_the_third_read_for_a_cap_of_two():
    env = local_env()
    secret = env.get("SECRET_KEY") or env["SERVICE_ROLE_KEY"]
    visitor = uuid.uuid4().hex[:32]
    got = [_call(env, secret, visitor) for _ in range(3)]
    assert [r.status_code for r in got] == [200, 200, 200], got[-1].text
    assert [r.json()["allowed"] for r in got] == [True, True, False]
    assert got[2].json()["reason"] == "visitor"


def test_the_publishable_key_cannot_call_it():
    env = local_env()
    anon = env.get("PUBLISHABLE_KEY") or env["ANON_KEY"]
    r = _call(env, anon, uuid.uuid4().hex[:32])
    assert r.status_code in (401, 403, 404), r.text


def test_the_publishable_key_cannot_read_the_counters():
    env = local_env()
    anon = env.get("PUBLISHABLE_KEY") or env["ANON_KEY"]
    r = httpx.get(
        f"{env['API_URL']}/rest/v1/site_budget",
        headers={"apikey": anon, "Authorization": f"Bearer {anon}"},
        timeout=15,
    )
    assert r.status_code in (401, 403, 404), r.text


def test_a_signed_in_person_can_neither_call_it_nor_read_the_counters():
    env = local_env()
    token, _ = signed_up(env)
    anon = env.get("PUBLISHABLE_KEY") or env["ANON_KEY"]
    headers = {"apikey": anon, "Authorization": f"Bearer {token}"}
    r = httpx.post(
        f"{env['API_URL']}/rest/v1/rpc/count_photo_read",
        headers=headers,
        json={
            "p_day": date(2026, 10, 12).isoformat(),
            "p_visitor": uuid.uuid4().hex[:32],
            "p_cost": 0,
            "p_day_cap": 1,
            "p_visitor_cap": 1,
            "p_budget": 1,
            "p_judge": True,
        },
        timeout=15,
    )
    assert r.status_code in (401, 403, 404), r.text
    for table in ("site_budget", "site_usage_days", "site_usage_visitors"):
        got = httpx.get(f"{env['API_URL']}/rest/v1/{table}", headers=headers, timeout=15)
        assert got.status_code in (401, 403, 404), (table, got.text)


def _rpc(env: dict[str, str], name: str, body: dict, key: str, token: str | None = None):
    return httpx.post(
        f"{env['API_URL']}/rest/v1/rpc/{name}",
        headers={"apikey": key, "Authorization": f"Bearer {token or key}"},
        json=body,
        timeout=15,
    )


def test_charge_spend_refuses_once_spent_and_lets_a_judge_through():
    env = local_env()
    secret = env.get("SECRET_KEY") or env["SERVICE_ROLE_KEY"]
    big = {"p_cost": 0.000001, "p_budget": 1_000_000_000, "p_judge": False}
    ok = _rpc(env, "charge_spend", big, secret)
    assert ok.status_code == 200, ok.text
    assert ok.json()["allowed"] is True and ok.json()["reason"] == "ok"
    # a zero budget is always spent: refused, unless a judge (cost 0 keeps the total as is)
    spent = _rpc(env, "charge_spend", {"p_cost": 0, "p_budget": 0, "p_judge": False}, secret)
    assert spent.json()["allowed"] is False and spent.json()["reason"] == "budget"
    judge = _rpc(env, "charge_spend", {"p_cost": 0, "p_budget": 0, "p_judge": True}, secret)
    assert judge.json()["allowed"] is True


def test_usage_ping_answers_true_for_the_secret_key_only():
    env = local_env()
    secret = env.get("SECRET_KEY") or env["SERVICE_ROLE_KEY"]
    r = _rpc(env, "usage_ping", {}, secret)
    assert r.status_code == 200 and r.json() is True, r.text


def test_no_person_can_charge_or_ping():
    env = local_env()
    anon = env.get("PUBLISHABLE_KEY") or env["ANON_KEY"]
    token, _ = signed_up(env)
    body = {"p_cost": 0, "p_budget": 1, "p_judge": True}
    for who in (None, token):
        assert _rpc(env, "charge_spend", body, anon, who).status_code in (401, 403, 404)
        assert _rpc(env, "usage_ping", {}, anon, who).status_code in (401, 403, 404)
