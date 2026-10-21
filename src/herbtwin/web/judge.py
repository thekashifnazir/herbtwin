"""The judges' code (spec D59): typed once on /judge, it sets a signed HTTP-only cookie
for 60 days that skips the photo-read caps and the budget stop. The cookie holds an HMAC
keyed by the code, never the code; wrong tries are capped at 10 a day per visitor (a right
code never uses one up: judges on one venue Wi-Fi share an IP)."""

from __future__ import annotations

import hashlib
import hmac
import threading
from datetime import date

from fastapi import Request, Response

COOKIE = "herbtwin_judge"
MAX_AGE = 60 * 86400
TRIES_A_DAY = 10
_LABEL = b"herbtwin-judge"


def judge_token(code: str) -> str:
    return hmac.new(code.encode(), _LABEL, hashlib.sha256).hexdigest()


def right_code(given: str, code: str) -> bool:
    return hmac.compare_digest(given.strip().encode(), code.encode())


def is_judge(request: Request, code: str | None) -> bool:
    if not code:
        return False
    got = request.cookies.get(COOKIE)
    return bool(got) and hmac.compare_digest(got.encode(), judge_token(code).encode())


def set_judge(response: Response, code: str, secure: bool) -> None:
    response.set_cookie(
        COOKIE,
        judge_token(code),
        max_age=MAX_AGE,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


class Attempts:
    """Tries at the code per visitor per UK day, in memory (one instance runs the site)."""

    def __init__(self, per_day: int = TRIES_A_DAY) -> None:
        self.per_day = per_day
        self._lock = threading.Lock()
        self._day: date | None = None
        self._tries: dict[str, int] = {}

    def allow(self, day: date, visitor: str, *, count: bool = True) -> bool:
        """False once this visitor has used today's tries; otherwise True, and the try is
        counted when `count` (a wrong code). A right code passes without using a try, but a
        visitor already blocked stays blocked even with the right code, so a guesser past
        the cap learns nothing from the reply."""
        with self._lock:
            if day != self._day:  # only today matters: older days are dropped
                self._day, self._tries = day, {}
            n = self._tries.get(visitor, 0)
            if n >= self.per_day:
                return False
            if count:
                self._tries[visitor] = n + 1
            return True
