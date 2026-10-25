from datetime import UTC, date, datetime

import httpx
import pytest

from herbtwin import reminders
from tests.test_scoring import _stored

PHOTO = datetime(2026, 10, 12, 10, tzinfo=UTC)


def _reminder(action="water", when=PHOTO, name="Basil"):
    r = reminders.schedule(_stored("a1", when, action=action), name)
    assert r is not None
    return r


@pytest.mark.parametrize(
    ("action", "due", "last"),
    [
        ("water", date(2026, 10, 16), date(2026, 10, 19)),
        ("leave_normal", date(2026, 10, 24), date(2026, 11, 2)),
        ("feed", date(2026, 10, 26), date(2026, 11, 2)),
    ],
)
def test_due_halfway_through_the_check_window(action, due, last):
    r = _reminder(action)
    assert (r.due_on, r.last_on) == (due, last)
    assert r.answer_id == "a1" and r.plant_id == "p" and r.plant_name == "Basil"


def test_days_count_from_the_uk_date_of_the_photo():
    # 23:30 UTC on 12 Oct is 00:30 on 13 Oct in London (summer time)
    assert _reminder(when=datetime(2026, 10, 12, 23, 30, tzinfo=UTC)).due_on == date(2026, 10, 17)
    # after the clock change 23:30 UTC on 25 Oct is still 25 Oct in London
    assert _reminder(when=datetime(2026, 10, 25, 23, 30, tzinfo=UTC)).due_on == date(2026, 10, 29)


def test_no_reminder_without_a_prediction():
    assert reminders.schedule(_stored("a1", PHOTO, predicted=False), "Basil") is None


def test_no_reminder_for_an_action_with_no_words():
    stored = _stored("a1", PHOTO, action="repot")
    assert reminders.schedule(stored, "Basil") is None


def test_action_words_cover_every_scored_action():
    from herbtwin.scoring import RULES

    assert set(RULES) <= set(reminders.ACTION_WORDS)


def test_the_token_checks_out_only_for_its_answer_and_secret():
    t = reminders.sign("a1", "s")
    assert reminders.valid("a1", t, "s")
    assert not reminders.valid("a2", t, "s")
    assert not reminders.valid("a1", t, "other")
    assert not reminders.valid("a1", t[:-1], "s")
    assert not reminders.valid("a1", "", "s")
    assert not reminders.valid("a1", t, "")


def test_the_email_says_what_was_advised_and_how_to_stop():
    r = _reminder()
    e = reminders.email_for(r, "https://herbtwin.example", "tok")
    assert e.subject == "Time to check your Basil"
    assert "On 12 Oct you were told to water it." in e.text
    assert "https://herbtwin.example/" in e.text
    assert e.unsubscribe_url == "https://herbtwin.example/reminders/unsubscribe?a=a1&t=tok"
    assert e.unsubscribe_url in e.text and e.unsubscribe_url.replace("&", "&amp;") in e.html


def test_the_email_html_escapes_the_plant_name():
    e = reminders.email_for(_reminder(name="<b>Basil</b>"), "https://x.example", "tok")
    assert "<b>Basil</b>" not in e.html
    assert "&lt;b&gt;Basil&lt;/b&gt;" in e.html


# --- the daily run -------------------------------------------------------------------

TODAY = date(2026, 10, 16)
NOW = datetime(2026, 10, 16, 8, tzinfo=UTC)


class FakeAdmin:
    """The rows the job may see, kept as the database would after each call."""

    def __init__(self, *rows, later=(), gone=(), fail_mark=()):
        self.rows = {
            r.answer_id: r.model_copy(update={"user_id": "u-" + r.answer_id}) for r in rows
        }
        self.later, self.gone, self.fail_mark = set(later), set(gone), set(fail_mark)
        self.off: dict[str, str] = {}

    def due(self, today):
        return [
            r
            for r in self.rows.values()
            if r.due_on <= today and r.sent_at is None and r.off_at is None
        ]

    def followed_up(self, r):
        return r.answer_id in self.later

    def email_of(self, user_id):
        return None if user_id.removeprefix("u-") in self.gone else f"{user_id}@x.test"

    def mark_sent(self, answer_id, now):
        if answer_id in self.fail_mark:
            raise reminders.AdminError("down")
        self.rows[answer_id] = self.rows[answer_id].model_copy(update={"sent_at": now})

    def turn_off(self, answer_id, reason, now):
        r = self.rows[answer_id]
        if r.sent_at or r.off_at:
            return False
        self.rows[answer_id] = r.model_copy(update={"off_at": now})
        self.off[answer_id] = reason
        return True


class Outbox:
    def __init__(self, fail=()):
        self.sent: list[tuple[str, str, str]] = []
        self.fail = set(fail)

    def __call__(self, to, email, key):
        if key in self.fail:
            from herbtwin.mail import MailError

            raise MailError("Resend: HTTP 500")
        self.sent.append((to, email.subject, key))


def _due(aid, due=TODAY, last=date(2026, 10, 19)):
    return _reminder().model_copy(update={"answer_id": aid, "due_on": due, "last_on": last})


def _run(admin, outbox):
    return reminders.run(admin, outbox, TODAY, NOW, "https://x.test", "s")


def test_a_due_reminder_is_sent_once_and_a_rerun_sends_nothing():
    admin, outbox = FakeAdmin(_due("a1")), Outbox()
    assert _run(admin, outbox) == reminders.RunResult(sent=1)
    assert outbox.sent == [("u-a1@x.test", "Time to check your Basil", "reminder-a1")]
    assert admin.rows["a1"].sent_at == NOW
    assert _run(admin, outbox) == reminders.RunResult()
    assert len(outbox.sent) == 1


def test_not_yet_due_is_left_alone():
    admin, outbox = FakeAdmin(_due("a1", due=date(2026, 10, 17))), Outbox()
    assert _run(admin, outbox) == reminders.RunResult()
    assert outbox.sent == [] and admin.off == {}


def test_past_the_last_day_is_turned_off_not_sent():
    admin, outbox = FakeAdmin(_due("a1", due=date(2026, 10, 10), last=date(2026, 10, 15))), Outbox()
    assert _run(admin, outbox) == reminders.RunResult(skipped=1)
    assert outbox.sent == [] and admin.off == {"a1": "too_late"}


def test_a_later_photo_turns_it_off():
    admin, outbox = FakeAdmin(_due("a1"), later={"a1"}), Outbox()
    assert _run(admin, outbox) == reminders.RunResult(skipped=1)
    assert outbox.sent == [] and admin.off == {"a1": "followed_up"}


def test_a_deleted_account_turns_it_off_and_is_not_a_failure():
    admin, outbox = FakeAdmin(_due("a1"), gone={"a1"}), Outbox()
    assert _run(admin, outbox) == reminders.RunResult(skipped=1)
    assert admin.off == {"a1": "no_account"}


def test_one_failed_send_does_not_stop_the_rest_and_is_retried_tomorrow():
    admin = FakeAdmin(_due("a1"), _due("a2"), _due("a3"))
    outbox = Outbox(fail={"reminder-a2"})
    assert _run(admin, outbox) == reminders.RunResult(sent=2, failed=1)
    assert [k for _, _, k in outbox.sent] == ["reminder-a1", "reminder-a3"]
    assert admin.rows["a2"].sent_at is None and "a2" not in admin.off


def test_marking_sent_failing_counts_as_a_failure_and_the_run_goes_on():
    admin, outbox = FakeAdmin(_due("a1"), _due("a2"), fail_mark={"a1"}), Outbox()
    assert _run(admin, outbox) == reminders.RunResult(sent=1, failed=1)
    assert len(outbox.sent) == 2  # a rerun repeats a1's key, so Resend sends it once


# --- python -m herbtwin.reminders ------------------------------------------------------

ENV = {
    "HERBTWIN_SUPABASE_URL": "https://sb.test",
    "HERBTWIN_SUPABASE_SECRET_KEY": "sb_secret_x",
    "HERBTWIN_RESEND_API_KEY": "re_x",
    "HERBTWIN_MAIL_FROM": "herbtwin <r@x.test>",
    "HERBTWIN_REMINDER_SECRET": "s",
    "HERBTWIN_SITE_URL": "https://x.test",
}


@pytest.fixture
def wired(monkeypatch):
    """main() with the fake admin and outbox in place of Supabase and Resend."""
    parts = {"admin": FakeAdmin(), "outbox": Outbox(), "purges": []}
    monkeypatch.setattr(reminders, "_admin_from", lambda settings, client: parts["admin"])
    monkeypatch.setattr(
        reminders, "_purge_answers", lambda settings, client: parts["purges"].append(1)
    )
    monkeypatch.setattr(reminders, "_sender_from", lambda settings, client: parts["outbox"])
    monkeypatch.setattr(reminders, "_today", lambda: TODAY)
    return parts


@pytest.mark.parametrize("missing", sorted(set(ENV) - {"HERBTWIN_SITE_URL"}))
def test_main_refuses_to_start_without_a_setting(wired, caplog, missing):
    env = {k: v for k, v in ENV.items() if k != missing}
    assert reminders.main(env) == 2
    assert missing in caplog.text
    assert "sb_secret_x" not in caplog.text and "re_x" not in caplog.text


def test_main_exits_2_when_the_reminders_cannot_be_read(wired):
    class Down(FakeAdmin):
        def due(self, today):
            raise reminders.AdminError("down")

    wired["admin"] = Down()
    assert reminders.main(ENV) == 2


def test_main_exits_1_when_a_send_failed_and_logs_the_tally(wired, caplog):
    wired["admin"] = FakeAdmin(_due("a1"), _due("a2"))
    wired["outbox"] = Outbox(fail={"reminder-a2"})
    with caplog.at_level("INFO"):
        assert reminders.main(ENV) == 1
    assert "reminders: sent 1, skipped 0, failed 1" in caplog.text


def test_main_exits_0_when_all_went(wired, caplog):
    wired["admin"] = FakeAdmin(_due("a1"))
    with caplog.at_level("INFO"):
        assert reminders.main(ENV) == 0
    assert caplog.records[-1].getMessage() == "reminders: sent 1, skipped 0, failed 0"


@pytest.mark.filterwarnings("ignore::RuntimeWarning")  # runpy: the module is already imported
def test_python_dash_m_catches_the_admin_stores_errors(monkeypatch):
    # under `python -m` this file runs as __main__, a second copy of the module, while the
    # admin store raises herbtwin.reminders.AdminError: that copy must still catch it
    import runpy

    from herbtwin import answer_cache
    from herbtwin.adapters import reminder_admin

    class Down:
        def __init__(self, *args):
            pass

        def due(self, today):
            raise reminders.AdminError("down")

    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(reminder_admin, "SupabaseReminderAdmin", Down)
    monkeypatch.setattr(answer_cache.SupabaseAnswerCache, "purge", lambda self: 0)
    with pytest.raises(SystemExit) as stop:
        runpy.run_module("herbtwin.reminders", run_name="__main__")
    assert stop.value.code == 2


def test_each_run_purges_the_expired_answers_once(wired):
    wired["admin"] = FakeAdmin(_due("a1"))
    assert reminders.main(ENV) == 0
    assert wired["purges"] == [1]


def _purge_client(reply: httpx.Response | Exception, seen: list[httpx.Request]) -> httpx.Client:
    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if isinstance(reply, Exception):
            raise reply
        return reply

    return httpx.Client(transport=httpx.MockTransport(handle))


def test_the_purge_calls_purge_answer_cache_and_logs_the_count(caplog):
    seen: list[httpx.Request] = []
    client = _purge_client(httpx.Response(200, json=3), seen)
    with caplog.at_level("INFO"):
        reminders._purge_answers(reminders.load_settings(ENV), client)
    assert [r.url.path for r in seen] == ["/rest/v1/rpc/purge_answer_cache"]
    assert seen[0].headers["authorization"] == "Bearer sb_secret_x"
    assert "purged 3 expired answers" in caplog.text


@pytest.mark.parametrize(
    "reply", [httpx.Response(500, json={}), httpx.ConnectError("down")], ids=["500", "down"]
)
def test_a_failed_purge_is_logged_and_never_raises(caplog, reply):
    reminders._purge_answers(reminders.load_settings(ENV), _purge_client(reply, []))
    assert "could not purge the expired answers" in caplog.text
    assert "sb_secret_x" not in caplog.text
