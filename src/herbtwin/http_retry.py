"""One GET with one retry, for the free public data APIs (Open-Meteo) a busy hour can knock
over: a 503 "The service is overloaded" should not cost an answer its 2-week weather.

One retry, never more. A 429, a 5xx or a dropped connection waits a short jittered pause
(or the server's Retry-After) and tries once more; the pause is never more than
MAX_RETRY_WAIT_S, and the retry gets at most RETRY_TIMEOUT_S of its own, so the most it
adds is 3 s + 8 s on top of the first try. A timeout is not retried (a second wait
doubles a stall the page is already waiting on), nor is any other 4xx (the request itself
is wrong and will be wrong again). Same policy as the model calls in
adapters/openai_compat.py."""

from __future__ import annotations

import logging
import math
import random
import time
from email.utils import parsedate_to_datetime

import httpx

log = logging.getLogger(__name__)

RETRY_JITTER_S = (0.5, 1.5)
MAX_RETRY_WAIT_S = 3.0
RETRY_TIMEOUT_S = 8.0  # the retry's own budget, never more than the client's
_sleep = time.sleep  # a seam for tests


def _retry_after(resp: httpx.Response) -> float | None:
    """The server's Retry-After in seconds (delta-seconds or a date); None when missing or
    not a finite number."""
    value = resp.headers.get("retry-after")
    if not value:
        return None
    try:
        try:
            after = float(value)
        except ValueError:
            after = parsedate_to_datetime(value).timestamp() - time.time()
    except (TypeError, ValueError, OverflowError):
        return None
    return max(after, 0.0) if math.isfinite(after) else None


def _worth_retry(resp: httpx.Response) -> bool:
    return resp.status_code == 429 or resp.status_code >= 500


def _wait_for(resp: httpx.Response | None) -> float:
    after = _retry_after(resp) if resp is not None else None
    wait = random.uniform(*RETRY_JITTER_S) if after is None else after
    return min(wait, MAX_RETRY_WAIT_S)


def _retry_timeout(client: httpx.Client) -> httpx.Timeout:
    t = client.timeout.read
    return httpx.Timeout(RETRY_TIMEOUT_S if t is None else min(t, RETRY_TIMEOUT_S))


def get_with_one_retry(
    client: httpx.Client, url: str, *, params: dict | None = None, what: str
) -> httpx.Response:
    """GET url, retrying once on a 429, a 5xx or a dropped connection. Returns the last
    response (the caller judges its status); raises the last httpx.HTTPError when the
    request never got a response. `what` names the service in the logs (never the
    params: they carry the user's location)."""
    try:
        resp = client.get(url, params=params)
    except httpx.TimeoutException:
        raise
    except httpx.TransportError as e:
        first, resp = type(e).__name__, None
    else:
        if not _worth_retry(resp):
            return resp
        first = str(resp.status_code)
    wait = _wait_for(resp)
    log.info("%s failed (%s); retrying once in %.1f s", what, first, wait)
    _sleep(wait)
    try:
        resp = client.get(url, params=params, timeout=_retry_timeout(client))
    except httpx.HTTPError as e:
        log.warning("%s failed again on retry (%s)", what, type(e).__name__)
        raise
    if _worth_retry(resp):
        log.warning("%s failed again on retry (%s)", what, resp.status_code)
    return resp
