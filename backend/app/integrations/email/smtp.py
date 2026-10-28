"""Gmail (or any SMTP) email transport.

Uses the standard library's smtplib run in a worker thread, so no extra
dependency and nothing blocks the event loop. Gmail needs an App Password
(with 2FA enabled), never the account password — stated in the README.

It never raises: a notification that cannot be sent is logged and swallowed,
because an email failure must never break the action that triggered it.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage as MimeEmailMessage

import structlog

from app.config import Settings
from app.integrations.email.interface import EmailMessage

logger = structlog.get_logger(__name__)


class SmtpEmailGateway:
    """Sends through an SMTP server (Gmail by default)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send(self, message: EmailMessage) -> bool:
        try:
            await asyncio.to_thread(self._send_sync, message)
        except Exception as exc:  # noqa: BLE001 — nothing may escape to the caller
            logger.warning(
                "email.send_failed",
                error=f"{type(exc).__name__}",
                recipients=len(message.to),
            )
            return False
        logger.info("email.sent", subject=message.subject, recipients=len(message.to))
        return True

    def _send_sync(self, message: EmailMessage) -> None:
        mime = MimeEmailMessage()
        mime["From"] = self._settings.email_from_address
        mime["To"] = ", ".join(message.to)
        mime["Subject"] = message.subject
        mime.set_content(message.body)

        host = self._settings.smtp_host
        port = self._settings.smtp_port
        username = self._settings.smtp_username
        password = self._settings.smtp_password.get_secret_value()

        timeout = 15
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=timeout) as server:
                server.login(username, password)
                server.send_message(mime)
        else:
            with smtplib.SMTP(host, port, timeout=timeout) as server:
                if self._settings.smtp_starttls:
                    server.starttls()
                server.login(username, password)
                server.send_message(mime)
