"""Caps and the live budget (spec D59, D60): the in-memory store, which is also the reference
for the Postgres function, and the Supabase client's request shape."""

import json
from datetime import UTC, date, datetime

import httpx
import pytest
import respx

from herbtwin.config import load_settings
from herbtwin.usage import (
    Limits,
    MemoryUsage,
    SupabaseUsage,
    UsageError,
    Verdict,
    uk_day,
    visitor_key,
)

DAY = date(2026, 10, 12)
LIMITS = Limits()


def _reads(store, n, visitor="a", limits=LIMITS, judge=False, day=DAY):
    return [store.count_read(day, visitor, limits, judge=judge) for _ in range(n)]


def test_tenth_read_from_a_visitor_allowed_eleventh_refused():
    store = MemoryUsage()
    got = _reads(store, 11)
    assert all(v.allowed for v in got[:10])
    assert got[10] == Verdict(False, "visitor", pytest.approx(0.05), False)


def test_another_visitor_still_gets_in():
    store = MemoryUsage()
    _reads(store, 11, "a")
    assert store.count_read(DAY, "b", LIMITS, judge=False).allowed


def test_visitor_cap_resets_the_next_day():
    store = MemoryUsage()
    _reads(store, 10, "a")
    assert store.count_read(date(2026, 10, 13), "a", LIMITS, judge=False).allowed


def test_day_cap_refuses_the_fourth_read_site_wide():
    store = MemoryUsage()
    limits = Limits(day_reads=3)
    got = [store.count_read(DAY, v, limits, judge=False) for v in "abcd"]
    assert [v.allowed for v in got] == [True, True, True, False]
    assert got[3].reason == "day"


def test_budget_stops_reads_once_spent():
    store = MemoryUsage()
    limits = Limits(budget_usd=0.02, read_cost_usd=0.005)
    got = [store.count_read(DAY, v, limits, judge=False) for v in "abcde"]
    assert all(v.allowed for v in got[:4])
    assert got[3].spent_usd == 0.02
    assert not got[4].allowed and got[4].reason == "budget"


def test_budget_wins_over_the_other_caps():
    store = MemoryUsage()
    limits = Limits(day_reads=1, visitor_reads=1, budget_usd=0.005)
    store.count_read(DAY, "a", limits, judge=False)
    assert store.count_read(DAY, "a", limits, judge=False).reason == "budget"


def test_warn_from_eighty_percent_until_marked():
    store = MemoryUsage()
    limits = Limits(budget_usd=0.05, read_cost_usd=0.01)
    got = [store.count_read(DAY, v, limits, judge=False) for v in "abc"]
    assert [v.warn for v in got] == [False, False, False]
    assert store.count_read(DAY, "d", limits, judge=False).warn  # 0.04 = 80%
    assert store.count_read(DAY, "e", limits, judge=False).warn  # not marked yet: still true
    store.mark_warned()
    assert not store.count_read(DAY, "f", limits, judge=True).warn


def test_judge_passes_every_cap_and_still_adds_to_the_spend():
    store = MemoryUsage()
    limits = Limits(day_reads=1, visitor_reads=1, budget_usd=0.01, read_cost_usd=0.005)
    got = _reads(store, 5, limits=limits, judge=True)
    assert all(v.allowed and v.reason == "ok" for v in got)
    assert got[-1].spent_usd == pytest.approx(0.025)
    assert store.count_read(DAY, "b", limits, judge=False).reason == "budget"


def test_uk_day_follows_british_summer_time():
    assert uk_day(datetime(2026, 7, 1, 23, 30, tzinfo=UTC)) == date(2026, 7, 2)
    assert uk_day(datetime(2026, 12, 1, 23, 30, tzinfo=UTC)) == date(2026, 12, 1)


def test_visitor_key_is_a_stable_keyed_hash():
    k = visitor_key("203.0.113.7", "s3")
    assert k == visitor_key("203.0.113.7", "s3")
    assert len(k) == 32 and all(c in "0123456789abcdef" for c in k)
    assert "203.0.113.7" not in k and "203" not in k
    assert k != visitor_key("203.0.113.7", "s4")
    assert k != visitor_key("203.0.113.8", "s3")


def test_limits_from_settings():
    s = load_settings(
        {
            "HERBTWIN_DAILY_READS": "50",
            "HERBTWIN_VISITOR_READS": "3",
            "HERBTWIN_LIVE_BUDGET_USD": "7.5",
            "HERBTWIN_READ_COST_USD": "0.01",
            "HERBTWIN_CAPS_ENABLED": "1",
        }
    )
    assert s.limits == Limits(50, 3, 7.5, 0.01) and s.caps_enabled


def test_limits_default():
    s = load_settings({})
    assert s.limits == Limits(200, 10, 20.0, 0.005) and not s.caps_enabled


@pytest.mark.parametrize(
    ("key", "raw"),
    [
        ("HERBTWIN_DAILY_READS", "0"),
        ("HERBTWIN_DAILY_READS", "2.5"),
        ("HERBTWIN_VISITOR_READS", "-1"),
        ("HERBTWIN_LIVE_BUDGET_USD", "nan"),
        ("HERBTWIN_READ_COST_USD", "free"),
    ],
)
def test_limits_must_be_positive_numbers(key, raw):
    with pytest.raises(ValueError, match=key):
        load_settings({key: raw})


URL = "https://proj.supabase.co"
RPC = f"{URL}/rest/v1/rpc/count_photo_read"


@respx.mock
def test_supabase_count_read_request_and_verdict():
    route = respx.post(RPC).mock(
        return_value=httpx.Response(
            200, json={"allowed": True, "reason": "ok", "spent": 16.005, "warn": True}
        )
    )
    v = SupabaseUsage(URL, "sb_secret_x").count_read(DAY, "k1", LIMITS, judge=False)
    assert v == Verdict(True, "ok", 16.005, True)
    req = route.calls.last.request
    assert req.headers["apikey"] == "sb_secret_x"
    assert req.headers["authorization"] == "Bearer sb_secret_x"
    assert json.loads(req.content) == {
        "p_day": "2026-10-12",
        "p_visitor": "k1",
        "p_cost": 0.005,
        "p_day_cap": 200,
        "p_visitor_cap": 10,
        "p_budget": 20.0,
        "p_judge": False,
    }


@respx.mock
def test_supabase_refusal_maps_to_verdict():
    respx.post(RPC).mock(
        return_value=httpx.Response(
            200, json={"allowed": False, "reason": "visitor", "spent": 1, "warn": False}
        )
    )
    v = SupabaseUsage(URL, "k").count_read(DAY, "k1", LIMITS, judge=False)
    assert v == Verdict(False, "visitor", 1.0, False)


@respx.mock
def test_supabase_error_raises_usage_error():
    respx.post(RPC).mock(return_value=httpx.Response(500, json={"message": "boom"}))
    with pytest.raises(UsageError):
        SupabaseUsage(URL, "k").count_read(DAY, "k1", LIMITS, judge=False)


@respx.mock
def test_supabase_transport_error_raises_usage_error():
    respx.post(RPC).mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(UsageError):
        SupabaseUsage(URL, "k").count_read(DAY, "k1", LIMITS, judge=False)


@respx.mock
def test_supabase_odd_reply_raises_usage_error():
    respx.post(RPC).mock(return_value=httpx.Response(200, json={"allowed": "maybe"}))
    with pytest.raises(UsageError):
        SupabaseUsage(URL, "k").count_read(DAY, "k1", LIMITS, judge=False)


@respx.mock
def test_supabase_mark_warned():
    route = respx.post(f"{URL}/rest/v1/rpc/mark_budget_warned").mock(
        return_value=httpx.Response(204)
    )
    SupabaseUsage(URL, "k").mark_warned()
    assert route.called and route.calls.last.request.headers["apikey"] == "k"


@respx.mock
def test_supabase_mark_warned_error_raises_usage_error():
    respx.post(f"{URL}/rest/v1/rpc/mark_budget_warned").mock(return_value=httpx.Response(401))
    with pytest.raises(UsageError):
        SupabaseUsage(URL, "k").mark_warned()


def test_ipv6_visitors_are_keyed_on_their_64_prefix():
    a = visitor_key("2001:db8:1:2:aaaa::1", "s3")
    assert a == visitor_key("2001:db8:1:2:bbbb:cccc:dddd:eeee", "s3")  # same /64
    assert a == visitor_key("2001:DB8:1:2::9", "s3")  # any spelling of it
    assert a != visitor_key("2001:db8:1:3::1", "s3")  # the next /64


def test_ipv4_visitors_keep_their_whole_address():
    assert visitor_key("203.0.113.7", "s3") != visitor_key("203.0.113.8", "s3")
    assert visitor_key("::ffff:203.0.113.7", "s3") == visitor_key("203.0.113.7", "s3")
    assert visitor_key("not an ip", "s3") == visitor_key("not an ip", "s3")


# --- refine and chat spend (charge) and the health check (ping) ---


def test_charge_adds_to_the_spend_and_stops_at_the_budget():
    store = MemoryUsage()
    limits = Limits(budget_usd=0.01)
    assert store.charge(0.006, limits, judge=False) == Verdict(True, "ok", 0.006, False)
    second = store.charge(0.006, limits, judge=False)
    assert second.allowed and second.spent_usd == 0.012 and second.warn
    assert store.charge(0.001, limits, judge=False) == Verdict(False, "budget", 0.012, False)
    assert store.days == {}  # not a photo read


def test_charge_lets_a_judge_past_the_budget_and_still_counts():
    store = MemoryUsage()
    limits = Limits(budget_usd=0.001)
    store.charge(0.001, limits, judge=False)
    assert store.charge(0.003, limits, judge=True).spent_usd == 0.004


def test_charge_and_reads_share_one_budget():
    store = MemoryUsage()
    limits = Limits(budget_usd=0.01, read_cost_usd=0.005)
    store.charge(0.01, limits, judge=False)
    assert store.count_read(DAY, "a", limits, judge=False).reason == "budget"


def test_memory_ping_is_fine():
    MemoryUsage().ping()


def test_refine_and_chat_costs_from_settings():
    s = load_settings({"HERBTWIN_REFINE_COST_USD": "0.004", "HERBTWIN_CHAT_COST_USD": "0.002"})
    assert (s.limits.refine_cost_usd, s.limits.chat_cost_usd) == (0.004, 0.002)
    d = load_settings({}).limits
    assert (d.refine_cost_usd, d.chat_cost_usd) == (0.003, 0.001)
    with pytest.raises(ValueError, match="HERBTWIN_CHAT_COST_USD"):
        load_settings({"HERBTWIN_CHAT_COST_USD": "-1"})


@respx.mock
def test_supabase_charge_request_and_verdict():
    route = respx.post(f"{URL}/rest/v1/rpc/charge_spend").mock(
        return_value=httpx.Response(
            200, json={"allowed": False, "reason": "budget", "spent": 20, "warn": False}
        )
    )
    v = SupabaseUsage(URL, "k").charge(0.003, LIMITS, judge=False)
    assert v == Verdict(False, "budget", 20.0, False)
    assert json.loads(route.calls.last.request.content) == {
        "p_cost": 0.003,
        "p_budget": 20.0,
        "p_judge": False,
    }
    assert route.calls.last.request.headers["authorization"] == "Bearer k"


@respx.mock
def test_supabase_charge_error_raises_usage_error():
    respx.post(f"{URL}/rest/v1/rpc/charge_spend").mock(return_value=httpx.Response(503))
    with pytest.raises(UsageError):
        SupabaseUsage(URL, "k").charge(0.003, LIMITS, judge=True)


@respx.mock
def test_supabase_ping_ok():
    route = respx.post(f"{URL}/rest/v1/rpc/usage_ping").mock(
        return_value=httpx.Response(200, json=True)
    )
    SupabaseUsage(URL, "k").ping()
    assert route.called


@pytest.mark.parametrize(
    "reply", [httpx.Response(200, json=False), httpx.Response(404), httpx.Response(200)]
)
@respx.mock
def test_supabase_ping_failure_raises_usage_error(reply):
    respx.post(f"{URL}/rest/v1/rpc/usage_ping").mock(return_value=reply)
    with pytest.raises(UsageError):
        SupabaseUsage(URL, "k").ping()
