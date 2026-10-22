"""A slow photo read races the backup, and the closer photo check runs beside research and
the weather (21 Oct: the photo read was 60-70% of a run, p95 35 s, and the backup only
started after GLM, so the slowest answers took 70-90 s)."""

import dataclasses
import functools
import json
import threading
import time

import httpx
import pytest
import respx

import herbtwin.pipeline as pl
import herbtwin.stages.observe as observe_stage
from herbtwin.adapters.base import AdapterError, CallRecord, ModelAdapter
from herbtwin.adapters.fallback import FallbackAdapter
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.stages.observe import ObserveError, observe
from herbtwin.tracing import StageTracer, TraceStore, bind
from tests.test_pipeline import JPEG, OBS, SAMPLE, WHEN, _deps

HEDGE = 0.05  # the race starts this soon in these tests; live it is HEDGE_AFTER_S
# how long a gated call waits for its cue at most. The tests say which call answers first
# with events, not with sleeps and a wall-clock margin: under a loaded machine (several
# suites at once) a margin of a few tenths of a second failed pushes (22 Oct)
CUE_S = 5.0
FULL = {**OBS, "decline": 0, "leaf_colour": "green"}  # strict reads need these too
BASIL = json.dumps(FULL)
MINT = json.dumps(
    {**FULL, "species": [{"name": "Mentha spicata", "common_name": "mint", "confidence": 0.9}]}
)


class Timed(ModelAdapter):
    """Waits `delay` seconds (and for `cue`, when given), then answers `reply` or raises
    `error`; traced like a real adapter. The fallback copies it for each call, so what a test
    reads back (`asked`, `started`, `answered`, `missed_cue`: a cue never came) is a shared
    list or Event, never a plain attribute set on the copy."""

    def __init__(
        self, model: str, reply: str = "", *, delay: float = 0.0, error=None, alone=None,
        cue: threading.Event | None = None,
    ) -> None:  # fmt: skip
        self.model, self.reply, self.delay, self.error = model, reply, delay, error
        self.alone = reply if alone is None else alone  # the reply to one photo alone
        self.cue = cue
        self.asked: list[str] = []
        self.started, self.answered = threading.Event(), threading.Event()
        self.missed_cue = threading.Event()
        self.before = self.after = lambda n: None  # hooks around the n-th call's trace

    def _answer(self, reply: str) -> str:
        self.asked.append(self.model)
        self.started.set()
        n = len(self.asked)
        time.sleep(self.delay)
        if self.cue is not None and not self.cue.wait(CUE_S):
            self.missed_cue.set()
        try:
            if self.error is not None:
                raise self.error
            self.before(n)
            self._record(CallRecord(self.model, self.stage, "p", reply, 9, 1, 1, 0.0, False))
            self.after(n)
            return reply
        finally:
            self.answered.set()

    def complete(self, system, user, *, max_tokens=1024):
        return self._answer(self.reply)

    def complete_with_image(self, system, user, image, mime, schema=None, *, max_tokens=1024):
        return self._answer(self.alone)

    def complete_with_images(self, system, user, images, schema=None, *, max_tokens=1024):
        return self._answer(self.reply)


def _read(first: Timed, backup: Timed, tmp_path, hedge: float = HEDGE, **kwargs):
    store = TraceStore(tmp_path / "t.db")
    a = bind(FallbackAdapter(first, backup), "observe", StageTracer(store, "run"))
    started = time.monotonic()
    obs = observe(a, b"img", "image/jpeg", hedge_after_s=hedge, **kwargs)
    return obs, time.monotonic() - started, store


def test_a_slow_first_model_loses_to_the_backup_soon_after_the_threshold(tmp_path):
    held = threading.Event()  # GLM answers only once the read is back
    first, backup = Timed("glm", BASIL, cue=held), Timed("deepseek", MINT)
    try:
        obs, _, store = _read(first, backup, tmp_path)
        assert obs.species[0].common_name == "mint"  # the backup's reading
        assert not first.answered.is_set()  # never waited for GLM's own answer
    finally:
        held.set()  # never leave a racer holding its slot for later tests
    # the loser still finishes on its own, and both calls are traced under their models
    assert first.answered.wait(CUE_S)
    time.sleep(0.05)
    rows = store.rows("run")
    assert sorted(r["model"] for r in rows) == ["deepseek", "glm"]
    assert {r["stage"] for r in rows} == {"observe"}


def test_a_fast_usable_first_model_never_starts_the_backup(tmp_path):
    first, backup = Timed("glm", BASIL), Timed("deepseek", MINT)
    obs, _, store = _read(first, backup, tmp_path, hedge=0.2)
    time.sleep(0.3)  # past the threshold: still nothing asked of the backup
    assert obs.species[0].common_name == "basil" and backup.asked == []
    assert [r["model"] for r in store.rows("run")] == ["glm"]


def test_a_quick_unusable_reply_still_hands_the_photo_to_the_backup_at_once(tmp_path):
    first, backup = Timed("glm", "I see some pots."), Timed("deepseek", MINT)
    obs, _, _ = _read(first, backup, tmp_path, hedge=5.0)  # never reached
    assert obs.species[0].common_name == "mint"
    assert first.asked == ["glm", "glm"] and backup.asked == ["deepseek"]  # read, repair


def test_the_first_model_wins_when_it_answers_before_a_slower_backup(tmp_path):
    held = threading.Event()  # the backup answers only once the read is back
    backup = Timed("deepseek", MINT, cue=held)
    first = Timed("glm", BASIL, cue=backup.started)  # GLM answers once the race is on
    try:
        obs, _, _ = _read(first, backup, tmp_path)
        assert obs.species[0].common_name == "basil" and backup.asked == ["deepseek"]
        assert not first.missed_cue.is_set()  # the backup was racing when GLM answered
        assert not backup.answered.is_set()  # GLM's reading did not wait for the backup's
    finally:
        held.set()


def test_a_first_model_that_fails_mid_race_does_not_ask_the_backup_twice(tmp_path):
    # GLM fails once the backup is racing, and the backup answers after that failure: its
    # one call in flight is the reading, not a second call made after GLM's error
    backup = Timed("deepseek", MINT)
    first = Timed("glm", error=AdapterError("glm: Request timed out."), cue=backup.started)
    backup.cue = first.answered
    obs, _, _ = _read(first, backup, tmp_path)
    assert obs.species[0].common_name == "mint"
    # raced, not one after the other: GLM failed while the backup's call was in flight
    assert not first.missed_cue.is_set() and not backup.missed_cue.is_set()
    time.sleep(0.2)  # long enough for a second backup call to have started
    assert backup.asked == ["deepseek"]


def test_when_both_racers_fail_the_backup_is_not_asked_again(tmp_path):
    first = Timed("glm", "pots", delay=0.1)
    backup = Timed("deepseek", "still no json", delay=0.15)
    with pytest.raises(ObserveError, match="observe output invalid"):
        _read(first, backup, tmp_path)
    assert backup.asked == ["deepseek"]


def test_several_photos_both_racers_failed_on_are_read_as_the_main_photo_alone(tmp_path):
    # as before the race: no reading of several photos falls back to the main one alone
    first = Timed("glm", "pots", delay=0.1, alone=BASIL)
    backup = Timed("deepseek", "still no json", delay=0.15)
    obs, _, _ = _read(first, backup, tmp_path, more=[(b"leaf", "image/jpeg")])
    assert obs.species[0].common_name == "basil"
    assert backup.asked == ["deepseek"] and first.asked == ["glm", "glm", "glm"]


def test_a_backup_that_fails_leaves_the_slower_first_models_reading(tmp_path):
    first = Timed("glm", BASIL, delay=0.3)
    backup = Timed("deepseek", error=AdapterError("deepseek down"))
    obs, _, _ = _read(first, backup, tmp_path)
    assert obs.species[0].common_name == "basil"


def test_strict_eval_reads_never_race(tmp_path):
    first, backup = Timed("glm", BASIL, delay=0.2), Timed("deepseek", MINT)
    obs, _, _ = _read(first, backup, tmp_path, strict=True)
    assert obs.species[0].common_name == "basil" and backup.asked == []


def test_with_no_race_slot_free_a_read_runs_one_model_after_the_other(tmp_path, monkeypatch):
    monkeypatch.setattr(observe_stage, "_FREE", threading.BoundedSemaphore(1))
    observe_stage._FREE.acquire()  # every slot taken
    first, backup = Timed("glm", BASIL, delay=0.2), Timed("deepseek", MINT)
    obs, _, _ = _read(first, backup, tmp_path)
    assert obs.species[0].common_name == "basil" and backup.asked == []


@respx.mock
def test_the_closer_photo_check_runs_beside_the_weather(tmp_path, monkeypatch):
    # each waits until the other has started: one after the other, neither would see that
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    real_check, real_fetch = pl.check_problem, pl.fetch_environment
    checking, fetching, saw = threading.Event(), threading.Event(), {}

    def slow_check(*a, **k):
        checking.set()
        saw["weather"] = fetching.wait(CUE_S)
        return real_check(*a, **k)

    def slow_fetch(*a, **k):
        fetching.set()
        saw["check"] = checking.wait(CUE_S)
        return real_fetch(*a, **k)

    monkeypatch.setattr(pl, "check_problem", slow_check)
    monkeypatch.setattr(pl, "fetch_environment", slow_fetch)
    seen = {**OBS, "symptoms": ["downy mildew fuzz under the leaves"]}
    reply = json.dumps({"problem": "basil downy mildew", "seen": "grey fuzz"})
    deps = _deps(tmp_path, [json.dumps(seen), reply], [])
    lines: list = []
    reading = pl.read_photo(deps, JPEG, "image/jpeg", received=WHEN, progress=lines.append)
    assert saw == {"weather": True, "check": True}  # both ran at once
    assert reading.rec.problem is not None and reading.rec.problem.name == "basil downy mildew"
    assert reading.rec.environment is not None
    # the check is the step still running once the weather is in, so it is said last
    said = [line for line in lines if isinstance(line, str)]
    assert said.index("Looking closer at the leaves") > said.index(
        "Checking the weather where you are"
    )


@respx.mock
def test_the_wait_names_the_winner_even_when_the_losers_call_is_traced_after_it(
    tmp_path, monkeypatch
):
    # #376 named the photo model from the last traced call: racing, that can be the loser.
    # Here GLM's junk reply is traced just after DeepSeek's winning one, before "Found"
    from herbtwin import receipt
    from herbtwin.pipeline import PlantFound

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    monkeypatch.setattr(pl, "observe", functools.partial(observe, hedge_after_s=HEDGE))
    glm_id, deepseek_id = "zai-org/GLM-5.3-Flash", "deepseek-ai/DeepSeek-V4.1-Flash"
    glm, deepseek = Timed(glm_id, "no JSON here"), Timed(deepseek_id, BASIL)
    backup_traced, glm_traced = threading.Event(), threading.Event()
    glm.before = lambda n: backup_traced.wait(2) if n == 1 else time.sleep(0.3)
    glm.after = lambda n: glm_traced.set()
    deepseek.before = lambda n: time.sleep(HEDGE * 2)  # well after the race starts
    deepseek.after = lambda n: (backup_traced.set(), glm_traced.wait(2))
    deps = dataclasses.replace(
        _deps(tmp_path, [], []), observe_adapter=FallbackAdapter(glm, deepseek)
    )
    lines: list = []
    reading = pl.read_photo(deps, JPEG, "image/jpeg", received=WHEN, progress=lines.append)
    assert PlantFound("basil", deepseek_id) in lines
    # both calls were billed, so once the loser's repair is in the receipt lists both
    assert glm.answered.wait(2)
    deadline = time.monotonic() + 2
    while len(glm.asked) < 2 or len(deps.trace_store.rows(reading.rec.record_id)) < 3:
        assert time.monotonic() < deadline
        time.sleep(0.02)
    rec = reading.rec
    pl._note_models(deps, rec, receipt.MODEL_STAGES)
    calls = {s.model: s.calls for s in rec.receipt if s.stage == "observe"}
    assert calls == {glm_id: 2, deepseek_id: 1}
