"""Caps and the live budget (spec D59, D60): photo reads a day site-wide and per visitor,
and a running estimate of the live site's model spend.

Rules, the same in both stores: a judge is always allowed. Anyone else is refused with
"budget" once the spend has reached the budget, else "day" once today's reads reached the
day cap, else "visitor" once this visitor's reads today reached the visitor cap. An
allowed read adds one to today, one to the visitor and the per-read cost to the spend;
`warn` is true while the spend is at or past 80% of the budget and no warning has been
marked sent. Refines and chat messages are charged to the same budget (`charge`): the
budget rule only, judges exempt. MemoryUsage is the reference for the Postgres functions
count_photo_read and charge_spend (supabase/migrations/20261012120000_site_usage.sql)."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import threading
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Protocol, get_args
from zoneinfo import ZoneInfo

import httpx

Reason = Literal["ok", "visitor", "day", "budget"]
UK = ZoneInfo("Europe/London")
WARN_AT = Decimal("0.8")


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    reason: Reason
    spent_usd: float
    warn: bool


@dataclass(frozen=True)
class Limits:
    day_reads: int = 200
    visitor_reads: int = 10
    budget_usd: float = 20.0
    read_cost_usd: float = 0.005
    refine_cost_usd: float = 0.003  # a refine: the advisor three times on the same reading
    chat_cost_usd: float = 0.001  # one chat message
    voice_cost_usd: float = 0.05  # the plant reading its answer aloud: ~300 ElevenLabs credits


class UsageError(Exception):
    """The usage store could not answer; the caller allows the read and logs."""


class UsageStore(Protocol):
    def count_read(self, day: date, visitor: str, limits: Limits, *, judge: bool) -> Verdict: ...

    def charge(self, cost: float, limits: Limits, *, judge: bool) -> Verdict:
        """Model spend that is not a photo read (refine, chat): the budget rule only."""
        ...

    def mark_warned(self) -> None: ...

    def ping(self) -> None:
        """Raise UsageError unless the store answers (the health check; reads nothing)."""
        ...


def uk_day(now: datetime) -> date:
    """The UK calendar day of an aware time: caps reset at UK midnight, summer time included."""
    return now.astimezone(UK).date()


def _subject(ip: str) -> str:
    """What one visitor is: an IPv4 address, or an IPv6 /64 (one home or phone is handed a
    whole /64, so counting single v6 addresses would let one visitor be thousands)."""
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        return ip
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped is not None:
            return str(addr.ipv4_mapped)
        return str(ipaddress.ip_network(f"{addr}/64", strict=False))
    return str(addr)


def visitor_key(ip: str, secret: str | None) -> str:
    """The visitor as stored: an HMAC of the IP (an IPv6 /64) keyed by the edge secret,
    never the IP."""
    subject = _subject(ip).encode()
    return hmac.new((secret or "").encode(), subject, hashlib.sha256).hexdigest()[:32]


def _dec(x: float) -> Decimal:
    return Decimal(str(x))  # exact like Postgres numeric: 4 x 0.005 is 0.02, not 0.0199...


class MemoryUsage:
    """The rules in Python, for tests and as the reference for the SQL."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.days: dict[date, int] = {}
        self.visitors: dict[tuple[date, str], int] = {}
        self.spent = Decimal(0)
        self.warned = False

    def count_read(self, day: date, visitor: str, limits: Limits, *, judge: bool) -> Verdict:
        with self._lock:
            d, v = self.days.get(day, 0), self.visitors.get((day, visitor), 0)
            budget = _dec(limits.budget_usd)
            if not judge:
                refused: Reason | None = (
                    "budget"
                    if self.spent >= budget
                    else "day"
                    if d >= limits.day_reads
                    else "visitor"
                    if v >= limits.visitor_reads
                    else None
                )
                if refused:
                    return Verdict(False, refused, float(self.spent), False)
            self.days[day], self.visitors[(day, visitor)] = d + 1, v + 1
            return self._add(limits.read_cost_usd, budget)

    def charge(self, cost: float, limits: Limits, *, judge: bool) -> Verdict:
        with self._lock:
            budget = _dec(limits.budget_usd)
            if not judge and self.spent >= budget:
                return Verdict(False, "budget", float(self.spent), False)
            return self._add(cost, budget)

    def _add(self, cost: float, budget: Decimal) -> Verdict:
        self.spent += _dec(cost)
        warn = not self.warned and self.spent >= WARN_AT * budget
        return Verdict(True, "ok", float(self.spent), warn)

    def mark_warned(self) -> None:
        with self._lock:
            self.warned = True

    def ping(self) -> None:
        return None


class SupabaseUsage:
    """The counters on Supabase, through count_photo_read with the server's secret key."""

    def __init__(self, url: str, secret_key: str, client: httpx.Client | None = None) -> None:
        self.url = url.rstrip("/")
        self.headers = {"apikey": secret_key, "Authorization": f"Bearer {secret_key}"}
        self.client = client or httpx.Client(timeout=10)

    def _rpc(self, name: str, body: dict) -> httpx.Response:
        try:
            r = self.client.post(f"{self.url}/rest/v1/rpc/{name}", headers=self.headers, json=body)
        except httpx.HTTPError as e:
            raise UsageError(f"{name}: {type(e).__name__}") from e
        if not r.is_success:
            raise UsageError(f"{name}: HTTP {r.status_code}")
        return r

    def count_read(self, day: date, visitor: str, limits: Limits, *, judge: bool) -> Verdict:
        r = self._rpc(
            "count_photo_read",
            {
                "p_day": day.isoformat(),
                "p_visitor": visitor,
                "p_cost": limits.read_cost_usd,
                "p_day_cap": limits.day_reads,
                "p_visitor_cap": limits.visitor_reads,
                "p_budget": limits.budget_usd,
                "p_judge": judge,
            },
        )
        return _verdict("count_photo_read", r)

    def charge(self, cost: float, limits: Limits, *, judge: bool) -> Verdict:
        r = self._rpc(
            "charge_spend", {"p_cost": cost, "p_budget": limits.budget_usd, "p_judge": judge}
        )
        return _verdict("charge_spend", r)

    def mark_warned(self) -> None:
        self._rpc("mark_budget_warned", {})

    def ping(self) -> None:
        r = self._rpc("usage_ping", {})
        try:
            ok = r.json()
        except ValueError:
            ok = None
        if ok is not True:
            raise UsageError("usage_ping: unexpected reply")


def _verdict(name: str, r: httpx.Response) -> Verdict:
    try:
        d = r.json()
        allowed, reason, warn = d["allowed"], d["reason"], d["warn"]
        spent = float(d["spent"])
    except (ValueError, KeyError, TypeError) as e:
        raise UsageError(f"{name}: unexpected reply") from e
    if not isinstance(allowed, bool) or not isinstance(warn, bool):
        raise UsageError(f"{name}: unexpected reply")
    if reason not in get_args(Reason):
        raise UsageError(f"{name}: unexpected reply")
    return Verdict(allowed, reason, spent, warn)
