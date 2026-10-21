"""The site nav's facts: who is asking, whether accounts are on, and
which page this is. `_nav.html` exports `site_nav` as this function, so every page that
calls it, in its own `{% block nav %}` or through base.html's default, gets the facts it
didn't pass from the request in its template context."""

from __future__ import annotations

from jinja2 import pass_context
from jinja2.runtime import Context
from markupsafe import Markup

from herbtwin.web.accounts import ACCESS, REFRESH

UNSET = object()
# the two jobs and sign-in, by address: the page a visitor is on is marked
HERE = {"/": "check", "/plants": "plants", "/auth/sign-in": "sign-in"}


def has_session(request) -> bool:
    """A cheap hint that this browser is signed in: its session cookies are there. Only for
    pages that never look the person up (privacy, sign-in, messages, judges). It can be
    wrong (an expired or revoked session), and that is all right: it only picks between
    "Sign in" and "My plants" + "Sign out", and /plants itself checks the session properly,
    sending a stale one to sign in."""
    return bool(
        request is not None and (request.cookies.get(ACCESS) or request.cookies.get(REFRESH))
    )


@pass_context
def site_nav(ctx: Context | None = None, person=UNSET, accounts=UNSET, here: str = "") -> Markup:
    """The header nav. `person` is the signed-in person (or True/False) where the page knows;
    left out, the page's own `person` or `signed_in` is used, else the session hint."""
    request = ctx.get("request") if ctx is not None else None
    state = request.app.state if request is not None else None
    if accounts is UNSET:
        accounts = state is None or getattr(state, "accounts", None) is not None
    if person is UNSET:
        if ctx is not None and "person" in ctx:
            person = ctx["person"]
        elif ctx is not None and "signed_in" in ctx:
            person = ctx["signed_in"]
        else:
            person = has_session(request)
    if not here and request is not None and request.method == "GET":
        # a POST's page (a message after a form) is not the page at that address
        here = HERE.get(request.url.path, "")
    links = ctx.environment if ctx is not None else _env()
    return links.get_template("_nav.html").module.links(
        signed_in=bool(person) and bool(accounts), accounts=accounts, here=here
    )


def _env():
    from herbtwin.web.app import TEMPLATES  # called from Python only (tests), never a page

    return TEMPLATES.env
