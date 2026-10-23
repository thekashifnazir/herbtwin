"""The "did you do it?" check under an answer (C2, spec section 4): which earlier advice
is due a check, the person's reply, the side-by-side comparison and the stored score."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime

from herbtwin import scoring
from herbtwin.history import AdviceScore, HistoryError, StoredAnswer
from herbtwin.pipeline import Deps
from herbtwin.schemas import Comparison, DidIt
from herbtwin.side_by_side import Side, compare_pair
from herbtwin.tracing import StageTracer, bind
from herbtwin.web.accounts import Person

log = logging.getLogger(__name__)

# pairs being scored in this process: a double tap waits for the first reply instead of
# paying for a second comparison (the table's unique pair backs this across processes)
_in_flight: set[tuple[str, str]] = set()
_turn = threading.Condition()
# a comparison whose save failed, kept so a retry does not pay for the calls again
KEEP_S = 600
_kept: dict[tuple[str, str, str], tuple[float, Comparison]] = {}  # (earlier, later, signal)
_kept_lock = threading.Lock()  # other pairs add and drop entries while one sweeps


def _kept_comparison(key: tuple[str, str, str]) -> Comparison | None:
    now = time.monotonic()
    with _kept_lock:
        for k in [k for k, (at, _) in _kept.items() if now - at > KEEP_S]:
            _kept.pop(k, None)
        got = _kept.get(key)
    return got[1] if got else None


def _keep(key: tuple[str, str, str], comparison: Comparison | None) -> None:
    with _kept_lock:
        if comparison is None:
            _kept.pop(key, None)
        else:
            _kept[key] = (time.monotonic(), comparison)


@dataclass(frozen=True)
class Checkup:
    ask: str | None  # "On 2 Oct we suggested watering it. Did you do it?"
    line: str | None  # the result line, once answered


def _pair(person: Person, answer_id: str):
    """(earlier, later, its score or None) when an earlier visit is due a check."""
    later = person.store.get_answer(answer_id)
    return _pair_of(person, later) if later is not None else None


def _pair_of(person: Person, later: StoredAnswer):
    """_pair for an answer already read."""
    earlier = scoring.earlier_visit(person.store.answers_for(later.plant_id), later)
    if earlier is None:
        return None
    done = next(
        (
            s
            for s in person.store.scores_for(later.plant_id)
            if (s.earlier_answer_id, s.later_answer_id) == (earlier.id, later.id)
        ),
        None,
    )
    return earlier, later, done


def checkup_for(person: Person | None, answer_id: str) -> Checkup | None:
    """The ask, or the stored result, for this answer. None when nothing is due or
    history cannot be read: the answer is shown either way."""
    if person is None:
        return None
    try:
        later = person.store.get_answer(answer_id)
    except HistoryError:
        log.exception("could not read the checkup")
        return None
    return checkup_of(person, later)


def checkup_of(person: Person | None, later: StoredAnswer | None) -> Checkup | None:
    """checkup_for an answer already read (None: not stored, or it could not be read)."""
    if person is None or later is None:
        return None
    try:
        got = _pair_of(person, later)
    except HistoryError:
        log.exception("could not read the checkup")
        return None
    if got is None:
        return None
    earlier, _, done = got
    if done is not None:
        return Checkup(None, scoring.score_line(done))
    return Checkup(scoring.ask_text(earlier), None)


def _side(person: Person, a: StoredAnswer) -> Side | None:
    try:
        image = person.store.get_photo(a.photo_path) if a.photo_path else None
    except HistoryError:
        log.exception("could not read a stored photo")
        image = None
    if image is None:
        return None
    light = a.evidence.light
    if light is not None:
        return Side(image, light.local_time, light.now)
    exif = a.evidence.taken_at_source == "exif"
    return Side(image, a.taken_at.replace(tzinfo=None) if exif else None, None)


def record(
    deps: Deps, person: Person, answer_id: str, did_it: DidIt, now: datetime
) -> Checkup | None:
    """Store the reply and its score. The comparison runs only when it can count; a
    second reply for the same pair keeps the first, and one arriving while the first is
    still being scored waits for it. HistoryError reaches the route."""
    got = _pair(person, answer_id)
    if got is None:
        return None
    key = (got[0].id, got[1].id)
    with _turn:
        while key in _in_flight:
            _turn.wait()
        _in_flight.add(key)
    try:
        got = _pair(person, answer_id)  # a reply that held the pair may have stored it
        if got is None:
            return None
        return _score(deps, person, answer_id, did_it, now, *got)
    finally:
        with _turn:
            _in_flight.discard(key)
            _turn.notify_all()


def _score(
    deps: Deps,
    person: Person,
    answer_id: str,
    did_it: DidIt,
    now: datetime,
    earlier: StoredAnswer,
    later: StoredAnswer,
    done: AdviceScore | None,
) -> Checkup:
    if done is not None:
        return Checkup(None, scoring.score_line(done))
    p = earlier.answer.prediction
    result, reason = scoring.plan_score(earlier, later, did_it, scoring.load_gate())
    comparison = None
    if result is None:
        a, b = _side(person, earlier), _side(person, later)
        if a is None or b is None:
            result, reason = ("not_done" if did_it == "no" else "cant_tell"), "a photo is missing"
        else:
            key = (earlier.id, later.id, p.signal)  # a refined earlier answer may change it
            comparison = _kept_comparison(key)
            if comparison is None:
                adapter = bind(
                    deps.observe_adapter, "compare", StageTracer(deps.trace_store, answer_id)
                )
                comparison = compare_pair(
                    adapter, a, b, p.signal, model=deps.settings.observe_model, workers=deps.workers
                )
                _keep(key, comparison)
            result, reason = scoring.result_of(did_it, comparison)
    score = AdviceScore(
        plant_id=later.plant_id,
        earlier_answer_id=earlier.id,
        later_answer_id=later.id,
        prediction=p,
        did_it=did_it,
        result=result,
        reason=reason,
        comparison=comparison,
        scored_at=now,
    )
    person.store.add_score(score)
    _keep((earlier.id, later.id, p.signal), None)
    if deps.traces is not None:  # which advice worked, on the earlier read's trace (D64)
        deps.traces.feedback(earlier.id, result, reason)
    return Checkup(None, scoring.score_line(score))
