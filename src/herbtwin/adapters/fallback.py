"""A backup photo model. On 13 Oct GLM-5.3-Flash stopped answering on Token Factory while
every other model there was fine; a second model that reads the photo when the first fails
keeps the site answering through an outage like that."""

from __future__ import annotations

import copy
import logging
import time
from collections.abc import Callable

from herbtwin.adapters.base import AdapterError, ModelAdapter, TokenOverrun

log = logging.getLogger(__name__)

COOL_OFF_S = 300.0  # after a failure, the backup goes first for this long
MAX_COOL_OFF_S = 3600.0  # each failure in a row triples the skip, up to an hour


class FallbackAdapter(ModelAdapter):
    """Asks `first`; if it raises AdapterError (timeout, outage, cut-off reply), asks
    `backup` once. After a failure the backup goes first for `cool_off_s`, so a silent
    model costs its timeout once, not on every repair and upload. A model that fails again
    when retried is skipped three times as long each time, up to `max_cool_off_s` (on
    13 Oct GLM stayed down all day and every upload after a quiet 5 minutes waited 90 s);
    one good answer resets it. Each call is traced under the model that made it."""

    name = "fallback"
    # set on the per-run copy bind() makes when the backup answered, so a page can say so
    # (the spot page asks "pot or ground?": Gemma misread pots on 13 Oct; DeepSeek's spot
    # read is untested, so the page still asks); never on the shared one
    used_backup = False
    # set on the per-run copy while the backup reads the same photo alongside the first
    # (backup_to_race): a first model that then fails leaves the reading to that call
    # rather than asking the backup a second time
    racing = False

    def __init__(
        self,
        first: ModelAdapter,
        backup: ModelAdapter,
        *,
        cool_off_s: float = COOL_OFF_S,
        max_cool_off_s: float = MAX_COOL_OFF_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.first = first
        self.backup = backup
        self.cool_off_s = cool_off_s
        self.max_cool_off_s = max_cool_off_s
        self.clock = clock
        # a dict, so the shallow copies bind() makes per run share one outage clock and
        # one count of failures in a row
        self._first_down_until = {"t": float("-inf"), "fails": 0}

    def _run(self, call: Callable[[ModelAdapter], str]) -> str:
        if self.clock() < self._first_down_until["t"]:
            self.used_backup = True
            return call(self._as_me(self.backup))
        try:
            answer = call(self._as_me(self.first))
        except AdapterError as e:
            down = self._first_down_until
            if isinstance(e, TokenOverrun):
                skip = self.cool_off_s  # a long reply, not an outage: never grows the skip
            else:
                down["fails"] += 1
                skip = min(self.cool_off_s * 3 ** (down["fails"] - 1), self.max_cool_off_s)
            down["t"] = self.clock() + skip
            log.warning(
                "%s failed (%s); reading with %s for the next %.0f s",
                _model(self.first),
                e,
                _model(self.backup),
                skip,
            )
            if self.racing:
                raise
            self.used_backup = True
            return call(self._as_me(self.backup))
        self._first_down_until["fails"] = 0  # it answered: the next outage starts short
        return answer

    def backup_for_unusable(self) -> ModelAdapter | None:
        """The backup, for a reply the first model sent that is still unusable after its
        repair (18 Oct, Kash's pots photo: GLM sent no JSON twice and the page said it could
        not read the photo). At most once a run, and never once the backup has read it. It
        starts no cool-off: a bad reply is about the photo, not an outage."""
        if self.used_backup:
            return None
        log.warning(
            "%s sent no usable reply; reading with %s", _model(self.first), _model(self.backup)
        )
        self.used_backup = True
        return self._as_me(self.backup)

    def backup_to_race(self) -> ModelAdapter | None:
        """The backup, to read the photo alongside a first model that is slow to answer
        (21 Oct: GLM took over 35 s on one read in twenty, and the backup only started
        after it, so the slowest answers took 70-90 s). None when the backup already reads
        this run's photo, or goes first anyway in a cool-off. Like backup_for_unusable it
        starts no cool-off: a slow reply is not an outage."""
        if self.used_backup or self.clock() < self._first_down_until["t"]:
            return None
        log.info("%s is slow; racing %s", _model(self.first), _model(self.backup))
        self.used_backup = self.racing = True
        return self._as_me(self.backup)

    def _as_me(self, adapter: ModelAdapter) -> ModelAdapter:
        """A copy carrying this adapter's stage and tracer (set per run by bind())."""
        inner = copy.copy(adapter)
        inner.stage, inner.on_call = self.stage, self.on_call
        return inner

    def complete(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        return self._run(lambda a: a.complete(system, user, max_tokens=max_tokens))

    def complete_json(
        self,
        system: str,
        user: str,
        schema: dict,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> str:
        return self._run(
            lambda a: a.complete_json(
                system, user, schema, max_tokens=max_tokens, temperature=temperature
            )
        )

    def complete_with_image(
        self,
        system: str,
        user: str,
        image: bytes,
        mime: str,
        schema: dict | None = None,
        *,
        max_tokens: int = 1024,
    ) -> str:
        return self._run(
            lambda a: a.complete_with_image(
                system, user, image, mime, schema, max_tokens=max_tokens
            )
        )

    def complete_with_images(
        self,
        system: str,
        user: str,
        images: list[tuple[bytes, str]],
        schema: dict | None = None,
        *,
        max_tokens: int = 1024,
    ) -> str:
        return self._run(
            lambda a: a.complete_with_images(system, user, images, schema, max_tokens=max_tokens)
        )


def _model(adapter: ModelAdapter) -> str:
    return getattr(adapter, "model", adapter.name)
