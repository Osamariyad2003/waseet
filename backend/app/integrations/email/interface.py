"""The EmailGateway contract.

Services depend on this Protocol, never on smtplib, so notifications can be
tested without a network call and the transport (Gmail SMTP, a console log, a
test spy) can be swapped behind it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class EmailMessage:
    """One outbound email. `to` is one or more recipient addresses."""

    to: tuple[str, ...]
    subject: str
    body: str

    def __post_init__(self) -> None:
        if not self.to:
            raise ValueError("an email needs at least one recipient")


@runtime_checkable
class EmailGateway(Protocol):
    """Outbound email. Notifications only — never anything transactional."""

    async def send(self, message: EmailMessage) -> bool:
        """Deliver the message. Returns True on success, False on a handled
        failure — it never raises, so a notification can never break the
        action that triggered it."""
        ...
