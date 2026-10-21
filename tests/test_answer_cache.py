from datetime import UTC, datetime, timedelta

from herbtwin.answer_cache import TTL, AnswerCache
from herbtwin.history import ChatMessage
from herbtwin.pipeline import Reading
from herbtwin.schemas import AnalysisRecord
from herbtwin.species import match_species

T0 = datetime(2026, 10, 6, 9, tzinfo=UTC)


def _reading(rid):
    rec = AnalysisRecord(
        record_id=rid, taken_at=T0, observation=None, environment=None, pack=None, state=None
    )
    return Reading(
        rec=rec,
        match=match_species("unknown", "unknown"),
        top=None,
        month=10,
        season_missing=None,
        weather_missing=None,
        weather=None,
        failures=[],
    )


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now


def test_get_returns_the_entry_within_the_hour_then_expires():
    clock = Clock()
    cache = AnswerCache(clock)
    r = _reading("a" * 32)
    cache.put(r, r.rec)
    clock.now = T0 + timedelta(minutes=59)
    assert cache.get("a" * 32).reading is r
    clock.now = T0 + timedelta(minutes=61)
    assert cache.get("a" * 32) is None
    assert cache.get("nope") is None


def test_the_oldest_answer_is_dropped_beyond_the_cap():
    cache = AnswerCache(Clock(), max_entries=2)
    for rid in ("a", "b", "c"):
        r = _reading(rid)
        cache.put(r, r.rec)
    assert cache.get("a") is None and cache.get("b") and cache.get("c")


def test_first_headline_is_kept_for_what_changed():
    cache = AnswerCache(Clock())
    r = _reading("x")
    cache.put(r, r.rec)  # no answer: headline None
    assert cache.get("x").first_headline is None


def test_the_cache_keeps_the_latest_answer_and_the_chat():
    clock = Clock()
    cache = AnswerCache(clock)
    r = _reading("b" * 32)
    cache.put(r, r.rec)
    assert cache.get("b" * 32).latest is r.rec
    refined = r.rec.model_copy(update={"refined_from": "Water it."})
    cache.set_latest("b" * 32, refined)
    assert cache.get("b" * 32).latest is refined
    assert cache.add_chat("b" * 32, ChatMessage(role="user", content="hi"))
    assert [m.content for m in cache.get("b" * 32).chat] == ["hi"]
    clock.now = T0 + TTL + timedelta(seconds=1)
    assert cache.get("b" * 32) is None
    assert cache.add_chat("b" * 32, ChatMessage(role="user", content="late")) is False
    cache.set_latest("b" * 32, refined)  # gone: a no-op, no error


def test_get_for_checks_the_owner():
    cache = AnswerCache(Clock())
    mine, anon = _reading("c" * 32), _reading("d" * 32)
    cache.put(mine, mine.rec, owner="u1")
    cache.put(anon, anon.rec)
    assert cache.get_for("c" * 32, "u1") is not None
    assert cache.get_for("c" * 32, "u2") is None and cache.get_for("c" * 32, None) is None
    assert cache.get_for("d" * 32, None) is not None and cache.get_for("d" * 32, "u1") is None


def test_a_record_without_a_reading_is_kept_for_its_page():
    from datetime import UTC, datetime

    from herbtwin.answer_cache import AnswerCache
    from herbtwin.schemas import AnalysisRecord

    now = datetime(2026, 10, 11, 9, tzinfo=UTC)
    rec = AnalysisRecord(
        record_id="ab" * 16,
        taken_at=now,
        taken_at_source="assumed",
        location=None,
        observation=None,
        environment=None,
        pack=None,
        state=None,
    )
    cache = AnswerCache(lambda: now)
    cache.put(None, rec, "u1", last_decline=3)
    entry = cache.get_for(rec.record_id, "u1")
    assert entry is not None and entry.reading is None and entry.latest is rec
    assert entry.last_decline == 3 and cache.get_for(rec.record_id, None) is None
