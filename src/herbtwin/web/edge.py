"""The edge guard (spec D63): the live site is reached only through the Cloudflare Worker,
which adds a shared secret and the visitor's IP. A request without the secret is refused;
the visitor IP header is believed only when the secret matched. With no secret configured
(local runs) the guard is off and the header is never believed."""

from __future__ import annotations

import hmac

from fastapi import Request
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

EDGE_HEADER = "x-herbtwin-edge"
VISITOR_HEADER = "x-herbtwin-visitor-ip"
OPEN_PATHS = frozenset({"/health", "/healthz"})  # Cloud Run's own checks come without the Worker


def _matches(given: str | bytes | None, secret: str | None) -> bool:
    if not secret or given is None:
        return False
    if isinstance(given, str):
        given = given.encode()
    return hmac.compare_digest(given, secret.encode())


class EdgeGuard:
    """Pure ASGI, so a refusal never touches the app (or reads a body)."""

    def __init__(self, app: ASGIApp, secret: str | None) -> None:
        self.app, self.secret = app, secret

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.secret or scope["path"] in OPEN_PATHS:
            await self.app(scope, receive, send)
            return
        given = dict(scope["headers"]).get(EDGE_HEADER.encode(), b"")
        if not _matches(given, self.secret):
            await PlainTextResponse("Forbidden", 403)(scope, receive, send)
            return
        await self.app(scope, receive, send)


def visitor_ip(request: Request, secret: str | None) -> str:
    """The visitor's address: the Worker's header when the edge secret matched, the socket
    address otherwise (a forged header sent straight to the origin is ignored)."""
    if _matches(request.headers.get(EDGE_HEADER), secret):
        forwarded = (request.headers.get(VISITOR_HEADER) or "").strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else ""
