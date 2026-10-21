"""Mail through Resend: the live budget warning to Kash (spec D60) and re-photo reminders (D65)."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from herbtwin.config import Settings

RESEND_URL = "https://api.resend.com/emails"

Mailer = Callable[[str, str], None]  # (subject, text) to the alert address


class MailError(Exception):
    """Resend did not take the mail."""


def send_mail(
    api_key: str,
    sender: str,
    to: str,
    subject: str,
    text: str,
    client: httpx.Client,
    *,
    html: str | None = None,
    headers: dict[str, str] | None = None,
    idempotency_key: str | None = None,
) -> None:
    """Send one mail. With an idempotency key Resend sends it once, however often asked
    within its 24 hours, and returns the first send to a repeat."""
    body: dict = {"from": sender, "to": [to], "subject": subject, "text": text}
    if html is not None:
        body["html"] = html
    if headers:
        body["headers"] = headers
    request_headers = {"Authorization": f"Bearer {api_key}"}
    if idempotency_key:
        request_headers["Idempotency-Key"] = idempotency_key
    try:
        r = client.post(RESEND_URL, headers=request_headers, json=body)
    except httpx.HTTPError as e:
        raise MailError(f"Resend: {type(e).__name__}") from e
    if not r.is_success:
        raise MailError(f"Resend: HTTP {r.status_code}")


def mailer_from(settings: Settings) -> Mailer | None:
    """A sender to the alert address, or None unless the key, sender and address are set."""
    key, sender, to = settings.resend_api_key, settings.mail_from, settings.alert_email
    if not (key and sender and to):
        return None
    client = httpx.Client(timeout=3)  # the warning is sent in a request: give up fast

    def mail(subject: str, text: str) -> None:
        send_mail(key, sender, to, subject, text, client)

    return mail
