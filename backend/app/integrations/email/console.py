"""A console email gateway: logs what would have been sent, sends nothing.

The default when email is not configured, so the product can be demonstrated
(and tested) without Gmail credentials — the notification shows up in the
server log instead of an inbox.
"""

from __future__ import annotations

import structlog

from app.integrations.email.interface import EmailMessage

logger = structlog.get_logger(__name__)


class ConsoleEmailGateway:
    async def send(self, message: EmailMessage) -> bool:
        logger.info(
            "email.console",
            to=", ".join(message.to),
            subject=message.subject,
            preview=message.body[:140],
        )
        return True
