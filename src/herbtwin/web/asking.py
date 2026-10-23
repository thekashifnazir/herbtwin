"""The chat's reply as it comes, for the page's waiting line (23 Oct, Kash on a phone walk
of the live site: "Same for loading when we ask questions, should be waiting text"). One
JSON object per line: a step as it starts ({"step": "search", "by": "Tavily"}), then the
reply as the plain API gives it, or {"detail", "status"} when it is refused. A blank line
every 10 s keeps a quiet wait open; past 270 s it gives up and says so. The page asks for this with
`Accept: application/x-ndjson`; any other caller gets the one JSON body, as before."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from herbtwin.chat import OnStep

log = logging.getLogger(__name__)

STREAM = "application/x-ndjson"
KEEPALIVE_S = 10.0
SORRY = "Something went wrong. Try again."
# Cloud Run ends a request at 300 s and cuts the stream mid-reply, so the page gives up a
# little before that and says so, as the photo wait does (progress.READ_DEADLINE_S)
DEADLINE_S = 270.0
TOO_LONG = "The answer took too long. Try asking again."

Work = Callable[[OnStep], dict]  # hears each step, returns the reply's body


def _line(said: dict) -> str:
    return json.dumps(said, ensure_ascii=False) + "\n"


async def lines(
    work: Work, keepalive_s: float = KEEPALIVE_S, deadline_s: float = DEADLINE_S
) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + deadline_s
    events: asyncio.Queue[dict] = asyncio.Queue()
    said: set[tuple[str, str | None]] = set()

    def on_step(step: str, by: str | None) -> None:
        if (step, by) in said:  # a second search says nothing new
            return
        said.add((step, by))
        try:
            loop.call_soon_threadsafe(events.put_nowait, {"step": step, "by": by})
        except RuntimeError:  # the page's loop is gone (tab closed at shutdown)
            log.info("chat step dropped after the page closed: %s", step)

    # in this request's context, so its traces count as this request's (D64)
    done = asyncio.ensure_future(run_in_threadpool(work, on_step))
    while True:
        left = deadline - loop.time()
        if left <= 0:
            log.warning("chat reply passed %.0f s; telling the page", deadline_s)
            yield _line({"detail": TOO_LONG, "status": 504})
            return
        get = asyncio.ensure_future(events.get())
        finished, _ = await asyncio.wait(
            {get, done}, timeout=min(keepalive_s, left), return_when=asyncio.FIRST_COMPLETED
        )
        if get in finished:
            yield _line(get.result())
            continue
        get.cancel()
        if done in finished:
            break
        yield "\n"
    while not events.empty():
        yield _line(events.get_nowait())
    try:
        yield _line(done.result())
    except HTTPException as e:
        yield _line({"detail": e.detail, "status": e.status_code})
    except Exception:  # noqa: BLE001 - shown as a plain line; the real error is logged
        log.exception("chat reply failed")
        yield _line({"detail": SORRY, "status": 500})


def chat_stream(work: Work) -> StreamingResponse:
    return StreamingResponse(
        lines(work),
        media_type=STREAM,
        # no-transform: a proxy must not buffer or recompress the stream
        headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"},
    )
