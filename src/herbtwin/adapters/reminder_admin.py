"""The reminder job's view of Supabase (spec section 7): across people, with the secret
key, and only through the columns the reminders migration grants the service role."""

from __future__ import annotations

import logging
from datetime import date, datetime

import httpx

from herbtwin.history import utc
from herbtwin.reminders import AdminError, OffReason, Reminder

log = logging.getLogger(__name__)
# every column the service role may read (supabase/migrations/20261013120000_reminders.sql)
COLUMNS = "answer_id,user_id,plant_id,plant_name,action,taken_at,due_on,last_on,sent_at,off_at"


class SupabaseReminderAdmin:
    def __init__(self, url: str, secret_key: str, client: httpx.Client) -> None:
        self.url, self.key, self.http = url.rstrip("/"), secret_key, client

    def _req(self, method: str, path: str, **kw) -> httpx.Response:
        headers = {"apikey": self.key, "Authorization": f"Bearer {self.key}"}
        headers.update(kw.pop("headers", {}))
        try:
            r = self.http.request(method, f"{self.url}{path}", headers=headers, **kw)
        except httpx.HTTPError as e:
            raise AdminError(f"supabase {method} {path}: {type(e).__name__}") from e
        if r.status_code >= 400 and r.status_code != 404:
            log.error("supabase %s %s -> %s %s", method, path, r.status_code, r.text[:200])
            raise AdminError(f"supabase {method} {path}: HTTP {r.status_code}")
        return r

    def due(self, today: date) -> list[Reminder]:
        params = {
            "select": COLUMNS,
            "due_on": f"lte.{today.isoformat()}",
            "sent_at": "is.null",
            "off_at": "is.null",
            "order": "due_on.asc",
        }
        r = self._req("GET", "/rest/v1/reminders", params=params)
        if r.status_code == 404:
            raise AdminError("supabase: no reminders table")
        return [Reminder.model_validate(row) for row in r.json()]

    def followed_up(self, r: Reminder) -> bool:
        params = {
            "select": "plant_id",
            "plant_id": f"eq.{r.plant_id}",
            "taken_at": f"gt.{utc(r.taken_at).isoformat()}",
            "limit": "1",
        }
        got = self._req("GET", "/rest/v1/answers", params=params)
        if got.status_code == 404:
            raise AdminError("supabase: no answers table")
        return bool(got.json())

    def email_of(self, user_id: str) -> str | None:
        r = self._req("GET", f"/auth/v1/admin/users/{user_id}")
        if r.status_code == 404:
            return None
        return r.json().get("email") or None

    def mark_sent(self, answer_id: str, now: datetime) -> None:
        self._req(
            "PATCH",
            "/rest/v1/reminders",
            params={"answer_id": f"eq.{answer_id}", "sent_at": "is.null"},
            json={"sent_at": utc(now).isoformat()},
        )

    def turn_off(self, answer_id: str, reason: OffReason, now: datetime) -> bool:
        r = self._req(
            "PATCH",
            "/rest/v1/reminders",
            # return only a column the service role may read: "*" would be refused
            params={
                "answer_id": f"eq.{answer_id}",
                "off_at": "is.null",
                "sent_at": "is.null",
                "select": "answer_id",
            },
            json={"off_at": utc(now).isoformat(), "off_reason": reason},
            headers={"Prefer": "return=representation"},
        )
        return r.status_code != 404 and bool(r.json())
