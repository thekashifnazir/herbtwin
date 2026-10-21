"""Photo reads against the caps and the live budget (spec D59, D60), in the app."""

import json
import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from herbtwin.adapters.mock import MockAdapter
from herbtwin.config import load_settings
from herbtwin.mail import MailError
from herbtwin.pipeline import Deps
from herbtwin.tracing import TraceStore
from herbtwin.usage import Limits, MemoryUsage, UsageError, Verdict
from herbtwin.web.app import create_app
from herbtwin.web.judge import COOKIE, judge_token
from tests.fakes import follow
from tests.test_web import JPEG, OBS, PNG

BUSY = "The garden&#39;s had a busy day. Try again tomorrow."
BUDGET = "herbtwin has used its budget for model calls, so photo reads are paused for now."
CODE = "judge-code"
NOT_A_PLANT = json.dumps(dict(OBS, is_plant=False, species=[]))  # one model call, no weather
OCT_12 = datetime(2026, 10, 12, 9, tzinfo=UTC)


def _client(tmp_path, env=None, usage=None, mail=None, reads=12, clock=None) -> TestClient:
    deps = Deps(
        observe_adapter=MockAdapter([NOT_A_PLANT] * reads),
        advise_adapter=MockAdapter([]),
        settings=load_settings({"HERBTWIN_JUDGE_CODE": CODE, **(env or {})}),
        trace_store=TraceStore(tmp_path / "t.db"),
        cache_dir=tmp_path / "p",
        workers=1,
    )
    clock = clock or (lambda: OCT_12)
    return TestClient(create_app(deps, clock=clock, usage=usage, mail=mail))


def _upload(c: TestClient):
    return c.post("/analyse", files={"photo": ("b.jpg", JPEG, "image/jpeg")})


def test_eleventh_upload_from_one_visitor_is_refused(tmp_path):
    store = MemoryUsage()
    c = _client(tmp_path, usage=store)
    for _ in range(10):
        assert "No plant found" in follow(c, _upload(c)).text
    r = _upload(c)
    assert r.status_code == 429 and BUSY in r.text
    assert 'id="next"' not in r.text  # refused before the stream starts
    assert store.days == {date(2026, 10, 12): 10}


def test_day_cap_refuses_with_the_busy_page(tmp_path):
    c = _client(tmp_path, {"HERBTWIN_DAILY_READS": "1"}, usage=MemoryUsage())
    assert _upload(c).status_code == 200
    r = _upload(c)
    assert r.status_code == 429 and BUSY in r.text


def test_judge_cookie_passes_the_cap(tmp_path):
    c = _client(tmp_path, usage=MemoryUsage())
    for _ in range(10):
        assert _upload(c).status_code == 200
    c.cookies.set(COOKIE, judge_token(CODE))
    assert "No plant found" in follow(c, _upload(c)).text


def test_tampered_judge_cookie_does_not_pass(tmp_path):
    c = _client(tmp_path, {"HERBTWIN_VISITOR_READS": "1"}, usage=MemoryUsage())
    c.cookies.set(COOKIE, judge_token("guess"))
    assert _upload(c).status_code == 200
    assert _upload(c).status_code == 429


def test_budget_spent_gets_the_paused_page(tmp_path):
    env = {"HERBTWIN_LIVE_BUDGET_USD": "0.01", "HERBTWIN_READ_COST_USD": "0.01"}
    c = _client(tmp_path, env, usage=MemoryUsage(), mail=lambda s, t: None)
    assert _upload(c).status_code == 200
    r = _upload(c)
    assert r.status_code == 429 and BUDGET in r.text


def test_api_returns_429_json_when_capped(tmp_path):
    c = _client(tmp_path, {"HERBTWIN_VISITOR_READS": "1"}, usage=MemoryUsage())
    files = {"photo": ("b.png", PNG, "image/png")}
    assert c.post("/api/analyse", files=files).status_code == 200
    r = c.post("/api/analyse", files=files)
    assert r.status_code == 429 and r.json() == {"detail": BUSY.replace("&#39;", "'")}


def test_api_judge_passes_the_cap(tmp_path):
    c = _client(tmp_path, {"HERBTWIN_VISITOR_READS": "1"}, usage=MemoryUsage())
    c.cookies.set(COOKIE, judge_token(CODE))
    files = {"photo": ("b.png", PNG, "image/png")}
    assert [c.post("/api/analyse", files=files).status_code for _ in range(2)] == [200, 200]


BUDGET_5C = {"HERBTWIN_LIVE_BUDGET_USD": "0.05", "HERBTWIN_READ_COST_USD": "0.01"}


def test_crossing_eighty_percent_sends_one_mail_and_marks_it(tmp_path):
    sent: list[tuple[str, str]] = []
    store = MemoryUsage()
    c = _client(tmp_path, BUDGET_5C, usage=store, mail=lambda s, t: sent.append((s, t)))
    for _ in range(3):
        _upload(c)
    assert sent == []
    _upload(c)  # 0.04 of 0.05
    assert len(sent) == 1 and store.warned
    subject, text = sent[0]
    assert subject == "herbtwin has used 80% of its live budget"
    assert "$0.04" in text and "$0.05" in text
    _upload(c)
    assert len(sent) == 1


def test_failing_mail_is_tried_again_at_most_once_a_minute(tmp_path, caplog):
    tries: list[str] = []

    def broken(subject: str, text: str) -> None:
        tries.append(subject)
        raise MailError("resend down")

    now = [OCT_12]
    store = MemoryUsage()
    store.spent = Decimal("0.75")  # each read below takes it on by 0.05 of the $1 budget
    env = {"HERBTWIN_LIVE_BUDGET_USD": "1", "HERBTWIN_READ_COST_USD": "0.05"}
    c = _client(tmp_path, env, store, broken, clock=lambda: now[0])
    with caplog.at_level(logging.ERROR):
        assert _upload(c).status_code == 200  # the read still goes ahead
    assert len(tries) == 1 and not store.warned
    assert "budget warning" in caplog.text
    now[0] += timedelta(seconds=30)
    assert _upload(c).status_code == 200
    assert len(tries) == 1  # a failing Resend does not slow every request
    now[0] += timedelta(seconds=31)
    _upload(c)
    assert len(tries) == 2 and not store.warned


class DownUsage:
    def count_read(self, day, visitor, limits: Limits, *, judge: bool) -> Verdict:
        raise UsageError("count_photo_read: HTTP 500")

    def mark_warned(self) -> None:
        raise UsageError("down")


def test_usage_store_down_lets_the_read_through_and_logs(tmp_path, caplog):
    c = _client(tmp_path, usage=DownUsage())
    with caplog.at_level(logging.ERROR):
        assert "No plant found" in follow(c, _upload(c)).text
    assert "usage store" in caplog.text


def test_no_usage_store_counts_nothing(tmp_path):
    c = _client(tmp_path, {"HERBTWIN_VISITOR_READS": "1"})
    assert [_upload(c).status_code for _ in range(3)] == [200, 200, 200]


def test_a_bad_form_is_refused_before_counting(tmp_path):
    store = MemoryUsage()
    c = _client(tmp_path, usage=store)
    r = c.post("/analyse", data={"lat": "51.5"}, files={"photo": ("b.jpg", JPEG, "image/jpeg")})
    assert r.status_code == 400 and store.days == {}


def test_only_photo_reads_count(tmp_path):
    store = MemoryUsage()
    c = _client(tmp_path, usage=store)
    c.get("/")
    c.get("/judge")
    assert store.days == {}


def test_live_counters_only_with_caps_on_and_the_secret_key():
    from herbtwin.usage import SupabaseUsage
    from herbtwin.web.app import _usage_from

    sb = {"HERBTWIN_SUPABASE_URL": "https://sb.test", "HERBTWIN_SUPABASE_SECRET_KEY": "k"}
    assert _usage_from(load_settings(sb)) is None  # local runs never write hosted counters
    assert _usage_from(load_settings({"HERBTWIN_CAPS_ENABLED": "1"})) is None
    live = _usage_from(load_settings({**sb, "HERBTWIN_CAPS_ENABLED": "1"}))
    assert isinstance(live, SupabaseUsage) and live.url == "https://sb.test"


def test_a_non_photo_upload_does_not_use_a_slot(tmp_path):
    store = MemoryUsage()
    c = _client(tmp_path, usage=store)
    r = c.post("/analyse", files={"photo": ("x.txt", b"not a photo", "text/plain")})
    assert r.status_code == 400 and store.days == {}
    r = c.post("/api/analyse", files={"photo": ("x.txt", b"not a photo", "text/plain")})
    assert r.status_code == 400 and store.days == {}


def test_the_limit_page_band_reaches_both_edges_of_a_wide_screen(tmp_path):
    # 21 Oct, Kash at 2000px: the band stopped short on the right and left a white block.
    # The band's full bleed (50% - 50vw) needs a centred column; the limit page keeps the
    # 38rem reading column, whose wide right padding put the band 279px to the left
    from herbtwin.web import style

    c = _client(tmp_path, {"HERBTWIN_DAILY_READS": "1"}, usage=MemoryUsage())
    _upload(c)
    r = _upload(c)
    assert r.status_code == 429 and "That&#39;s the limit for today" in r.text
    assert '<div class="wrap">\n<div class="page-band">' in r.text  # the reading column
    assert "main .wrap:has(> .page-band) { padding-right: 16px; }" in style.CSS
