"""HEAD as GET without the body. FastAPI's GET routes don't answer HEAD, so a HEAD request
(uptime and link checkers) met the 405 handler, which sends a form address back to its page:
`curl -I /about` got 303 to / (22 Oct site walk). Every page answers GET without changing
anything, so a HEAD is that GET with its headers and no body."""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class HeadAsGet:
    """Pure ASGI: the app sees a GET, the client gets its status and headers only."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "HEAD":
            await self.app(scope, receive, send)
            return

        async def headers_only(message: Message) -> None:
            if message["type"] == "http.response.body":
                if message.get("more_body"):
                    return  # the rest of a streamed body: nothing is sent for HEAD
                message = {"type": "http.response.body", "body": b"", "more_body": False}
            await send(message)

        await self.app({**scope, "method": "GET"}, receive, headers_only)
