"""Optional accounts for the web layer (spec section 5): on only when Supabase settings
exist, tokens in httpOnly cookies, refreshed when the access token is refused."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Request, Response

from herbtwin.auth import AuthError, Session, SupabaseAuth
from herbtwin.config import Settings
from herbtwin.history import HistoryStore

log = logging.getLogger(__name__)
ACCESS, REFRESH = "herbtwin_at", "herbtwin_rt"
REFRESH_DAYS = 30


@dataclass
class Accounts:
    auth: SupabaseAuth  # or tests' FakeAuth with the same methods
    store_for: Callable[[str, str], HistoryStore]  # (user_id, access_token) -> store
    secure: bool
    delete_folder: Callable[[str], int] | None


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
    return Accounts(
        auth=SupabaseAuth(url, key, secret),
        store_for=lambda uid, token: SupabaseHistoryStore(url, key, token, uid),
        secure=settings.site_url.startswith("https://"),
        delete_folder=(lambda uid: delete_folder(url, secret, uid)) if secret else None,
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
