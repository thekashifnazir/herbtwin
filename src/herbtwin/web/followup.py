"""The chat under an answer, signed in or out (spec section 6). Loads the answer as it
stands (after any refine), the plant's other visits and the chat so far; runs one turn;
keeps both messages. Signed in: the person's store (the cache when the store has no row);
signed out: the 1-hour cache. Keeping the chat never blocks the reply."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from herbtwin.answer_cache import AnswerCache
from herbtwin.chat import MAX_MESSAGES, ChatReply, OnStep, reply, shown
from herbtwin.history import ChatMessage, HistoryError, StoredAnswer
from herbtwin.pipeline import Deps, History, history_for, reading_from
from herbtwin.schemas import AnalysisRecord
from herbtwin.stages import trusted_page
from herbtwin.tracing import StageTracer, bind
from herbtwin.voice import line_for
from herbtwin.web.accounts import Person
from herbtwin.web.remember import HISTORY_DOWN

log = logging.getLogger(__name__)


class Expired(Exception):
    """Neither the store nor the cache holds this answer for this person."""


class AtLimit(Exception):
    """The person has used all their messages on this answer."""


@dataclass(frozen=True)
class Turn:
    reply: ChatReply
    left: int  # messages the person has left on this answer
    note: str | None


def _record(stored: StoredAnswer) -> AnalysisRecord:
    rec = reading_from(stored).rec
    rec.answer, rec.told = stored.answer, stored.told
    # the trusted page decided again against the kept answer's own action (the quote is
    # never stored: a refine can change the action)
    if rec.trusted is not None and stored.answer is not None and stored.answer.do:
        state = trusted_page.plant_state(rec, stored.answer.do[0].action, stored.told)
        rec.trusted = trusted_page.quoted(rec.trusted, state)
    return rec


def _history(person: Person, stored: StoredAnswer) -> History | None:
    past = [a for a in person.store.answers_for(stored.plant_id) if a.id != stored.id]
    scores = person.store.scores_for(stored.plant_id)
    return (
        history_for(past, stored.observation, stored.taken_at, scores, stored.evidence.problem)
        if past
        else None
    )


def _stored(person: Person | None, answer_id: str) -> StoredAnswer | None:
    if person is None:
        return None
    try:
        return person.store.get_answer(answer_id)
    except HistoryError:
        log.exception("could not read the stored answer")
        return None


def answer_for(person: Person | None, answer_id: str, cache: AnswerCache) -> AnalysisRecord:
    """The answer as it stands, for its owner only. Raises Expired when it is gone."""
    stored = _stored(person, answer_id)
    if stored is not None:
        return _record(stored)
    entry = cache.get_for(answer_id, person.user_id if person else None)
    if entry is None:
        raise Expired(answer_id)
    return entry.latest


def chat_so_far(person: Person | None, answer_id: str, cache: AnswerCache) -> list[ChatMessage]:
    """The chat to show under a page, best effort: empty when it cannot be read. A reply
    kept before a text tool call was caught shows as the lookup that failed (chat.shown)."""
    stored = _stored(person, answer_id)
    if stored is not None:
        try:
            said = person.store.chat_for(stored.id)
        except HistoryError:
            log.exception("could not read the chat")
            return []
    else:
        entry = cache.get_for(answer_id, person.user_id if person else None)
        said = list(entry.chat) if entry else []
    return [m.model_copy(update={"content": shown(m.content, m.role)}) for m in said]


def _nothing() -> None:
    return None


def chat_turn(
    deps: Deps,
    person: Person | None,
    answer_id: str,
    message: str,
    cache: AnswerCache,
    before_model: Callable[[], None] = _nothing,
    on_step: OnStep | None = None,
) -> Turn:
    """One chat message and its reply. `before_model` runs only once the message will
    reach the model (the answer found, the chat under its limit); it may raise to refuse.
    `on_step` hears a search as it starts, for the page's waiting line."""
    stored = _stored(person, answer_id)
    note: str | None = None
    history: History | None = None
    if stored is not None:
        rec = _record(stored)
        try:
            past = person.store.chat_for(stored.id)
            history = _history(person, stored)
        except HistoryError:
            log.exception("could not read the chat or the plant's history")
            past, note = [], HISTORY_DOWN
    else:
        entry = cache.get_for(answer_id, person.user_id if person else None)
        if entry is None:
            raise Expired(answer_id)
        rec, past = entry.latest, list(entry.chat)
    asked = sum(1 for m in past if m.role == "user")
    if asked >= MAX_MESSAGES:
        raise AtLimit(answer_id)
    before_model()
    model = deps.chat_adapter or deps.advise_adapter
    adapter = bind(model, "chat", StageTracer(deps.trace_store, rec.record_id))
    got = reply(
        adapter,
        rec,
        message=message,
        past=past,
        history=history,
        search=deps.search,
        on_step=on_step,
    )
    mine = ChatMessage(role="user", content=message)
    theirs = ChatMessage(role="assistant", content=got.text, tools=got.tools or None)
    if stored is not None:
        try:
            person.store.add_chat(stored.id, mine)
            person.store.add_chat(stored.id, theirs)
        except HistoryError:
            log.exception("could not keep the chat run=%s", rec.record_id)
            note = HISTORY_DOWN
    else:
        cache.add_chat(answer_id, mine)
        cache.add_chat(answer_id, theirs)
    return Turn(got, MAX_MESSAGES - asked - 1, note)


def voice_line(deps: Deps, rec: AnalysisRecord) -> str:
    """What the plant says aloud, written by the chat model from the answer it voices."""
    model = deps.chat_adapter or deps.advise_adapter
    return line_for(bind(model, "voice", StageTracer(deps.trace_store, rec.record_id)), rec)
