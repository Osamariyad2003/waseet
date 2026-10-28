"""Lifecycle email notifications.

Builds a plain, honest email for each event a party cares about and hands it
to the email gateway. Everything here is best-effort: it is invoked as a
FastAPI background task after the triggering action has already committed, and
the gateway never raises, so a failed or slow email can neither roll back a
deal nor delay a response.
"""

from __future__ import annotations

import structlog

from app.config import Settings
from app.integrations.email.interface import EmailGateway, EmailMessage
from app.models.deal import Deal
from app.models.milestone import Milestone

logger = structlog.get_logger(__name__)

SANDBOX_NOTE = "This is a Waseet sandbox demo — no real money moves."


class NotificationService:
    def __init__(self, *, settings: Settings, email: EmailGateway) -> None:
        self._settings = settings
        self._email = email

    # --- events -----------------------------------------------------------

    async def deal_funded(self, deal: Deal) -> None:
        await self._send(
            (deal.seller.email,),
            f"Waseet: “{deal.title}” is funded — submit your work",
            (
                f"{self._greet(deal.seller)}\n\n"
                f"The buyer has funded “{deal.title}” "
                f"({self._money(deal)}). The money is held in escrow.\n"
                "Submit your deliverable so the AI can verify it against the "
                "agreed checklist.\n\n"
                f"{self._link(deal)}"
            ),
        )

    async def deliverable_submitted(self, deal: Deal) -> None:
        await self._send(
            (deal.buyer.email,),
            f"Waseet: the seller delivered “{deal.title}”",
            (
                f"{self._greet(deal.buyer)}\n\n"
                f"The seller has submitted their work for “{deal.title}”. "
                "The AI verifier checks it against the checklist you both "
                "confirmed; you can contest before it pays out.\n\n"
                f"{self._link(deal)}"
            ),
        )

    async def released(self, deal: Deal) -> None:
        await self._send(
            (deal.buyer.email, deal.seller.email),
            f"Waseet: funds released for “{deal.title}”",
            (
                f"Good news — “{deal.title}” passed verification and "
                f"{self._money(deal)} was released to the seller.\n\n"
                f"{self._link(deal)}"
            ),
        )

    async def milestone_released(self, deal: Deal, milestone: Milestone) -> None:
        await self._send(
            (deal.buyer.email, deal.seller.email),
            f"Waseet: milestone “{milestone.title}” released",
            (
                f"The milestone “{milestone.title}” of “{deal.title}” passed "
                f"verification and its {milestone.amount} {deal.currency} was "
                "released to the seller.\n\n"
                f"{self._link(deal)}"
            ),
        )

    async def disputed(self, deal: Deal) -> None:
        await self._send(
            (deal.buyer.email, deal.seller.email),
            f"Waseet: “{deal.title}” is under review",
            (
                f"“{deal.title}” did not pass automatic verification, so the "
                "funds stay held and a human reviewer will decide the outcome. "
                "No action is needed from you right now.\n\n"
                f"{self._link(deal)}"
            ),
        )

    # --- plumbing ---------------------------------------------------------

    async def _send(self, to: tuple[str, ...], subject: str, body: str) -> None:
        recipients = tuple(address for address in to if address)
        if not recipients:
            return
        try:
            await self._email.send(
                EmailMessage(to=recipients, subject=subject, body=f"{body}\n\n— {SANDBOX_NOTE}")
            )
        except Exception as exc:  # noqa: BLE001 — a notification must never surface
            logger.warning("notification.failed", error=type(exc).__name__)

    def _link(self, deal: Deal) -> str:
        return f"View the deal: {self._settings.app_base_url.rstrip('/')}/en/deals/{deal.id}"

    @staticmethod
    def _money(deal: Deal) -> str:
        return f"{deal.amount} {deal.currency}"

    @staticmethod
    def _greet(user) -> str:
        name = (user.full_name or "").strip() or "there"
        return f"Hi {name},"
