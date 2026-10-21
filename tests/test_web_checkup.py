import html
import json
from datetime import timedelta

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from herbtwin import scoring
from herbtwin.adapters.mock import MockAdapter
from herbtwin.config import load_settings
from herbtwin.history import HistoryError, MemoryHistory, MemoryHistoryStore
from herbtwin.pipeline import Deps
from herbtwin.stages.environment import OPEN_METEO_URL
from herbtwin.tracing import TraceStore
from herbtwin.web.app import create_app
from tests.fakes import FakeAuth, fake_accounts, follow
from tests.test_web import ADV, JPEG, OBS, OCT_4, SAMPLE

SAGE = {
    **OBS,
    "species": [{"name": "Salvia officinalis", "common_name": "sage", "confidence": 0.9}],
}
LESS = [json.dumps({"change": c, "confidence": "high", "reason": "r"}) for c in ("less", "more")]
AGREE_LESS = LESS * 2  # earlier-first "less", later-first "more" (= less), twice
PASSED = scoring.Gate(
    prompt_version="c2-v1",
    signals={"posture": "passed", "tissue": "untested", "colour": "untested"},
)


@pytest.fixture(autouse=True)
def _gate(monkeypatch):
    monkeypatch.setattr(scoring, "load_gate", lambda: PASSED)


def _signed_in(tmp_path, observe, now):
    hist, auth = MemoryHistory(), FakeAuth()
    deps = Deps(
        observe_adapter=MockAdapter(observe),
        advise_adapter=MockAdapter([json.dumps(ADV)] * 9),
        settings=load_settings({"HERBTWIN_HOME_LAT": "51.5", "HERBTWIN_HOME_LON": "-0.12"}),
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "p",
        workers=1,
    )
    c = TestClient(create_app(deps, clock=lambda: now[0], accounts=fake_accounts(hist, auth)))
    c.post(
        "/auth/callback",
        data={"token_hash": auth.issue("u1", "a@b.co"), "type": "email"},
        follow_redirects=False,
    )
    return c, hist


def _upload(c):
    r = c.post("/analyse", files={"photo": ("s.jpg", JPEG, "image/jpeg")}, data={"place": ""})
    return follow(c, r)


def _second_visit(c, hist, now, days=3):
    """First photo now, second photo `days` later, linked to the same plant."""
    _upload(c)
    now[0] = OCT_4 + timedelta(days=days)
    r = _upload(c)
    plant = hist.for_user("u1").list_plants()[0]
    rid = r.text.split('action="/answers/')[1].split("/plant")[0]
    return rid, c.post(f"/answers/{rid}/plant", data={"plant_id": plant.id}), plant


@respx.mock
def test_second_photo_in_the_window_asks_and_a_yes_scores_it(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    now = [OCT_4]
    c, hist = _signed_in(tmp_path, [json.dumps(SAGE)] * 2 + AGREE_LESS, now)
    rid, page, plant = _second_visit(c, hist, now)
    assert "On 4 Oct we suggested watering it. Did you do it?" in page.text
    assert f'action="/answers/{rid}/did-it"' in page.text
    done = c.post(f"/answers/{rid}/did-it", data={"did_it": "yes"})
    assert done.status_code == 200
    assert "Last advice: water (you did it). Since then: less droop." in done.text
    assert "Did you do it?" not in done.text
    [s] = hist.for_user("u1").scores_for(plant.id)
    assert (s.result, s.did_it, s.later_answer_id) == ("improved", "yes", rid)
    calls = c.app.state.deps.observe_adapter.calls
    assert [call["kind"] for call in calls] == ["image", "image"] + ["images"] * 4


@respx.mock
def test_a_second_reply_for_the_same_pair_keeps_the_first(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    now = [OCT_4]
    c, hist = _signed_in(tmp_path, [json.dumps(SAGE)] * 2 + AGREE_LESS, now)
    rid, _, plant = _second_visit(c, hist, now)
    c.post(f"/answers/{rid}/did-it", data={"did_it": "yes"})
    again = c.post(f"/answers/{rid}/did-it", data={"did_it": "no"})
    assert "Last advice: water (you did it)." in again.text
    assert len(hist.for_user("u1").scores_for(plant.id)) == 1
    assert len(c.app.state.deps.observe_adapter.calls) == 6  # no second comparison


@respx.mock
def test_skip_stores_the_reply_without_a_call(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    now = [OCT_4]
    c, hist = _signed_in(tmp_path, [json.dumps(SAGE)] * 2, now)
    rid, _, plant = _second_visit(c, hist, now)
    done = c.post(f"/answers/{rid}/did-it", data={"did_it": "skip"})
    assert "Last advice: water (you skipped the question)." in done.text
    assert hist.for_user("u1").scores_for(plant.id)[0].result == "cant_tell"


@respx.mock
def test_an_untested_signal_is_not_scored_yet_and_makes_no_call(tmp_path, monkeypatch):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    failed = PASSED.model_copy(update={"signals": {"posture": "failed"}})
    monkeypatch.setattr(scoring, "load_gate", lambda: failed)
    now = [OCT_4]
    c, hist = _signed_in(tmp_path, [json.dumps(SAGE)] * 2, now)
    rid, _, plant = _second_visit(c, hist, now)
    done = c.post(f"/answers/{rid}/did-it", data={"did_it": "yes"})
    assert "We can't check droop from photos reliably yet." in html.unescape(done.text)
    assert hist.for_user("u1").scores_for(plant.id)[0].result == "not_scored_yet"


@respx.mock
def test_a_second_photo_the_same_day_is_not_asked_about(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    now = [OCT_4]
    c, hist = _signed_in(tmp_path, [json.dumps(SAGE)] * 2, now)
    _, page, _ = _second_visit(c, hist, now, days=0)
    assert "Did you do it?" not in page.text


@respx.mock
def test_the_refined_page_still_asks(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    now = [OCT_4]
    c, hist = _signed_in(tmp_path, [json.dumps(SAGE)] * 2, now)
    rid, _, _ = _second_visit(c, hist, now)
    refined = c.post(f"/answers/{rid}/refine", data={"soil_feel": "dry"})
    assert refined.status_code == 200 and "Did you do it?" in refined.text


@respx.mock
def test_history_down_while_recording_gives_a_message_not_a_500(tmp_path, monkeypatch):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    now = [OCT_4]
    c, hist = _signed_in(tmp_path, [json.dumps(SAGE)] * 2, now)
    rid, _, plant = _second_visit(c, hist, now)

    def down(self, s):
        raise HistoryError("History is not available right now.")

    monkeypatch.setattr(MemoryHistoryStore, "add_score", down)
    r = c.post(f"/answers/{rid}/did-it", data={"did_it": "skip"})
    assert r.status_code == 503 and "History is not available right now." in r.text
    assert hist.for_user("u1").scores_for(plant.id) == []


def test_signed_out_or_a_bad_reply_is_refused(tmp_path):
    now = [OCT_4]
    c, _ = _signed_in(tmp_path, [], now)
    assert c.post("/answers/abc/did-it", data={"did_it": "maybe"}).status_code == 404
    c.cookies.clear()
    assert c.post("/answers/abc/did-it", data={"did_it": "yes"}).status_code == 404


@respx.mock
def test_plants_page_shows_the_line_and_the_same_spot_tip(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    now = [OCT_4]
    c, hist = _signed_in(tmp_path, [json.dumps(SAGE)] * 2 + AGREE_LESS, now)
    rid, _, _ = _second_visit(c, hist, now)
    c.post(f"/answers/{rid}/did-it", data={"did_it": "yes"})
    page = c.get("/plants").text
    assert "Last advice: water (you did it). Since then: less droop." in page
    assert "from the same spot, at about the same time of day if you can" in page


@respx.mock
def test_the_chooser_shows_the_same_spot_tip(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    now = [OCT_4]
    c, _ = _signed_in(tmp_path, [json.dumps(SAGE)] * 2, now)
    _upload(c)
    r = _upload(c)
    assert "Which plant is this?" in r.text
    assert "from the same spot, at about the same time of day if you can" in r.text


class _SlowMock(MockAdapter):
    """A vision model that takes a moment, so two replies overlap."""

    def complete_with_images(self, system, user, images, schema=None, *, max_tokens=1024):
        import time

        time.sleep(0.05)
        return super().complete_with_images(system, user, images, schema, max_tokens=max_tokens)


@respx.mock
def test_two_overlapping_replies_run_one_comparison_and_store_one_row(tmp_path):
    import threading

    from herbtwin.web import checkup
    from herbtwin.web.accounts import Person

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    now = [OCT_4]
    c, hist = _signed_in(tmp_path, [json.dumps(SAGE)] * 2, now)
    rid, _, plant = _second_visit(c, hist, now)
    deps = c.app.state.deps
    slow = _SlowMock(AGREE_LESS * 2)  # enough for two comparisons, should only one run
    deps.observe_adapter = slow
    person = Person("u1", "a@b.co", hist.for_user("u1"))
    got: list = []

    def reply():
        got.append(checkup.record(deps, person, rid, "yes", now[0]))

    threads = [threading.Thread(target=reply) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(slow.calls) == 4
    assert len(hist.for_user("u1").scores_for(plant.id)) == 1
    assert [g.line for g in got] == ["Last advice: water (you did it). Since then: less droop."] * 2


@respx.mock
def test_a_reply_that_loses_the_save_race_shows_the_stored_result(tmp_path, monkeypatch):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    now = [OCT_4]
    c, hist = _signed_in(tmp_path, [json.dumps(SAGE)] * 2, now)
    rid, _, plant = _second_visit(c, hist, now)
    real = MemoryHistoryStore.add_score

    def saved_elsewhere_then_conflict(self, s):
        real(self, s)  # another server process stored the same pair first
        raise HistoryError("History is not available right now.")

    monkeypatch.setattr(MemoryHistoryStore, "add_score", saved_elsewhere_then_conflict)
    r = c.post(f"/answers/{rid}/did-it", data={"did_it": "skip"})
    assert r.status_code == 200
    assert "Last advice: water (you skipped the question)." in r.text


@respx.mock
def test_someone_elses_answer_is_not_found_and_costs_nothing(tmp_path):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    now = [OCT_4]
    c, hist = _signed_in(tmp_path, [json.dumps(SAGE)] * 2 + AGREE_LESS, now)
    rid, _, plant = _second_visit(c, hist, now)
    c.cookies.clear()
    c.post(
        "/auth/callback",
        data={"token_hash": c.app.state.accounts.auth.issue("u2", "b@b.co"), "type": "email"},
        follow_redirects=False,
    )
    r = c.post(f"/answers/{rid}/did-it", data={"did_it": "yes"})
    assert r.status_code == 404
    assert len(c.app.state.deps.observe_adapter.calls) == 2  # the two photo reads only
    assert hist.for_user("u1").scores_for(plant.id) == []


def test_a_malformed_answer_id_is_not_found_not_history_down(tmp_path, monkeypatch):
    def refuses(self, answer_id):
        raise HistoryError("History is not available right now.")  # PostgREST: not a uuid

    monkeypatch.setattr(MemoryHistoryStore, "get_answer", refuses)
    c, _ = _signed_in(tmp_path, [], [OCT_4])
    r = c.post("/answers/not-an-id/did-it", data={"did_it": "yes"})
    assert r.status_code == 404


@respx.mock
def test_a_retry_after_a_failed_save_reuses_the_comparison(tmp_path, monkeypatch):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    now = [OCT_4]
    c, hist = _signed_in(tmp_path, [json.dumps(SAGE)] * 2 + AGREE_LESS * 2, now)
    rid, _, plant = _second_visit(c, hist, now)
    real = MemoryHistoryStore.add_score
    fails = [True]

    def once_down(self, s):
        if fails.pop() if fails else False:
            raise HistoryError("History is not available right now.")
        real(self, s)

    monkeypatch.setattr(MemoryHistoryStore, "add_score", once_down)
    assert c.post(f"/answers/{rid}/did-it", data={"did_it": "yes"}).status_code == 503
    again = c.post(f"/answers/{rid}/did-it", data={"did_it": "yes"})
    assert again.status_code == 200 and "Since then: less droop." in again.text
    assert len(c.app.state.deps.observe_adapter.calls) == 6  # 2 photo reads + 4 looks, once
    assert len(hist.for_user("u1").scores_for(plant.id)) == 1


@respx.mock
def test_a_kept_comparison_is_not_reused_for_a_changed_signal(tmp_path, monkeypatch):
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    both = PASSED.model_copy(update={"signals": {"posture": "passed", "tissue": "passed"}})
    monkeypatch.setattr(scoring, "load_gate", lambda: both)
    now = [OCT_4]
    c, hist = _signed_in(tmp_path, [json.dumps(SAGE)] * 2 + AGREE_LESS * 2, now)
    rid, _, plant = _second_visit(c, hist, now)
    store = hist.for_user("u1")
    real = MemoryHistoryStore.add_score
    fails = [True]

    def once_down(self, s):
        if fails.pop() if fails else False:
            raise HistoryError("History is not available right now.")
        real(self, s)

    monkeypatch.setattr(MemoryHistoryStore, "add_score", once_down)
    c.post(f"/answers/{rid}/did-it", data={"did_it": "yes"})  # posture compared, save fails
    earlier = next(a for a in store.answers_for(plant.id) if a.id != rid)
    refined = earlier.answer.model_copy(deep=True)
    refined.prediction = refined.prediction.model_copy(
        update={"action": "leave_normal", "signal": "tissue", "window_days": (1, 21)}
    )
    store.update_answer(earlier.id, refined, None)  # the earlier answer was refined meanwhile
    c.post(f"/answers/{rid}/did-it", data={"did_it": "yes"})
    [s] = store.scores_for(plant.id)
    assert s.prediction.signal == "tissue" and s.comparison.signal == "tissue"
    assert len(c.app.state.deps.observe_adapter.calls) == 10  # compared again for tissue


def test_the_kept_sweep_survives_other_pairs_changing_underneath():
    import threading
    import time

    from herbtwin.web import checkup

    stop = time.monotonic() + 0.5
    errors: list[Exception] = []
    old = time.monotonic() - checkup.KEEP_S - 1

    def churn(n):
        while time.monotonic() < stop:
            with checkup._kept_lock:  # as checkup._keep writes, but already expired
                for i in range(50):
                    checkup._kept[(f"{n}-{i}", "x", "posture")] = (old, None)
            try:
                checkup._kept_comparison(("none", "none", "posture"))
            except Exception as e:  # noqa: BLE001 - the race is the point
                errors.append(e)
                return

    threads = [threading.Thread(target=churn, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
