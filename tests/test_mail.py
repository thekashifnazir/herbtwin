"""Mail through Resend (the budget warning, spec D60)."""

import json

import httpx
import pytest
import respx

from herbtwin.config import load_settings
from herbtwin.mail import RESEND_URL, MailError, mailer_from, send_mail


@respx.mock
def test_send_mail_request_shape():
    route = respx.post(RESEND_URL).mock(return_value=httpx.Response(200, json={"id": "e1"}))
    with httpx.Client() as client:
        send_mail("re_key", "herbtwin <a@x.test>", "kash@x.test", "Subj", "Body", client)
    req = route.calls.last.request
    assert req.headers["authorization"] == "Bearer re_key"
    assert json.loads(req.content) == {
        "from": "herbtwin <a@x.test>",
        "to": ["kash@x.test"],
        "subject": "Subj",
        "text": "Body",
    }


@respx.mock
def test_send_mail_refused_raises_mail_error():
    respx.post(RESEND_URL).mock(return_value=httpx.Response(422, json={"message": "bad from"}))
    with httpx.Client() as client, pytest.raises(MailError):
        send_mail("k", "f@x.test", "t@x.test", "s", "b", client)


@respx.mock
def test_send_mail_transport_error_raises_mail_error():
    respx.post(RESEND_URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    with httpx.Client() as client, pytest.raises(MailError):
        send_mail("k", "f@x.test", "t@x.test", "s", "b", client)


def test_mailer_needs_key_sender_and_address():
    assert mailer_from(load_settings({})) is None
    partial = {"HERBTWIN_RESEND_API_KEY": "k", "HERBTWIN_MAIL_FROM": "f@x.test"}
    assert mailer_from(load_settings(partial)) is None


@respx.mock
def test_mailer_from_settings_sends_to_the_alert_address():
    route = respx.post(RESEND_URL).mock(return_value=httpx.Response(200, json={"id": "e1"}))
    s = load_settings(
        {
            "HERBTWIN_RESEND_API_KEY": "k",
            "HERBTWIN_MAIL_FROM": "herbtwin <alerts@x.test>",
            "HERBTWIN_ALERT_EMAIL": "kash@x.test",
        }
    )
    mailer_from(s)("Subj", "Body")
    assert json.loads(route.calls.last.request.content)["to"] == ["kash@x.test"]


def test_mailer_gives_up_fast(monkeypatch):
    from herbtwin import mail as mail_module

    seen = {}
    real = httpx.Client

    def spy(**kw):
        seen.update(kw)
        return real(**kw)

    monkeypatch.setattr(mail_module.httpx, "Client", spy)
    mailer_from(
        load_settings(
            {
                "HERBTWIN_RESEND_API_KEY": "k",
                "HERBTWIN_MAIL_FROM": "f@x.test",
                "HERBTWIN_ALERT_EMAIL": "t@x.test",
            }
        )
    )
    assert seen["timeout"] <= 3  # the warning is sent inside a visitor's request


@respx.mock
def test_send_mail_carries_html_headers_and_an_idempotency_key():
    route = respx.post(RESEND_URL).mock(return_value=httpx.Response(200, json={"id": "e1"}))
    with httpx.Client() as client:
        send_mail(
            "k",
            "f@x.test",
            "t@x.test",
            "s",
            "b",
            client,
            html="<p>b</p>",
            headers={"List-Unsubscribe": "<https://x.test/u>"},
            idempotency_key="reminder-a1",
        )
    req = route.calls.last.request
    assert req.headers["idempotency-key"] == "reminder-a1"
    body = json.loads(req.content)
    assert body["html"] == "<p>b</p>"
    assert body["headers"] == {"List-Unsubscribe": "<https://x.test/u>"}
    assert body["text"] == "b"
