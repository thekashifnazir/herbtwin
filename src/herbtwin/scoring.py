"""Scoring earlier advice on the next photo (C2, spec section 4, D48, D54): what each main
action should change, which earlier visit is due a check, when it cannot be compared, the
result, and the line shown in history and to the advisor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from herbtwin.history import AdviceScore, StoredAnswer, utc
from herbtwin.schemas import (
    Answer,
    Comparison,
    DidIt,
    LightNow,
    Observation,
    Prediction,
    ScoreResult,
    Signal,
)

# EXIF wall time is stored as if UTC while an undated photo carries real UTC, so a pair
# of one of each is off by the UK's UTC offset; the window edges allow for it
SLACK_DAYS = 2 / 24
GATE_PATH = Path(__file__).resolve().parents[2] / "data" / "scoring" / "gate.json"


@dataclass(frozen=True)
class Rule:
    signal: Signal
    window_days: tuple[int, int]
    less_sure: bool
    source: str


RULES: dict[str, Rule] = {
    "water": Rule(
        "posture",
        (1, 7),
        False,
        "watering lifts a wilted plant within hours to a day (garden soak, 2 Oct: the "
        "parsley stood up within four hours); probe c",
    ),
    "dont_water": Rule(
        "posture",
        (1, 7),
        False,
        "holding off water on moist soil should not bring on droop within a week (spec section 4)",
    ),
    "leave_normal": Rule(
        "tissue",
        (3, 21),
        False,
        "a plant left alone in its normal state should not gain dead or brown parts "
        "(spec section 4, D48)",
    ),
    "shelter": Rule(
        "tissue",
        (3, 21),
        False,
        "shelter from cold or wet should stop new damage (spec section 4)",
    ),
    "treat_or_remove": Rule(
        "tissue",
        (3, 21),
        True,
        "treating or removing the affected part should stop it spreading (spec section 4)",
    ),
    "prune": Rule(
        "tissue",
        (3, 21),
        True,
        "cutting back damaged growth should leave no more dead parts (spec section 4)",
    ),
    "isolate": Rule(
        "tissue",
        (3, 21),
        True,
        "keeping a plant apart should stop a problem spreading on it (spec section 4)",
    ),
    "move_light": Rule(
        "colour",
        (7, 21),
        True,
        "better light should keep leaves green or green them again within weeks (spec section 4)",
    ),
    "feed": Rule(
        "colour",
        (7, 21),
        True,
        "feeding should keep leaves green or green them again within weeks (spec section 4)",
    ),
}

ACTION_TEXT = {
    "water": "water",
    "dont_water": "hold off watering",
    "leave_normal": "leave it",
    "shelter": "shelter it",
    "treat_or_remove": "treat it",
    "prune": "cut it back",
    "isolate": "keep it apart",
    "move_light": "move it to better light",
    "feed": "feed it",
}
ASK_TEXT = {
    "water": "watering it",
    "dont_water": "holding off watering",
    "leave_normal": "leaving it as it is",
    "shelter": "sheltering it",
    "treat_or_remove": "treating it",
    "prune": "cutting it back",
    "isolate": "keeping it apart",
    "move_light": "moving it to better light",
    "feed": "feeding it",
}
DID_TEXT = {
    "yes": "you did it",
    "partly": "you partly did it",
    "no": "you didn't",
    "skip": "you skipped the question",
}
SIGNAL_TEXT = {"posture": "droop", "tissue": "dead or brown parts", "colour": "leaf colour"}
CHANGE_TEXT = {
    "posture": {"less": "less droop", "same": "no clear change in droop", "more": "more droop"},
    "tissue": {
        "less": "fewer dead or brown parts",
        "same": "no clear change in dead or brown parts",
        "more": "more dead or brown parts",
    },
    "colour": {
        "less": "greener leaves",
        "same": "no clear change in leaf colour",
        "more": "paler leaves",
    },
}
RESULT_OF = {"less": "improved", "same": "no_clear_change", "more": "worse"}


class Gate(BaseModel):
    """Which signals passed the step-0 check (scripts/check_scoring.py). A signal that has
    not passed is stored as "not scored yet" and no comparison is made for it."""

    prompt_version: str
    signals: dict[str, Literal["passed", "failed", "untested"]]
    note: str = ""


@cache
def load_gate() -> Gate:
    return Gate.model_validate_json(GATE_PATH.read_text())


def predict(answer: Answer, obs: Observation | None) -> Prediction | None:
    """The prediction for the answer's main action, or None when it is not scored."""
    if not answer.do or obs is None:
        return None
    action = answer.do[0].action
    rule = RULES.get(action)
    if rule is None:
        return None
    before = {"posture": obs.water_stress, "tissue": obs.decline}.get(rule.signal)
    expected = "less" if action == "water" and obs.water_stress > 0 else "not_more"
    return Prediction(
        action=action,
        signal=rule.signal,
        expected=expected,
        window_days=rule.window_days,
        less_sure=rule.less_sure,
        before=before,
        source=rule.source,
    )


def _days(earlier: datetime, later: datetime) -> float:
    return (utc(later) - utc(earlier)).total_seconds() / 86400


def earlier_visit(past: list[StoredAnswer], later: StoredAnswer) -> StoredAnswer | None:
    """The visit just before this photo, when its main action is due a check now. Only
    the latest earlier advice is checked: the advice before it was superseded."""
    before = [a for a in past if a.id != later.id and utc(a.taken_at) < utc(later.taken_at)]
    if not before:
        return None
    last = max(before, key=lambda a: utc(a.taken_at))
    p = last.answer.prediction if last.answer else None
    if p is None:
        return None
    lo, hi = p.window_days
    days = _days(last.taken_at, later.taken_at)
    return last if lo - SLACK_DAYS <= days <= hi + SLACK_DAYS else None


def light_mismatch(a: LightNow | None, b: LightNow | None) -> bool:
    """One photo in direct sun, the other in shade: harsh sun causes passing droop."""
    if a is None or b is None:
        return False
    return (a == "direct_sun") != (b == "direct_sun")


def _species(a: StoredAnswer) -> str:
    return a.observation.species[0].name.strip().casefold() if a.observation.species else ""


def _cannot_compare(earlier: StoredAnswer, later: StoredAnswer) -> str | None:
    if "poor" in (earlier.observation.photo_quality, later.observation.photo_quality):
        return "one of the photos was poor"
    if _species(earlier) != _species(later):
        return "the plant was named differently in the two photos"
    le, ll = earlier.evidence.light, later.evidence.light
    if light_mismatch(le.now if le else None, ll.now if ll else None):
        return "one photo was in direct sun and the other in shade"
    return None


def plan_score(
    earlier: StoredAnswer, later: StoredAnswer, did_it: DidIt, gate: Gate
) -> tuple[ScoreResult | None, str | None]:
    """The result when no comparison is needed (with its reason), else (None, None): then
    the comparison runs and result_of decides."""
    if did_it == "skip":
        return "cant_tell", "you skipped the question"
    if gate.signals.get(earlier.answer.prediction.signal) != "passed":
        return "not_scored_yet", None
    reason = _cannot_compare(earlier, later)
    if reason:
        return ("not_done" if did_it == "no" else "cant_tell"), reason
    return None, None


def result_of(did_it: DidIt, comparison: Comparison) -> tuple[ScoreResult, str | None]:
    """The result from the comparison. "No" keeps the comparison but gives no verdict on
    the advice (useful later as a comparison)."""
    if did_it == "no":
        return "not_done", None
    if comparison.verdict == "cant_tell":
        return "cant_tell", comparison.reason
    return RESULT_OF[comparison.verdict], None


def ask_text(earlier: StoredAnswer) -> str:
    when = f"{earlier.taken_at.day} {earlier.taken_at:%b}"
    return f"On {when} we suggested {ASK_TEXT[earlier.answer.prediction.action]}. Did you do it?"


def score_line(s: AdviceScore) -> str:
    """One line for the history and the advisor: "Last advice: water (you did it).
    Since then: less droop." """
    head = f"Last advice: {ACTION_TEXT[s.prediction.action]} ({DID_TEXT[s.did_it]})."
    if s.did_it in ("no", "skip"):
        return head
    if s.result == "not_scored_yet":
        return f"{head} We can't check {SIGNAL_TEXT[s.prediction.signal]} from photos reliably yet."
    if s.result == "cant_tell":
        return f"{head} Since then: couldn't tell from these two photos ({s.reason})."
    change = CHANGE_TEXT[s.prediction.signal][s.comparison.verdict]
    return f"{head} Since then: {change}."


def score_lines(scores: list[AdviceScore]) -> dict[str, str]:
    """Each score's line, keyed by the answer it was asked under (the later one)."""
    return {s.later_answer_id: score_line(s) for s in scores}
