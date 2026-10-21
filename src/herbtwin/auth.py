"""Sign-in by emailed link, spent only by our server (spec section 5; pattern from
~/Code/tools/docs/app-services-stack.md). Plain httpx against Supabase Auth (GoTrue).
The secret key is used only for account delete."""

from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

log = logging.getLogger(__name__)
EXPIRED_LINK = "That link has expired or was already used. Send a new one."
TIMEOUT_S = 15.0
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    def __init__(self, message: str, *, expired: bool = False) -> None:
        super().__init__(message)
        self.expired = expired


@dataclass(frozen=True)
class Session:
    access_token: str
    refresh_token: str
    expires_at: datetime
    user_id: str
    email: str


def valid_email(text: str) -> str:
    email = text.strip().casefold()
    if len(email) > 254 or not _EMAIL.match(email):
        raise ValueError("Enter a valid email address.")
    return email


class SupabaseAuth:
    def __init__(
        self,
        url: str,
        publishable_key: str,
        secret_key: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.url, self.key, self.secret = url.rstrip("/"), publishable_key, secret_key
        self.http = client or httpx.Client(timeout=TIMEOUT_S)

    def _call(
        self, method: str, path: str, *, key: str | None = None, token: str | None = None, **kw
    ) -> httpx.Response:
        headers = {"apikey": key or self.key}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            return self.http.request(method, f"{self.url}/auth/v1{path}", headers=headers, **kw)
        except httpx.HTTPError as e:
            log.exception("supabase auth %s %s failed", method, path)
            raise AuthError("Sign-in is not available right now. Try again soon.") from e

    def _session(self, r: httpx.Response) -> Session:
        d = r.json()
        return Session(
            access_token=d["access_token"],
            refresh_token=d["refresh_token"],
            expires_at=datetime.now(UTC) + timedelta(seconds=int(d.get("expires_in", 3600))),
            user_id=d["user"]["id"],
            email=d["user"].get("email", ""),
        )

    def send_link(self, email: str) -> None:
        r = self._call("POST", "/otp", json={"email": email, "create_user": True})
        if r.status_code == 429:
            raise AuthError("Too many sign-in emails just now. Wait a few minutes and try again.")
        if r.status_code >= 400:
            log.error("send_link refused: %s %s", r.status_code, r.text[:200])
            raise AuthError("Could not send the sign-in email. Try again soon.")

    def verify(self, token_hash: str, kind: str) -> Session:
        r = self._call("POST", "/verify", json={"type": kind, "token_hash": token_hash})
        if r.status_code in (400, 401, 403, 404, 410, 422):
            raise AuthError(EXPIRED_LINK, expired=True)
        if r.status_code >= 400:
            log.error("verify refused: %s %s", r.status_code, r.text[:200])
            raise AuthError("Sign-in is not available right now. Try again soon.")
        return self._session(r)

    def refresh(self, refresh_token: str) -> Session:
        r = self._call(
            "POST",
            "/token",
            params={"grant_type": "refresh_token"},
            json={"refresh_token": refresh_token},
        )
        if r.status_code in (400, 401):  # the refresh token was refused: signed out
            raise AuthError("Your sign-in has ended. Sign in again.", expired=True)
        if r.status_code >= 400:  # an outage is not a sign-out: keep the cookies
            log.error("refresh failed: %s %s", r.status_code, r.text[:200])
            raise AuthError("Sign-in is not available right now. Try again soon.")
        return self._session(r)

    def user(self, access_token: str) -> tuple[str, str] | None:
        r = self._call("GET", "/user", token=access_token)
        if r.status_code in (401, 403):
            return None
        if r.status_code >= 400:
            raise AuthError("Sign-in is not available right now. Try again soon.")
        d = r.json()
        return d["id"], d.get("email", "")

    @staticmethod
    def token_subject(access_token: str) -> str | None:
        """The user id an access token names, read without checking its signature. Only
        used to finish deleting an account that Supabase confirms is already gone."""
        try:
            payload = access_token.split(".")[1]
            data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        except (IndexError, ValueError):
            return None
        sub = data.get("sub") if isinstance(data, dict) else None
        return sub if isinstance(sub, str) else None

    def sign_out(self, access_token: str) -> None:
        try:
            self._call("POST", "/logout", token=access_token)
        except AuthError:
            log.warning("sign-out call failed; cookies are cleared anyway")

    def _admin(self) -> str:
        if not self.secret:
            raise AuthError("Account delete is not set up on this server.")
        return self.secret

    def delete_user(self, user_id: str) -> None:
        key = self._admin()
        r = self._call("DELETE", f"/admin/users/{user_id}", key=key, token=key)
        if r.status_code >= 400 and r.status_code != 404:
            log.error("delete_user refused: %s %s", r.status_code, r.text[:200])
            raise AuthError("Could not delete your account. Nothing was lost; try again.")

    def user_exists(self, user_id: str) -> bool:
        key = self._admin()
        r = self._call("GET", f"/admin/users/{user_id}", key=key, token=key)
        if r.status_code == 404:
            return False
        if r.status_code == 200:
            return True
        raise AuthError("Could not confirm the account is gone. Try again.")
