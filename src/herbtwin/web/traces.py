"""Send a request's LangSmith traces before its response ends (spec section 6, D64).
Cloud Run bills CPU per request: once the last byte has gone the instance may be
throttled, and a trace still queued then may not go until the next request (or at all,
before a deploy)."""

from __future__ import annotations

import logging
from collections.abc import Callable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from herbtwin.remote_traces import Batch, RemoteTraces
from herbtwin.tracing import request_scope

log = logging.getLogger(__name__)


class FlushTraces:
    """Pure ASGI: each request gets a Batch (the tracers made while it runs carry it), and
    before the response's last body message the request waits for that batch only, at
    most FLUSH_S and not at all while LangSmith is struggling (RemoteTraces.settle). A
    request that queued nothing never waits."""

    def __init__(self, app: ASGIApp, traces: Callable[[], RemoteTraces | None]) -> None:
        self.app, self.traces = app, traces

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        traces = self.traces() if scope["type"] == "http" else None
        if traces is None:
            await self.app(scope, receive, send)
            return
        batch = Batch()

        async def settling(message: Message) -> None:
            if message["type"] == "http.response.body" and not message.get("more_body"):
                try:
                    await traces.settle(batch)
                except Exception:  # noqa: BLE001 - never costs the response
                    log.exception("trace flush failed")
            await send(message)

        with request_scope(batch):
            await self.app(scope, receive, settling)
