"""HistoryStore on Supabase: PostgREST for rows and Storage for photos, always as the
signed-in person (their access token), so row-level security decides what they reach.
Only delete_folder uses the secret key (account delete)."""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from herbtwin.history import (
    AdviceScore,
    ChatMessage,
    Evidence,
    HistoryError,
    Plant,
    StoredAnswer,
    StoredSpot,
    UserSettings,
    photo_path,
    thumb_path,
    utc,
)
from herbtwin.reminders import Reminder
from herbtwin.schemas import Answer, Aspect, Location, Told

log = logging.getLogger(__name__)
TIMEOUT_S = 15.0
BUCKET = "photos"
SIGNED_S = 3600


class SupabaseHistoryStore:
    def __init__(
        self,
        url: str,
        publishable_key: str,
        access_token: str,
        user_id: str,
        client: httpx.Client | None = None,
    ) -> None:
        self.url, self.key, self.token, self.user_id = (
            url.rstrip("/"),
            publishable_key,
            access_token,
            user_id,
        )
        self.http = client or httpx.Client(timeout=TIMEOUT_S)

    def _req(self, method: str, path: str, **kw) -> httpx.Response:
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.token}",
            **kw.pop("headers", {}),
        }
        try:
            r = self.http.request(method, f"{self.url}{path}", headers=headers, **kw)
        except httpx.HTTPError as e:
            log.exception("supabase %s %s failed", method, path)
            raise HistoryError("History is not available right now.") from e
        if r.status_code >= 400:
            log.error("supabase %s %s -> %s %s", method, path, r.status_code, r.text[:200])
            raise HistoryError("History is not available right now.")
        return r

    def _rows(self, table: str, params: dict) -> list[dict]:
        return self._req("GET", f"/rest/v1/{table}", params=params).json()

    def list_plants(self) -> list[Plant]:
        return [
            Plant.model_validate(r)
            for r in self._rows("plants", {"select": "*", "order": "created_at.asc"})
        ]

    def create_plant(self, name, species, genus, place: Location | None) -> Plant:
        body = {
            "name": name,
            "species": species,
            "genus": genus,
            "place_lat": place.lat if place else None,
            "place_lon": place.lon if place else None,
        }
        r = self._req(
            "POST", "/rest/v1/plants", json=body, headers={"Prefer": "return=representation"}
        )
        return Plant.model_validate(r.json()[0])

    def rename_plant(self, plant_id, name):
        self._req("PATCH", "/rest/v1/plants", params={"id": f"eq.{plant_id}"}, json={"name": name})

    def delete_plant(self, plant_id):
        # photo paths follow the answer id, so an unrecorded path still goes with the plant
        paths = [
            photo_path(self.user_id, a.id.replace("-", "")) for a in self.answers_for(plant_id)
        ]
        if paths:
            self._req(
                "DELETE",
                f"/storage/v1/object/{BUCKET}",
                json={"prefixes": paths + [thumb_path(p) for p in paths]},
            )
        self._req("DELETE", "/rest/v1/plants", params={"id": f"eq.{plant_id}"})

    def add_answer(self, a: StoredAnswer) -> None:
        self._req(
            "POST",
            "/rest/v1/answers",
            content=a.model_dump_json(exclude={"created_at"}),
            headers={"Content-Type": "application/json"},
        )

    def update_answer(
        self, answer_id, answer: Answer | None, told: Told | None, evidence: Evidence | None = None
    ):
        body = {
            "answer": answer.model_dump(mode="json") if answer else None,
            "told": told.model_dump(mode="json") if told else None,
        }
        if evidence is not None:
            body["evidence"] = evidence.model_dump(mode="json")
        self._req("PATCH", "/rest/v1/answers", params={"id": f"eq.{answer_id}"}, json=body)

    def set_photo(self, answer_id: str, path: str) -> None:
        body = {"photo_path": path}
        self._req("PATCH", "/rest/v1/answers", params={"id": f"eq.{answer_id}"}, json=body)

    def get_answer(self, answer_id):
        rows = self._rows("answers", {"select": "*", "id": f"eq.{answer_id}"})
        return StoredAnswer.model_validate(rows[0]) if rows else None

    def answers_for(self, plant_id):
        rows = self._rows(
            "answers", {"select": "*", "plant_id": f"eq.{plant_id}", "order": "taken_at.desc"}
        )
        return [StoredAnswer.model_validate(r) for r in rows]

    def add_chat(self, answer_id: str, msg: ChatMessage) -> None:
        body = {
            "answer_id": answer_id,
            "role": msg.role,
            "content": msg.content,
            "tools": msg.tools,
        }
        self._req("POST", "/rest/v1/chat_messages", json=body)

    def chat_for(self, answer_id: str) -> list[ChatMessage]:
        rows = self._rows(
            "chat_messages",
            {
                "select": "role,content,tools,created_at",
                "answer_id": f"eq.{answer_id}",
                "order": "created_at.asc",
            },
        )
        return [ChatMessage.model_validate(r) for r in rows]

    def latest_by_plant(self):
        rows = self._rows("answers", {"select": "*", "order": "taken_at.desc"})
        out: dict[str, StoredAnswer] = {}
        for r in rows:
            out.setdefault(r["plant_id"], StoredAnswer.model_validate(r))
        return out

    def put_photo(self, answer_id, jpeg, thumb):
        path = photo_path(self.user_id, answer_id)
        for p, data in ((path, jpeg), (thumb_path(path), thumb)):
            self._req(
                "POST",
                f"/storage/v1/object/{BUCKET}/{p}",
                content=data,
                headers={"Content-Type": "image/jpeg", "x-upsert": "true"},
            )
        return path

    def photo_url(self, path, *, thumb=True):
        target = thumb_path(path) if thumb else path
        try:
            r = self._req(
                "POST", f"/storage/v1/object/sign/{BUCKET}/{target}", json={"expiresIn": SIGNED_S}
            )
        except HistoryError:
            return None
        signed = r.json().get("signedURL") or r.json().get("signedUrl")
        return f"{self.url}/storage/v1{signed}" if signed else None

    def get_photo(self, path):
        return self._req("GET", f"/storage/v1/object/authenticated/{BUCKET}/{path}").content

    def add_score(self, s: AdviceScore) -> None:
        c = s.comparison
        body = {
            "plant_id": s.plant_id,
            "earlier_answer_id": s.earlier_answer_id,
            "later_answer_id": s.later_answer_id,
            "action": s.prediction.action,
            "prediction": s.prediction.model_dump(mode="json"),
            "signal": s.prediction.signal,
            "did_it": s.did_it,
            "result": s.result,
            "reason": s.reason,
            "comparison": c.model_dump(mode="json") if c else None,
            "prompt_version": c.prompt_version if c else None,
            "model": c.model if c else None,
            "scored_at": s.scored_at.isoformat(),
        }
        self._req("POST", "/rest/v1/advice_scores", json=body)

    def scores_for(self, plant_id: str) -> list[AdviceScore]:
        rows = self._rows(
            "advice_scores",
            {
                "select": "plant_id,earlier_answer_id,later_answer_id,prediction,did_it,"
                "result,reason,comparison,scored_at",
                "plant_id": f"eq.{plant_id}",
                "order": "scored_at.desc",
            },
        )
        return [AdviceScore.model_validate(r) for r in rows]

    def get_settings(self) -> UserSettings:
        rows = self._rows(
            "user_settings",
            {"select": "share_scored_pairs,asked_at", "user_id": f"eq.{self.user_id}"},
        )
        return UserSettings.model_validate(rows[0]) if rows else UserSettings()

    def get_reminder(self, answer_id: str) -> Reminder | None:
        rows = self._rows("reminders", {"select": "*", "answer_id": f"eq.{answer_id}"})
        return Reminder.model_validate(rows[0]) if rows else None

    def set_reminder(self, answer_id: str, r: Reminder | None) -> None:
        if r is None:
            self._req("DELETE", "/rest/v1/reminders", params={"answer_id": f"eq.{answer_id}"})
            return
        self._req(
            "POST",
            "/rest/v1/reminders",
            content=r.model_dump_json(exclude={"user_id", "sent_at", "off_at"}),
            headers={"Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"},
        )

    def save_spot(self, s: StoredSpot) -> None:
        body = {
            "id": s.id,
            "taken_at": s.taken_at.isoformat(),
            "place_lat": s.place.lat if s.place else None,
            "place_lon": s.place.lon if s.place else None,
            "aspect": s.aspect.model_dump(mode="json") if s.aspect else None,
            "spot": s.spot.model_dump(mode="json"),
            "grow": s.grow.model_dump(mode="json") if s.grow else None,
        }
        self._req(
            "POST",
            "/rest/v1/spots",
            json=body,
            headers={"Prefer": "resolution=merge-duplicates"},
        )

    def recent_aspect(self, place: Location, since: datetime) -> tuple[Aspect, datetime] | None:
        rows = self._rows(
            "spots",
            {
                "select": "aspect,taken_at",
                "place_lat": f"eq.{place.lat}",
                "place_lon": f"eq.{place.lon}",
                "aspect": "not.is.null",
                "taken_at": f"gte.{utc(since).isoformat()}",
                "order": "taken_at.desc",
                "limit": "1",
            },
        )
        if not rows:
            return None
        return Aspect.model_validate(rows[0]["aspect"]), utc(
            datetime.fromisoformat(rows[0]["taken_at"])
        )

    def set_sharing(self, share: bool, now: datetime) -> None:
        body = {
            "user_id": self.user_id,
            "share_scored_pairs": share,
            "asked_at": utc(now).isoformat(),
        }
        self._req(
            "POST",
            "/rest/v1/user_settings",
            json=body,
            headers={"Prefer": "resolution=merge-duplicates"},
        )


def delete_folder(
    url: str, secret_key: str, user_id: str, client: httpx.Client | None = None
) -> int:
    """Admin sweep of photos/<user_id>/, a page at a time until a listing comes back empty."""
    http = client or httpx.Client(timeout=TIMEOUT_S)
    headers = {"apikey": secret_key, "Authorization": f"Bearer {secret_key}"}
    removed = 0
    for _ in range(100):  # bounded: 100 pages of 100
        try:
            r = http.post(
                f"{url}/storage/v1/object/list/{BUCKET}",
                headers=headers,
                json={"prefix": user_id, "limit": 100, "offset": 0},
            )
            r.raise_for_status()
            names = [f"{user_id}/{o['name']}" for o in r.json() if o.get("name")]
            if not names:
                return removed
            d = http.request(
                "DELETE",
                f"{url}/storage/v1/object/{BUCKET}",
                headers=headers,
                json={"prefixes": names},
            )
            d.raise_for_status()
        except httpx.HTTPError as e:
            log.exception("photo sweep failed for a deleted account")
            raise HistoryError("Could not delete your photos. Nothing was lost; try again.") from e
        removed += len(names)
    raise HistoryError("Could not delete your photos. Nothing was lost; try again.")
