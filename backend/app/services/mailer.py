"""Best-effort SMTP notifications.

Email is optional: when SMTP_HOST is blank every send is a silent no-op, and a
failed send never breaks the caller — alerts still trigger and show in the UI.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from app.config import get_settings
from app.observability.logging import get_logger

log = get_logger(__name__)


def email_configured() -> bool:
    settings = get_settings()
    return bool(settings.smtp_host.strip() and settings.smtp_from.strip())


def send_email(to: str, subject: str, body: str) -> bool:
    """Send one plain-text email synchronously. Returns True on success.

    Callers run this in a thread (asyncio.to_thread) — smtplib blocks.
    """
    if not email_configured():
        return False
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.smtp_from.strip()
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    username = settings.smtp_username.strip()
    if username and not settings.smtp_starttls:
        # login() would put the password on the wire in cleartext.
        log.error("email_send_refused_cleartext_login", extra={"subject": subject})
        return False
    try:
        with smtplib.SMTP(settings.smtp_host.strip(), settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_starttls:
                # starttls() with no context falls back to an unverified stdlib
                # context (check_hostname off, CERT_NONE), which would leave the
                # SMTP password and every password-reset link MITM-able.
                smtp.starttls(context=ssl.create_default_context())
            if username:
                smtp.login(username, settings.smtp_password)
            smtp.send_message(message)
        return True
    except Exception:  # noqa: BLE001 - notification failure must never propagate
        log.exception("email_send_failed", extra={"subject": subject})
        return False
