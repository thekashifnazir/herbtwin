"""Answers kept for a while after they are made, so the link works, refine and chat work
without an account, and a signed-out answer can be kept on signing in (spec section 4).

Two stores with the same methods and rules: `SupabaseAnswerCache` on the live site keeps
each answer for 24 hours in Supabase (25 Oct, Kash), so a deploy or a restart no longer
wipes every answer link (supabase/migrations/20261025120000_answer_cache.sql);
`AnswerCache` keeps them in server memory for an hour, for tests and local runs. Neither
keeps a photo. The browser's claim key is kept only as its SHA-256 (`claim_hash`)."""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import logging
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

import httpx

from herbtwin.advice_context import WeatherFacts
from herbtwin.history import ChatMessage
from herbtwin.pipeline import Reading
from herbtwin.schemas import AnalysisRecord, SpeciesCandidate, StageFailure
from herbtwin.species import PlantMatch

log = logging.getLogger(__name__)

TTL = timedelta(hours=1)  # in memory: tests and local runs
KEEP = timedelta(hours=24)  # in Supabase: the live site (25 Oct, Kash)
MAX_ENTRIES = 500  # memory stays bounded: the oldest answer is dropped first


def claim_hash(key: str) -> str:
    """How a browser's claim key is kept: its SHA-256, never the key (web/claims.py)."""
    return hashlib.sha256(key.encode()).hexdigest()


@dataclass
class Entry:
    reading: Reading | None  # None: the run stopped early (not a plant); no refine
    first_headline: str | None  # the photo-only answer, for "what changed"
    at: datetime
    latest: AnalysisRecord  # the answer as it stands, after any refine: the chat's subject
    owner: str | None = None  # the signed-in person's user id; None when signed out
    last_decline: int | None = None  # days since the plant last declined, for the asks
    chat: list[ChatMessage] = field(default_factory=list)
    claim: str | None = None  # signed out: claim_hash of the key of the browser that got it


class Answers(Protocol):
    """What the app needs of an answer store: AnswerCache and SupabaseAnswerCache."""

    def put(
        self,
        reading: Reading | None,
        first: AnalysisRecord,
        owner: str | None = None,
        last_decline: int | None = None,
        claim: str | None = None,
    ) -> None: ...

    def get(self, answer_id: str) -> Entry | None: ...

    def get_for(self, answer_id: str, owner: str | None) -> Entry | None: ...

    def claim(self, answer_id: str, key: str, owner: str) -> bool: ...

    def unclaim(self, answer_id: str, owner: str) -> None: ...

    def set_latest(self, answer_id: str, rec: AnalysisRecord) -> None: ...

    def set_reading(self, answer_id: str, reading: Reading) -> None: ...

    def add_chat(self, answer_id: str, msg: ChatMessage) -> bool: ...


class AnswerCache:
    def __init__(
        self,
        clock: Callable[[], datetime],
        ttl: timedelta = TTL,
        max_entries: int = MAX_ENTRIES,
    ) -> None:
        self._clock, self._ttl, self._max = clock, ttl, max_entries
        self._entries: OrderedDict[str, Entry] = OrderedDict()
        self._lock = threading.Lock()

    def put(
        self,
        reading: Reading | None,
        first: AnalysisRecord,
        owner: str | None = None,
        last_decline: int | None = None,
        claim: str | None = None,
    ) -> None:
        headline = first.answer.headline if first.answer else None
        with self._lock:
            self._entries[first.record_id] = Entry(
                reading,
                headline,
                self._clock(),
                first,
                owner,
                last_decline,
                claim=claim_hash(claim) if claim is not None else None,
            )
            while len(self._entries) > self._max:
                self._entries.popitem(last=False)

    def get(self, answer_id: str) -> Entry | None:
        with self._lock:
            entry = self._entries.get(answer_id)
            if entry is None:
                return None
            if self._clock() - entry.at > self._ttl:
                del self._entries[answer_id]
                return None
            return entry

    def get_for(self, answer_id: str, owner: str | None) -> Entry | None:
        """The entry only for the person it was made for (None: signed out), so an answer
        id that leaks never hands one person's answer to another."""
        entry = self.get(answer_id)
        return entry if entry is not None and entry.owner == owner else None

    def claim(self, answer_id: str, key: str, owner: str) -> bool:
        """Keep a signed-out answer for `owner`, once: under the lock, only when it is unowned
        and was made for the browser holding `key`. Its chat, first headline and hour stay.
        False when it is gone, already kept, or not this browser's."""
        with self._lock:
            entry = self._entries.get(answer_id)
            if (
                entry is None
                or entry.owner is not None
                or entry.claim is None
                or not hmac.compare_digest(entry.claim, claim_hash(key))
            ):
                return False
            entry.owner = owner
            return True

    def unclaim(self, answer_id: str, owner: str) -> None:
        """Undo a claim whose store write failed, so it can be tried again."""
        with self._lock:
            entry = self._entries.get(answer_id)
            if entry is not None and entry.owner == owner and entry.claim is not None:
                entry.owner = None

    def drop(self, answer_id: str) -> None:
        with self._lock:
            self._entries.pop(answer_id, None)

    def set_latest(self, answer_id: str, rec: AnalysisRecord) -> None:
        with self._lock:
            entry = self._entries.get(answer_id)
            if entry is not None:
                entry.latest = rec

    def set_reading(self, answer_id: str, reading: Reading) -> None:
        with self._lock:
            entry = self._entries.get(answer_id)
            if entry is not None:
                entry.reading = reading

    def add_chat(self, answer_id: str, msg: ChatMessage) -> bool:
        entry = self.get(answer_id)  # drops it if the hour is up
        if entry is None:
            return False
        with self._lock:
            entry.chat.append(msg)
        return True


# --- as JSON, for Supabase -------------------------------------------------------------


def reading_to_json(r: Reading) -> dict[str, Any]:
    """A Reading as plain JSON: its pydantic models dumped, its dataclasses as dicts."""
    return {
        "rec": r.rec.model_dump(mode="json"),
        "match": dataclasses.asdict(r.match),
        "top": r.top.model_dump(mode="json") if r.top is not None else None,
        "month": r.month,
        "season_missing": r.season_missing,
        "weather_missing": r.weather_missing,
        "weather": dataclasses.asdict(r.weather) if r.weather is not None else None,
        "failures": [f.model_dump(mode="json") for f in r.failures],
        "checked": r.checked,
        "received": r.received.isoformat() if r.received is not None else None,
    }


def reading_from_json(d: dict[str, Any]) -> Reading:
    """The Reading `reading_to_json` made. Raises ValueError, KeyError or TypeError on a
    shape it did not make."""
    received = d.get("received")
    return Reading(
        rec=AnalysisRecord.model_validate(d["rec"]),
        match=PlantMatch(**d["match"]),
        top=SpeciesCandidate.model_validate(d["top"]) if d.get("top") is not None else None,
        month=int(d["month"]),
        season_missing=d.get("season_missing"),
        weather_missing=d.get("weather_missing"),
        weather=WeatherFacts(**d["weather"]) if d.get("weather") is not None else None,
        failures=[StageFailure.model_validate(f) for f in d.get("failures") or []],
        checked=bool(d.get("checked", False)),
        received=date.fromisoformat(received) if received is not None else None,
    )


def _entry_from_row(row: dict[str, Any]) -> Entry:
    reading = row.get("reading")
    return Entry(
        reading=reading_from_json(reading) if reading is not None else None,
        first_headline=row.get("first_headline"),
        at=datetime.fromisoformat(row["created_at"]),
        latest=AnalysisRecord.model_validate(row["record"]),
        owner=row.get("owner"),
        last_decline=row.get("last_decline"),
        chat=[ChatMessage.model_validate(m) for m in row.get("chat") or []],
        claim=row.get("claim_hash"),
    )


def _stamp(t: datetime) -> str:
    """A time for a PostgREST filter: UTC with a Z (a "+00:00" in a query reads as a space)."""
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class SupabaseAnswerCache:
    """The answers in Supabase's answer_cache table for 24 hours, with the server's secret
    key: the same methods and rules as AnswerCache. Supabase down never breaks a page: each
    failure is logged. An answer whose write failed is kept in this server's memory instead
    (an AnswerCache, bounded, gone at a restart), so the paid read it came from still shows,
    and every later call for that id goes there; any other read Supabase cannot answer is
    "not there" (get None, claim and add_chat False), and other failed writes are skipped.

    No row cap, unlike AnswerCache's MAX_ENTRIES: the table holds at most about two days of
    answers (24 hours kept, then deleted by the daily job's purge_answer_cache; reads never
    see a row past its 24 hours), and new answers come from photo reads, which the caps hold to
    Limits.day_reads a day site-wide (judges and same-day repeats of a photo aside). Each row
    is text and numbers, tens of kilobytes, never a photo."""

    def __init__(
        self,
        url: str,
        secret_key: str,
        clock: Callable[[], datetime],
        client: httpx.Client | None = None,
        keep: timedelta = KEEP,
    ) -> None:
        self.url = url.rstrip("/")
        self.headers = {"apikey": secret_key, "Authorization": f"Bearer {secret_key}"}
        self.client = client or httpx.Client(timeout=httpx.Timeout(5.0, connect=2.0))
        self._clock, self._keep = clock, keep
        self._memory = AnswerCache(clock, ttl=keep)  # answers whose write to Supabase failed

    def _held(self, answer_id: str) -> bool:
        return self._memory.get(answer_id) is not None

    def _send(self, what: str, method: str, path: str, **kw) -> httpx.Response | None:
        headers = {**self.headers, **kw.pop("headers", {})}
        try:
            r = self.client.request(method, f"{self.url}{path}", headers=headers, **kw)
            r.raise_for_status()
        except httpx.HTTPError:
            log.exception("answer cache: %s failed", what)
            return None
        return r

    def _rpc(self, name: str, body: dict[str, Any]) -> Any:
        r = self._send(name, "POST", f"/rest/v1/rpc/{name}", json=body)
        if r is None:
            return None
        try:
            return r.json()
        except ValueError:
            log.exception("answer cache: %s gave no JSON", name)
            return None

    def _patch(self, what: str, params: dict[str, str], body: dict[str, Any]) -> None:
        self._send(
            what,
            "PATCH",
            "/rest/v1/answer_cache",
            params=params,
            json=body,
            headers={"Prefer": "return=minimal"},
        )

    def put(
        self,
        reading: Reading | None,
        first: AnalysisRecord,
        owner: str | None = None,
        last_decline: int | None = None,
        claim: str | None = None,
    ) -> None:
        row = {
            "id": first.record_id,
            "owner": owner,
            "claim_hash": claim_hash(claim) if claim is not None else None,
            "record": first.model_dump(mode="json"),
            "reading": reading_to_json(reading) if reading is not None else None,
            "first_headline": first.answer.headline if first.answer else None,
            "last_decline": last_decline,
            "chat": [],
            "created_at": _stamp(self._clock()),
        }
        sent = self._send(
            "put",
            "POST",
            "/rest/v1/answer_cache",
            json=row,
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        # A request that errored after Supabase saved the row (a lost reply, a timeout) leaves a
        # copy in both: memory's is the one used for this id until it ages out or a later
        # write lands, and Supabase's goes at the daily purge. Harmless: it is the same answer.
        if sent is None:  # the read was paid for: show it from memory rather than "expired"
            log.warning("answer cache: answer %s kept in memory instead", first.record_id)
            self._memory.put(reading, first, owner, last_decline, claim)
        else:
            self._memory.drop(first.record_id)  # Supabase has the newer copy

    def get(self, answer_id: str) -> Entry | None:
        held = self._memory.get(answer_id)
        if held is not None:
            return held
        cutoff = _stamp(self._clock() - self._keep)
        r = self._send(
            "get",
            "GET",
            "/rest/v1/answer_cache",
            params={"select": "*", "id": f"eq.{answer_id}", "created_at": f"gt.{cutoff}"},
        )
        if r is None:
            return None
        try:
            rows = r.json()
            return _entry_from_row(rows[0]) if rows else None  # none: gone, or past 24 hours
        except (ValueError, KeyError, TypeError):  # pydantic's ValidationError is a ValueError
            log.exception("answer cache: could not read answer %s", answer_id)
            return None

    def get_for(self, answer_id: str, owner: str | None) -> Entry | None:
        """The entry only for the person it was made for (None: signed out)."""
        entry = self.get(answer_id)
        return entry if entry is not None and entry.owner == owner else None

    def claim(self, answer_id: str, key: str, owner: str) -> bool:
        """Keep a signed-out answer for `owner`, once, in one statement (claim_answer): only
        the key's hash is sent."""
        if self._held(answer_id):
            return self._memory.claim(answer_id, key, owner)
        got = self._rpc(
            "claim_answer",
            {"p_id": answer_id, "p_claim_hash": claim_hash(key), "p_owner": owner},
        )
        return got is True

    def unclaim(self, answer_id: str, owner: str) -> None:
        """Undo a claim whose store write failed, so it can be tried again."""
        if self._held(answer_id):
            return self._memory.unclaim(answer_id, owner)
        self._patch(
            "unclaim",
            {"id": f"eq.{answer_id}", "owner": f"eq.{owner}", "claim_hash": "not.is.null"},
            {"owner": None},
        )

    def set_latest(self, answer_id: str, rec: AnalysisRecord) -> None:
        if self._held(answer_id):
            return self._memory.set_latest(answer_id, rec)
        self._patch(
            "set_latest", {"id": f"eq.{answer_id}"}, {"record": rec.model_dump(mode="json")}
        )

    def set_reading(self, answer_id: str, reading: Reading) -> None:
        if self._held(answer_id):
            return self._memory.set_reading(answer_id, reading)
        self._patch("set_reading", {"id": f"eq.{answer_id}"}, {"reading": reading_to_json(reading)})

    def add_chat(self, answer_id: str, msg: ChatMessage) -> bool:
        if self._held(answer_id):
            return self._memory.add_chat(answer_id, msg)
        got = self._rpc(
            "add_answer_chat", {"p_id": answer_id, "p_msg": msg.model_dump(mode="json")}
        )
        return got is True

    def purge(self) -> int | None:
        """Delete every answer past its 24 hours (the daily job): how many went, None when
        Supabase could not be asked."""
        got = self._rpc("purge_answer_cache", {})
        return got if isinstance(got, int) and not isinstance(got, bool) else None
