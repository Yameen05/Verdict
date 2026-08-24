"""SMTP delivery must not hand credentials to an unverified server."""

from __future__ import annotations

import ssl

import pytest

from app.config import get_settings
from app.services import mailer


class _FakeSMTP:
    """Records what send_email did to the connection."""

    instances: list[_FakeSMTP] = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.starttls_context: ssl.SSLContext | None = None
        self.starttls_called = False
        self.login_args: tuple[str, str] | None = None
        self.sent = False
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.starttls_called = True
        self.starttls_context = context

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message):
        self.sent = True


@pytest.fixture
def smtp(monkeypatch):
    _FakeSMTP.instances = []
    monkeypatch.setattr(mailer.smtplib, "SMTP", _FakeSMTP)
    return _FakeSMTP


def _configure(monkeypatch, **overrides):
    env = {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_FROM": "verdict@example.com",
        "SMTP_USERNAME": "verdict",
        "SMTP_PASSWORD": "hunter2hunter2",
        "SMTP_STARTTLS": "true",
    }
    env.update(overrides)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


def test_starttls_uses_a_verifying_context(monkeypatch, smtp):
    """The stdlib default for starttls() is check_hostname=False/CERT_NONE."""
    _configure(monkeypatch)
    assert mailer.send_email("user@example.com", "Subject", "Body") is True

    connection = smtp.instances[0]
    assert connection.starttls_called
    context = connection.starttls_context
    assert isinstance(context, ssl.SSLContext)
    assert context.check_hostname is True
    assert context.verify_mode is ssl.CERT_REQUIRED
    assert connection.login_args == ("verdict", "hunter2hunter2")
    assert connection.sent


def test_refuses_to_send_credentials_over_a_cleartext_session(monkeypatch, smtp):
    _configure(monkeypatch, SMTP_STARTTLS="false")
    assert mailer.send_email("user@example.com", "Subject", "Body") is False
    assert smtp.instances == []


def test_sends_without_tls_only_when_no_credentials_are_configured(monkeypatch, smtp):
    """A local relay with no auth stays supported."""
    _configure(monkeypatch, SMTP_STARTTLS="false", SMTP_USERNAME="")
    assert mailer.send_email("user@example.com", "Subject", "Body") is True

    connection = smtp.instances[0]
    assert connection.starttls_called is False
    assert connection.login_args is None
    assert connection.sent


def test_send_failure_never_propagates(monkeypatch):
    _configure(monkeypatch)

    def explode(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(mailer.smtplib, "SMTP", explode)
    assert mailer.send_email("user@example.com", "Subject", "Body") is False


def test_no_send_when_smtp_is_unconfigured(monkeypatch, smtp):
    _configure(monkeypatch, SMTP_HOST="")
    assert mailer.send_email("user@example.com", "Subject", "Body") is False
    assert smtp.instances == []
