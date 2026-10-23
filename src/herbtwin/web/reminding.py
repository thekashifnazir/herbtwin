"""The reminder box under a signed-in answer (spec section 7): offered only when the
answer's main action has a check window, ticked when a reminder is stored for it."""

from __future__ import annotations

from dataclasses import dataclass

from herbtwin.history import StoredAnswer
from herbtwin.reminders import Reminder, schedule
from herbtwin.web.accounts import Person


@dataclass(frozen=True)
class ReminderBox:
    on: bool  # ticked: a reminder is waiting to go
    sent: bool = False  # the one email for this answer went: no box, a line instead


def _planned(person: Person, answer_id: str) -> Reminder | None:
    stored = person.store.get_answer(answer_id)
    return _plan_of(person, stored) if stored is not None else None


def _plan_of(person: Person, stored: StoredAnswer) -> Reminder | None:
    names = {p.id: p.name for p in person.store.list_plants()}
    name = names.get(stored.plant_id)
    return schedule(stored, name) if name else None


def box_for(person: Person | None, answer_id: str, secret: str | None) -> ReminderBox | None:
    """The box for this answer, or None when none is offered. Raises HistoryError."""
    if person is None or not secret:
        return None
    return box_of(person, answer_id, person.store.get_answer(answer_id), secret)


def box_of(
    person: Person | None, answer_id: str, stored: StoredAnswer | None, secret: str | None
) -> ReminderBox | None:
    """box_for an answer already read (None: not stored). Raises HistoryError."""
    if person is None or stored is None or not secret or _plan_of(person, stored) is None:
        return None
    r = person.store.get_reminder(answer_id)
    if r is not None and r.sent_at is not None:
        return ReminderBox(on=False, sent=True)
    return ReminderBox(on=r is not None and r.off_at is None)


def set_box(person: Person, answer_id: str, on: bool) -> bool:
    """Tick or untick; False when this answer offers no box. One email per answer: a sent
    reminder is never replaced or removed. Raises HistoryError."""
    planned = _planned(person, answer_id)
    if planned is None:
        return False
    r = person.store.get_reminder(answer_id)
    if r is not None and r.sent_at is not None:
        return True
    if r is not None and (r.off_at is not None or not on):
        person.store.set_reminder(answer_id, None)  # off (unsubscribed, too late): start again
    if on:
        person.store.set_reminder(answer_id, planned)
    return True


def replan(person: Person, answer_id: str) -> None:
    """After a refine changed the answer: move a waiting reminder to the new main action's
    window, or remove it when that action has none. Raises HistoryError."""
    r = person.store.get_reminder(answer_id)
    if r is None or r.sent_at is not None or r.off_at is not None:
        return
    person.store.set_reminder(answer_id, _planned(person, answer_id))
