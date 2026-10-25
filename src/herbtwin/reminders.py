"""Re-photo reminder emails (spec section 7, D65). Ticking the box under a signed-in
answer stores one reminder, due halfway through the main action's check window (the
window "Did you do it?" uses), so at least half of it is left to take the photo. A daily
Nebius job sends the day's reminders through Resend: `python -m herbtwin.reminders`."""

from __future__ import annotations

import hashlib
import hmac
import html
import logging
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal, Protocol
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, field_validator

from herbtwin.config import Settings, load_settings
from herbtwin.history import StoredAnswer, utc
from herbtwin.mail import MailError, send_mail

log = logging.getLogger(__name__)

UK = ZoneInfo("Europe/London")
OffReason = Literal["unsubscribed", "followed_up", "too_late", "no_account"]
# the main action, as the email says it: "you were told to <words>" (scored actions only)
ACTION_WORDS = {
    "water": "water it",
    "dont_water": "hold off watering",
    "leave_normal": "leave it",
    "shelter": "protect it",
    "treat_or_remove": "treat it",
    "prune": "cut it back",
    "isolate": "keep it apart",
    "move_light": "move it to better light",
    "feed": "feed it",
}


class Reminder(BaseModel):
    answer_id: str
    user_id: str | None = None  # filled by the database; None when the app builds one
    plant_id: str
    plant_name: str
    action: str
    taken_at: datetime
    due_on: date
    last_on: date
    sent_at: datetime | None = None
    off_at: datetime | None = None

    @field_validator("answer_id")
    @classmethod
    def _app_form(cls, v: str) -> str:
        """Answer ids in the app's 32-hex form; Postgres hands back hyphens."""
        try:
            return uuid.UUID(v).hex
        except ValueError:
            return v

    @field_validator("taken_at")
    @classmethod
    def _zoned(cls, v: datetime) -> datetime:
        return utc(v)


@dataclass(frozen=True)
class Email:
    subject: str
    text: str
    html: str
    unsubscribe_url: str


def schedule(stored: StoredAnswer, plant_name: str) -> Reminder | None:
    """The reminder for this answer, or None when its main action has no check window."""
    p = stored.answer.prediction if stored.answer else None
    if p is None or p.action not in ACTION_WORDS:
        return None
    lo, hi = p.window_days
    day = stored.taken_at.astimezone(UK).date()
    return Reminder(
        answer_id=stored.id,
        plant_id=stored.plant_id,
        plant_name=plant_name,
        action=ACTION_WORDS[p.action],
        taken_at=stored.taken_at,
        due_on=day + timedelta(days=(lo + hi) // 2),
        last_on=day + timedelta(days=hi),
    )


def sign(answer_id: str, secret: str) -> str:
    return hmac.new(secret.encode(), f"reminder:{answer_id}".encode(), hashlib.sha256).hexdigest()


def valid(answer_id: str, token: str, secret: str) -> bool:
    if not secret or not token:
        return False
    return hmac.compare_digest(token.encode(), sign(answer_id, secret).encode())


def email_for(r: Reminder, site_url: str, token: str) -> Email:
    site = site_url.rstrip("/")
    stop = f"{site}/reminders/unsubscribe?{urlencode({'a': r.answer_id, 't': token})}"
    told = r.taken_at.astimezone(UK).date()
    said = f"On {told.day} {told:%b} you were told to {r.action}."
    subject = f"Time to check your {r.plant_name}"
    text = (
        f"{subject}.\n\n{said} A new photo shows whether it worked.\n\n"
        f"Take one at {site}/\n\n"
        f"You asked for this one email. Stop it: {stop}\n"
    )
    e = html.escape
    body = (
        f"<p>{e(subject)}.</p><p>{e(said)} A new photo shows whether it worked.</p>"
        f'<p><a href="{e(site)}/">Take a photo</a></p>'
        f'<p style="color:#666;font-size:small">You asked for this one email. '
        f'<a href="{e(stop)}">Stop it</a>.</p>'
    )
    return Email(subject=subject, text=text, html=body, unsubscribe_url=stop)


class AdminError(Exception):
    """The reminders could not be read or written with the secret key."""


class ReminderAdmin(Protocol):
    def due(self, today: date) -> list[Reminder]: ...  # due_on <= today, not sent, not off
    def followed_up(self, r: Reminder) -> bool: ...  # a later photo of the same plant
    def email_of(self, user_id: str) -> str | None: ...  # None: the account is gone
    def mark_sent(self, answer_id: str, now: datetime) -> None: ...
    # True when this call turned it off; False when it was already sent or off
    def turn_off(self, answer_id: str, reason: OffReason, now: datetime) -> bool: ...


Send = Callable[[str, Email, str], None]  # (to, email, idempotency key); raises MailError


@dataclass
class RunResult:
    sent: int = 0
    skipped: int = 0
    failed: int = 0


def _skip_reason(admin: ReminderAdmin, r: Reminder, today: date) -> OffReason | None:
    if today > r.last_on:
        return "too_late"
    if admin.followed_up(r):
        return "followed_up"
    return None


def run(
    admin: ReminderAdmin, send: Send, today: date, now: datetime, site_url: str, secret: str
) -> RunResult:
    """Send each reminder due today, once. One failure is logged and the rest go on; a
    reminder that failed stays due, so tomorrow's run tries again until its last day."""
    out = RunResult()
    for r in admin.due(today):
        try:
            reason = _skip_reason(admin, r, today)
            to = None if reason else admin.email_of(r.user_id or "")
            if reason is None and to is None:
                reason = "no_account"
            if reason is not None:
                admin.turn_off(r.answer_id, reason, now)
                log.info("reminder %s off: %s", r.answer_id, reason)
                out.skipped += 1
                continue
            send(to, email_for(r, site_url, sign(r.answer_id, secret)), f"reminder-{r.answer_id}")
            admin.mark_sent(r.answer_id, now)  # unmarked, a rerun repeats the key: one mail
            out.sent += 1
        except (MailError, AdminError):
            log.exception("reminder %s failed", r.answer_id)
            out.failed += 1
    return out


# what the job cannot run without (names only are ever logged)
REQUIRED = (
    ("HERBTWIN_SUPABASE_URL", "supabase_url"),
    ("HERBTWIN_SUPABASE_SECRET_KEY", "supabase_secret_key"),
    ("HERBTWIN_RESEND_API_KEY", "resend_api_key"),
    ("HERBTWIN_MAIL_FROM", "mail_from"),
    ("HERBTWIN_REMINDER_SECRET", "reminder_secret"),
)


def _today() -> date:
    return datetime.now(UK).date()


def _admin_from(settings: Settings, client: httpx.Client) -> ReminderAdmin:
    from herbtwin.adapters.reminder_admin import SupabaseReminderAdmin

    return SupabaseReminderAdmin(
        settings.supabase_url or "", settings.supabase_secret_key or "", client
    )


def _sender_from(settings: Settings, client: httpx.Client) -> Send:
    key, sender = settings.resend_api_key or "", settings.mail_from or ""

    def send(to: str, e: Email, idempotency_key: str) -> None:
        send_mail(
            key,
            sender,
            to,
            e.subject,
            e.text,
            client,
            html=e.html,
            headers={
                "List-Unsubscribe": f"<{e.unsubscribe_url}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            },
            idempotency_key=idempotency_key,
        )

    return send


def _purge_answers(settings: Settings, client: httpx.Client) -> None:
    """Delete the answers past their 24 hours (answer_cache), once a run. Best effort: a
    failure is logged and never stops or reddens the reminders."""
    from herbtwin.answer_cache import SupabaseAnswerCache

    cache = SupabaseAnswerCache(
        settings.supabase_url or "",
        settings.supabase_secret_key or "",
        lambda: datetime.now(UK),
        client,
    )
    gone = cache.purge()
    if gone is None:
        log.error("reminders: could not purge the expired answers")
    else:
        log.info("reminders: purged %d expired answers", gone)


def main(env: Mapping[str, str] | None = None) -> int:
    """The daily job: 0 all sent, 1 some failed (the run shows red), 2 could not start."""
    try:
        settings = load_settings(env)
    except ValueError:
        log.exception("reminders: bad settings")
        return 2
    missing = [name for name, attr in REQUIRED if not getattr(settings, attr)]
    if missing:
        log.error("reminders: not set: %s", ", ".join(missing))
        return 2
    with httpx.Client(timeout=10) as client:
        _purge_answers(settings, client)
        admin, send = _admin_from(settings, client), _sender_from(settings, client)
        try:
            result = run(
                admin,
                send,
                _today(),
                datetime.now(UK),
                settings.site_url,
                settings.reminder_secret or "",
            )
        except AdminError:
            log.exception("reminders: could not read the reminders")
            return 2
    log.info(
        "reminders: sent %d, skipped %d, failed %d", result.sent, result.skipped, result.failed
    )
    return 1 if result.failed else 0


if __name__ == "__main__":
    # run the imported module's main, not this __main__ copy's: the admin store raises
    # herbtwin.reminders.AdminError, which a second copy of the class would not catch
    from herbtwin import reminders as _module

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    raise SystemExit(_module.main())
