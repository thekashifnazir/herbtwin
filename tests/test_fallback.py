"""The photo model's backup: a second model reads the photo when the first can't."""

import json
import logging

import pytest

from herbtwin.adapters import get_observe_adapter
from herbtwin.adapters.base import AdapterError, CallRecord, ModelAdapter, TokenOverrun
from herbtwin.adapters.fallback import FallbackAdapter
from herbtwin.adapters.tokenfactory import TokenFactoryAdapter
from herbtwin.config import load_settings
from herbtwin.tracing import bind


class Scripted(ModelAdapter):
    """Answers with `reply`, or raises `error`; records each call like a real adapter."""

    def __init__(self, model: str, reply: str = "", error: Exception | None = None) -> None:
        self.model, self.reply, self.error = model, reply, error
        self.asked: list[str] = []  # shared by copies, so a copy's call still counts

    def _answer(self) -> str:
        self.asked.append(self.model)
        if self.error is not None:
            raise self.error
        self._record(CallRecord(self.model, self.stage, "p", self.reply, 1, 1, 1, 0.0, False))
        return self.reply

    def complete(self, system, user, *, max_tokens=1024):
        return self._answer()

    def complete_with_image(self, system, user, image, mime, schema=None, *, max_tokens=1024):
        return self._answer()

    def complete_with_images(self, system, user, images, schema=None, *, max_tokens=1024):
        return self._answer()


def test_the_first_model_answers_and_the_backup_is_not_asked():
    first, backup = Scripted("glm", "from glm"), Scripted("gemma", "from gemma")
    a = FallbackAdapter(first, backup)
    assert a.complete_with_image("s", "u", b"img", "image/jpeg") == "from glm"
    assert backup.asked == []


def test_a_failed_first_model_hands_the_photo_to_the_backup(caplog):
    first = Scripted("glm", error=AdapterError("glm: Request timed out."))
    backup = Scripted("gemma", "from gemma")
    a = FallbackAdapter(first, backup)
    with caplog.at_level(logging.WARNING):
        assert a.complete_with_image("s", "u", b"img", "image/jpeg") == "from gemma"
    assert first.asked == ["glm"] and backup.asked == ["gemma"]
    assert "glm" in caplog.text and "gemma" in caplog.text


def test_when_both_fail_the_backups_error_is_raised():
    first = Scripted("glm", error=AdapterError("glm down"))
    backup = Scripted("gemma", error=AdapterError("gemma down"))
    with pytest.raises(AdapterError, match="gemma down"):
        FallbackAdapter(first, backup).complete_with_images("s", "u", [(b"i", "image/jpeg")])


def test_a_bound_fallback_traces_the_backups_call_under_its_stage():
    seen: list[CallRecord] = []
    first = Scripted("glm", error=AdapterError("glm down"))
    bound = bind(FallbackAdapter(first, Scripted("gemma", "ok")), "observe", seen.append)
    bound.complete_with_image("s", "u", b"img", "image/jpeg")
    assert [(r.model, r.stage) for r in seen] == [("gemma", "observe")]


def _settings(**extra):
    return load_settings(
        {
            "HERBTWIN_HOME_LAT": "51.5",
            "HERBTWIN_HOME_LON": "-0.1",
            "HERBTWIN_BACKEND": "tokenfactory",
            "HERBTWIN_NEBIUS_API_KEY": "k",
            "HERBTWIN_OBSERVE_MODEL": "glm",
            "HERBTWIN_ADVISE_MODEL": "nemotron",
            "HERBTWIN_TOKENFACTORY_TIMEOUT_S": "180",
            **extra,
        }
    )


def test_without_a_backup_the_photo_model_is_used_alone():
    a = get_observe_adapter(_settings())
    assert isinstance(a, TokenFactoryAdapter) and a.model == "glm"


def test_with_a_backup_both_photo_models_get_the_shorter_photo_timeout():
    a = get_observe_adapter(
        _settings(HERBTWIN_OBSERVE_FALLBACK_MODEL="gemma", HERBTWIN_OBSERVE_TIMEOUT_S="90")
    )
    assert isinstance(a, FallbackAdapter)
    assert (a.first.model, a.backup.model) == ("glm", "gemma")
    assert a.first.client.timeout == a.backup.client.timeout == 90


def test_the_photo_timeout_defaults_to_the_token_factory_timeout():
    assert _settings().observe_timeout_s == 180
    with pytest.raises(ValueError, match="HERBTWIN_OBSERVE_TIMEOUT_S"):
        _settings(HERBTWIN_OBSERVE_TIMEOUT_S="soon")


def test_the_pipeline_reads_photos_through_the_backup(tmp_path):
    from herbtwin.pipeline import build_deps

    deps = build_deps(_settings(HERBTWIN_OBSERVE_FALLBACK_MODEL="gemma"), tmp_path / "t.db")
    assert isinstance(deps.observe_adapter, FallbackAdapter)


def test_after_a_failure_the_backup_is_asked_first_for_a_while():
    # a silent model costs the full timeout on every call: repairs and the next uploads
    # skip it until the cool-off ends, then it is tried again
    now = [0.0]
    first = Scripted("glm", error=AdapterError("glm down"))
    backup = Scripted("gemma", "ok")
    a = FallbackAdapter(first, backup, cool_off_s=300, clock=lambda: now[0])
    a.complete_with_image("s", "u", b"img", "image/jpeg")
    bind(a, "observe", lambda r: None).complete_with_image("s", "u", b"img", "image/jpeg")
    assert first.asked == ["glm"] and backup.asked == ["gemma", "gemma"]
    now[0] = 301
    first.error = None
    first.reply = "glm back"
    assert a.complete_with_image("s", "u", b"img", "image/jpeg") == "glm back"


def test_a_cut_off_reply_from_the_first_model_goes_to_the_backup():
    first = Scripted("glm", error=TokenOverrun("glm: reply cut off at 4096 tokens"))
    assert FallbackAdapter(first, Scripted("gemma", "ok")).complete("s", "u") == "ok"


def test_the_photo_timeout_applies_without_a_backup_too():
    a = get_observe_adapter(_settings(HERBTWIN_OBSERVE_TIMEOUT_S="90"))
    assert a.client.timeout == 90


def test_a_run_knows_when_the_backup_read_its_photo():
    # the spot page asks "pot or ground?" when the backup read the photo (Gemma reads pots
    # as open ground: 13 Oct eval, setting 0.78 vs GLM 0.93); bind() copies per run, so
    # one run's flag never leaks into the next
    shared = FallbackAdapter(
        Scripted("glm", error=AdapterError("glm down")), Scripted("gemma", "ok")
    )
    run = bind(shared, "spot", lambda r: None)
    run.complete_with_image("s", "u", b"img", "image/jpeg")
    assert run.used_backup and not shared.used_backup
    skipped = bind(shared, "spot", lambda r: None)  # in the cool-off: the backup goes first
    skipped.complete_with_image("s", "u", b"img", "image/jpeg")
    assert skipped.used_backup
    fine = bind(
        FallbackAdapter(Scripted("glm", "ok"), Scripted("gemma", "ok")), "spot", lambda r: None
    )
    fine.complete_with_image("s", "u", b"img", "image/jpeg")
    assert not fine.used_backup


def test_a_model_that_stays_down_is_skipped_for_longer_each_time():
    # live 13 Oct: GLM stayed down all day, so every upload after a quiet 5 minutes paid the
    # full 90 s wait again (95 s for a judge arriving cold). Each failure in a row now triples
    # the skip, up to an hour; one good answer resets it
    now = [0.0]
    first = Scripted("glm", error=AdapterError("glm down"))
    a = FallbackAdapter(first, Scripted("gemma", "ok"), cool_off_s=300, clock=lambda: now[0])

    def tried_at(t: float) -> bool:
        now[0], before = t, len(first.asked)
        a.complete("s", "u")
        return len(first.asked) > before

    assert tried_at(0)  # fails: skipped for 300 s
    assert not tried_at(299) and tried_at(301)  # fails again: 900 s
    assert not tried_at(1200) and tried_at(1202)  # 2700 s
    assert not tried_at(3900) and tried_at(3903)  # capped at an hour
    assert not tried_at(7502) and tried_at(7504)
    first.error, first.reply = None, "glm back"
    now[0] = 11105
    assert a.complete("s", "u") == "glm back"  # back: the next failure starts at 300 s again
    first.error = AdapterError("glm down")
    assert tried_at(11106) and not tried_at(11405) and tried_at(11407)


def test_cut_off_replies_never_grow_the_skip():
    # a reply cut off at max_tokens is a long answer, not an outage: four in a row must not
    # push a working model out for an hour (review of the growing skip)
    now = [0.0]
    first = Scripted("glm", error=TokenOverrun("glm: reply cut off"))
    a = FallbackAdapter(first, Scripted("gemma", "ok"), cool_off_s=300, clock=lambda: now[0])
    for t in (0, 301, 602, 903):
        now[0] = t
        a.complete("s", "u")
    assert len(first.asked) == 4  # retried every 5 minutes, never skipped for longer


def test_the_chat_gets_the_fast_model_with_reasoning_off(tmp_path):
    # chat what-ifs on Nano: 10/10 and ~2x faster than Super with reasoning off, 8/10 with
    # it on (scripts/check_chat.py, 14 Oct)
    from herbtwin.pipeline import build_deps

    deps = build_deps(
        _settings(HERBTWIN_FAST_MODEL="nano", HERBTWIN_NO_THINKING_MODELS="nano"),
        tmp_path / "t.db",
    )
    assert deps.chat_adapter.model == "nano" and deps.advise_adapter.model == "nemotron"
    assert deps.chat_adapter.extra_body == {"chat_template_kwargs": {"enable_thinking": False}}
    assert build_deps(_settings(), tmp_path / "u.db").chat_adapter is None


def test_a_first_model_that_sends_no_usable_reading_hands_the_photo_to_the_backup():
    # 18 Oct, Kash's pots photo: GLM sent no JSON twice (read and repair) and the page said
    # "Could not read the photo" after 76 s; the backup only stepped in on an error
    from herbtwin.stages.observe import observe
    from tests.test_pipeline import OBS

    first = Scripted("glm", "I see some pots on a patio.")
    backup = Scripted("deepseek", json.dumps(OBS))
    shared = FallbackAdapter(first, backup)
    a = bind(shared, "observe", lambda r: None)
    obs = observe(a, b"img", "image/jpeg")
    assert obs.species[0].common_name == "basil"
    assert first.asked == ["glm", "glm"] and backup.asked == ["deepseek"]
    assert a.used_backup and not shared.used_backup  # this run only
    # one bad reading is about the photo, not an outage: the next photo, through the same
    # shared adapter, still goes to GLM first
    observe(bind(shared, "observe", lambda r: None), b"i", "image/png")
    assert first.asked[-1] == "glm" and backup.asked == ["deepseek", "deepseek"]


def test_a_backup_that_sends_no_usable_reading_is_not_asked_again():
    from herbtwin.stages.observe import ObserveError, observe

    first = Scripted("glm", error=AdapterError("glm down"))
    backup = Scripted("deepseek", "no json here")
    with pytest.raises(ObserveError, match="invalid after repair"):
        observe(bind(FallbackAdapter(first, backup), "observe", lambda r: None), b"i", "x/y")
    assert backup.asked == ["deepseek", "deepseek"]  # its read and its repair, nothing more


def test_the_backup_gets_one_call_after_a_bad_reading():
    # the page has 270 s for the whole read: GLM's read and repair, then one backup call
    from herbtwin.stages.observe import ObserveError, observe

    first, backup = Scripted("glm", "pots"), Scripted("deepseek", "still no json")
    with pytest.raises(ObserveError):
        observe(bind(FallbackAdapter(first, backup), "observe", lambda r: None), b"i", "x/y")
    assert backup.asked == ["deepseek"]


def test_a_bad_reading_that_took_too_long_leaves_no_time_for_the_backup():
    from herbtwin.stages.observe import BACKUP_WITHIN_S, ObserveError, observe

    first, backup = Scripted("glm", "pots"), Scripted("deepseek", "{}")
    times = iter([0.0, BACKUP_WITHIN_S + 1])
    a = bind(FallbackAdapter(first, backup), "observe", lambda r: None)
    with pytest.raises(ObserveError):
        observe(a, b"i", "x/y", clock=lambda: next(times))
    assert backup.asked == [] and not a.used_backup
