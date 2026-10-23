"""Optional accounts for the web layer (spec section 5): on only when Supabase settings
exist, tokens in httpOnly cookies, refreshed when the access token is refused."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from http.cookiejar import CookieJar, DefaultCookiePolicy

import httpx
from fastapi import Request, Response
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from herbtwin.auth import TIMEOUT_S, AuthError, Session, SupabaseAuth
from herbtwin.config import Settings
from herbtwin.history import HistoryStore

log = logging.getLogger(__name__)
ACCESS, REFRESH = "herbtwin_at", "herbtwin_rt"
REFRESH_DAYS = 30
KEEPALIVE_S = 30.0  # an idle Supabase connection is kept this long for the next page


@dataclass
class Accounts:
    auth: SupabaseAuth  # or tests' FakeAuth with the same methods
    store_for: Callable[[str, str], HistoryStore]  # (user_id, access_token) -> store
    secure: bool
    delete_folder: Callable[[str], int] | None
    http: httpx.Client | None = None  # the shared Supabase client, closed when the app stops


@dataclass(frozen=True)
class Person:
    user_id: str
    email: str
    store: HistoryStore


def accounts_from(settings: Settings) -> Accounts | None:
    if not settings.accounts_enabled:
        return None
    from herbtwin.adapters.supabase_store import SupabaseHistoryStore, delete_folder

    url, key, secret = (
        settings.supabase_url,
        settings.supabase_publishable_key,
        settings.supabase_secret_key,
    )
    http = supabase_client()
    return Accounts(
        auth=SupabaseAuth(url, key, secret, http),
        store_for=lambda uid, token: SupabaseHistoryStore(url, key, token, uid, http),
        secure=settings.site_url.startswith("https://"),
        delete_folder=(lambda uid: delete_folder(url, secret, uid, http)) if secret else None,
        http=http,
    )


def supabase_client() -> httpx.Client:
    """One client for every Supabase call the app makes, made once per app: its pool keeps
    connections open between calls, so a page's reads skip the TCP and TLS handshake (23
    Oct audit: each read opened a new connection). httpx clients are thread-safe, so the
    reads a page runs side by side share it. Each call still sends its own token, and the
    client keeps no cookies: one a response sets must never reach another person."""
    return httpx.Client(
        timeout=TIMEOUT_S,
        cookies=CookieJar(DefaultCookiePolicy(allowed_domains=[])),  # accepts none
        limits=httpx.Limits(max_keepalive_connections=20, keepalive_expiry=KEEPALIVE_S),
    )


def set_session(response: Response, s: Session, secure: bool) -> None:
    kw = dict(httponly=True, secure=secure, samesite="lax", path="/")
    response.set_cookie(ACCESS, s.access_token, max_age=3600, **kw)
    response.set_cookie(REFRESH, s.refresh_token, max_age=REFRESH_DAYS * 86400, **kw)


def clear_session(response: Response) -> None:
    response.delete_cookie(ACCESS, path="/")
    response.delete_cookie(REFRESH, path="/")


def current_person(
    request: Request, response: Response, accounts: Accounts | None
) -> Person | None:
    """Who is signed in, or None. When the person has session cookies but Supabase Auth
    cannot be reached, request.state.history_down is set so the page can say so."""
    if accounts is None:
        return None
    access, refresh = request.cookies.get(ACCESS), request.cookies.get(REFRESH)
    try:
        who = accounts.auth.user(access) if access else None
        if who is None and refresh:
            s = accounts.auth.refresh(refresh)
            set_session(response, s, accounts.secure)
            access, who = s.access_token, (s.user_id, s.email)
    except AuthError as e:
        if e.expired:
            clear_session(response)
        else:
            log.warning("sign-in check failed; answering without history: %s", e)
            request.state.history_down = True
        return None
    if who is None:
        return None
    return Person(who[0], who[1], accounts.store_for(who[0], access))


async def signed_in(request: Request, accounts: Accounts | None) -> tuple[Person | None, Response]:
    """current_person for a route, and the holder of any refreshed cookies: looked up once
    per request (one Supabase Auth call), however many times the request asks. A guard:
    each route asks once today. The page's fragments are their own requests and ask again
    (checking the token here would need Supabase's signing keys, which the app lacks)."""
    seen = getattr(request.state, "signed_in", None)
    if seen is not None:
        return seen
    holder = HTMLResponse("")
    person = await run_in_threadpool(current_person, request, holder, accounts)
    request.state.signed_in = (person, holder)
    return person, holder


def finish_delete(accounts: Accounts, user_id: str) -> bool:
    """A retried delete whose session no longer resolves: if Supabase confirms the account
    is gone, sweep its photo folder again (a straggler may have landed) and report True.
    A lookup that fails raises (fail closed); an account that still exists is False."""
    if accounts.delete_folder is None:
        raise AuthError("Account delete is not set up on this server.")
    if accounts.auth.user_exists(user_id):
        return False
    accounts.delete_folder(user_id)
    return True


def delete_account(accounts: Accounts, user_id: str) -> None:
    """Sweep photos, delete the sign-in (rows cascade), confirm it is gone, sweep again
    (a late upload between the two is then refused by account_exists()). Fails closed."""
    if accounts.delete_folder is None:
        raise AuthError("Account delete is not set up on this server.")
    accounts.delete_folder(user_id)
    accounts.auth.delete_user(user_id)
    if accounts.auth.user_exists(user_id):
        raise AuthError("Could not delete your account. Nothing was lost; try again.")
    accounts.delete_folder(user_id)
