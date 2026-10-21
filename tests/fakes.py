"""In-memory stand-ins for Supabase Auth, for the web tests."""

import html
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from herbtwin.auth import EXPIRED_LINK, AuthError, Session
from herbtwin.history import MemoryHistory
from herbtwin.web.accounts import Accounts


@dataclass
class FakeAuth:
    links: list[str] = field(default_factory=list)
    hashes: dict[str, tuple[str, str]] = field(default_factory=dict)  # hash -> (uid, email)
    tokens: dict[str, tuple[str, str]] = field(default_factory=dict)  # access -> (uid, email)
    refreshes: dict[str, tuple[str, str]] = field(default_factory=dict)
    users: set[str] = field(default_factory=set)
    down: bool = False

    def issue(self, uid: str, email: str) -> str:
        h = f"hash-{len(self.hashes)}"
        self.hashes[h] = (uid, email)
        self.users.add(uid)
        return h

    def _session(self, uid, email) -> Session:
        n = len(self.tokens)
        at, rt = f"at-{uid}-{n}", f"rt-{uid}-{n}"
        self.tokens[at], self.refreshes[rt] = (uid, email), (uid, email)
        return Session(at, rt, datetime.now(UTC) + timedelta(hours=1), uid, email)

    def send_link(self, email):
        if self.down:
            raise AuthError("Sign-in is not available right now. Try again soon.")
        self.links.append(email)

    def verify(self, token_hash, kind):
        got = self.hashes.pop(token_hash, None)
        if got is None:
            raise AuthError(EXPIRED_LINK, expired=True)
        return self._session(*got)

    def refresh(self, refresh_token):
        got = self.refreshes.pop(refresh_token, None)
        if got is None or got[0] not in self.users:
            raise AuthError("Your sign-in has ended. Sign in again.", expired=True)
        return self._session(*got)

    def user(self, access_token):
        if self.down:
            raise AuthError("Sign-in is not available right now. Try again soon.")
        got = self.tokens.get(access_token)
        return got if got and got[0] in self.users else None

    def token_subject(self, access_token):
        """The user id a token names (tokens here are at-<uid>-<n>)."""
        parts = access_token.split("-")
        return parts[1] if len(parts) == 3 and parts[0] == "at" else None

    def expire(self, access_token):
        self.tokens.pop(access_token, None)

    def sign_out(self, access_token):
        self.tokens.pop(access_token, None)

    def delete_user(self, user_id):
        self.users.discard(user_id)

    def user_exists(self, user_id):
        if self.down:
            raise AuthError("Could not confirm the account is gone. Try again.")
        return user_id in self.users


def fake_accounts(hist: MemoryHistory, auth: FakeAuth) -> Accounts:
    def sweep(user_id: str) -> int:
        mine = [k for k in hist.photos if k.startswith(f"{user_id}/")]
        for k in mine:
            del hist.photos[k]
        return len(mine)

    return Accounts(
        auth=auth,
        store_for=lambda uid, token: hist.for_user(uid),
        secure=False,
        delete_folder=sweep,
    )


NEXT = re.compile(r'<a id="next" href="([^"]+)"')


def follow(client, r):
    """The streamed upload page ends with a link to the answer (D58); follow it the way
    the page's own jump does, and return that page."""
    assert r.status_code == 200, r.text
    m = NEXT.search(r.text)
    assert m is not None, r.text[-500:]
    return client.get(html.unescape(m.group(1)))


@dataclass
class FakeSink:
    """Stands in for LangSmith: keeps what would have been sent (D64)."""

    runs: list[dict] = field(default_factory=list)
    updates: list[tuple] = field(default_factory=list)  # (run_id, fields)
    feedback: list[tuple] = field(default_factory=list)  # (run_id, key, value, comment)
    down: bool = False

    def _check(self) -> None:
        if self.down:
            raise ConnectionError("langsmith down")

    def create_run(self, run: dict) -> None:
        self._check()
        self.runs.append(run)

    def update_run(self, run_id, fields: dict) -> None:
        """As LangSmith does: one update per run (a second is a 409), and a run whose
        update carries a nested dotted order but no parent is refused (a 400)."""
        self._check()
        if any(r == run_id for r, _ in self.updates):
            raise RuntimeError("409 Run update payload already received")
        if "." in str(fields.get("dotted_order", "")) and fields.get("parent_run_id") is None:
            raise RuntimeError("400 dotted_order must contain a single part for root runs")
        self.updates.append((run_id, fields))

    def create_feedback(self, run_id, key: str, value: str, comment: str | None) -> None:
        self._check()
        self.feedback.append((run_id, key, value, comment))

    def roots(self) -> list[dict]:
        return [r for r in self.runs if r["parent_run_id"] is None]

    def under(self, run_id) -> list[dict]:
        return [r for r in self.runs if r["parent_run_id"] == run_id]
