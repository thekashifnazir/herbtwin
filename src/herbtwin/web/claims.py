"""Signing in from a signed-out answer keeps THAT answer (19 Oct, Kash: "as a user you would
expect it to work").

Only the browser that got the answer can claim it. The answer's id is in its URL and in
any shared link, so it proves nothing. Instead, a signed-out upload gives the browser a
random key in an httponly cookie, signed with the existing reminder secret (no new
secret), and the answer cache keeps that key's SHA-256 beside the answer. A claim needs the
cookie's key to hash to the answer's, the answer to be in the cache (24 hours on the live
site), and no owner yet; the claim sets the owner atomically (AnswerCache.claim, or the
claim_answer function in Supabase), so it happens once. Signing in only
brings the person back to the answer: it is kept by an explicit, same-site "Keep this in My
plants (signed in as ...)" tap, so a sign-in someone else arranged cannot carry it off.
Without the secret nothing is set and nothing can be claimed.

The sign-in link comes back by email, so where to return is kept in a second signed cookie,
and only an answer's own path is accepted (no open redirect).
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from urllib.parse import urlsplit

from fastapi import Request, Response

from herbtwin.answer_cache import KEEP, Entry, claim_hash

KEY_COOKIE = "herbtwin_claim"
NEXT_COOKIE = "herbtwin_next"
MAX_AGE_S = int(KEEP.total_seconds())  # as long as the longest an answer is kept
_ANSWER_PATH = re.compile(r"/answers/[0-9a-f]{32}")


def _mac(context: str, value: str, secret: str) -> str:
    return hmac.new(secret.encode(), f"{context}:{value}".encode(), hashlib.sha256).hexdigest()


def _signed(context: str, value: str, secret: str) -> str:
    return f"{value}.{_mac(context, value, secret)}"


def _unsigned(context: str, cookie: str | None, secret: str) -> str | None:
    if not cookie or "." not in cookie:
        return None
    value, mac = cookie.rsplit(".", 1)
    # as bytes: a str compare raises on non-ASCII, and a cookie is untrusted input
    return (
        value if hmac.compare_digest(mac.encode(), _mac(context, value, secret).encode()) else None
    )


def _set(response: Response, name: str, value: str, secure: bool) -> None:
    response.set_cookie(
        name, value, max_age=MAX_AGE_S, httponly=True, secure=secure, samesite="lax", path="/"
    )


def browser_key(request: Request, secret: str | None) -> str | None:
    """This browser's claim key, when its cookie is present and signed by us."""
    if not secret:
        return None
    return _unsigned("claim", request.cookies.get(KEY_COOKIE), secret)


def give_key(request: Request, response: Response, secret: str, secure: bool) -> str:
    """The browser's claim key, made on its first signed-out upload; refreshed each time."""
    key = browser_key(request, secret) or secrets.token_hex(16)
    _set(response, KEY_COOKIE, _signed("claim", key, secret), secure)
    return key


def can_claim(entry: Entry | None, key: str | None) -> bool:
    """A cached, unowned answer made for this browser: the cache drops it when its time is up."""
    return (
        entry is not None
        and entry.owner is None
        and entry.reading is not None
        and entry.latest.answer is not None
        and entry.claim is not None
        and key is not None
        and hmac.compare_digest(entry.claim, claim_hash(key))
    )


def safe_next(path: str | None) -> str | None:
    """Only an answer's own path: never another site, another page or a scheme."""
    return path if path and _ANSWER_PATH.fullmatch(path) else None


def _from_the_answer(request: Request, path: str, site_url: str | None) -> bool:
    """The sign-in page was opened from that answer on this site, not by another site (a
    page elsewhere must not plant a way back into someone's answer). Behind the edge worker
    the app sees its own host, so the public site counts as this site too."""
    fetched = request.headers.get("sec-fetch-site")
    if fetched is not None:
        return fetched == "same-origin"
    ref = urlsplit(request.headers.get("referer") or "")
    hosts = {request.url.netloc} | ({urlsplit(site_url).netloc} if site_url else set())
    return bool(ref.netloc) and ref.netloc in hosts and ref.path == path


def keep_next(
    request: Request,
    response: Response,
    path: str | None,
    secret: str | None,
    secure: bool,
    site_url: str | None = None,
) -> None:
    """Remember where the sign-in started; any other sign-in clears an old way back, so a
    second person on a shared browser never lands in the first person's answer."""
    path = safe_next(path)
    if secret and path and _from_the_answer(request, path, site_url):
        _set(response, NEXT_COOKIE, _signed("next", path, secret), secure)
    elif request.cookies.get(NEXT_COOKIE) is not None:
        response.delete_cookie(NEXT_COOKIE, path="/")


def has_next(request: Request, secret: str | None) -> bool:
    return (
        bool(secret)
        and safe_next(_unsigned("next", request.cookies.get(NEXT_COOKIE), secret or "")) is not None
    )


def forget(response: Response) -> None:
    """Sign-out: this browser's key and any way back go with the session."""
    response.delete_cookie(KEY_COOKIE, path="/")
    response.delete_cookie(NEXT_COOKIE, path="/")


def take_next(request: Request, response: Response, secret: str | None) -> str | None:
    """Where the sign-in started, used once."""
    if request.cookies.get(NEXT_COOKIE) is not None:
        response.delete_cookie(NEXT_COOKIE, path="/")
    if not secret:
        return None
    return safe_next(_unsigned("next", request.cookies.get(NEXT_COOKIE), secret))


def answer_id(path: str) -> str:
    return path.rsplit("/", 1)[1]
