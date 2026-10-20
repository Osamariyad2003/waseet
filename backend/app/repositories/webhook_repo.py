"""Webhook event data access — the database half of webhook idempotency."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook import WebhookEvent


class WebhookRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(
        self, *, event_id: str, event_type: str, payload: dict[str, Any]
    ) -> WebhookEvent | None:
        """Record this event id, or return None if it was already recorded.

        A single INSERT ... ON CONFLICT DO NOTHING is the claim: whichever
        request wins the unique index processes the event, and a redelivery
        gets None and stops there. Checking first and then inserting would
        leave a race between the two statements, which is exactly the window
        a duplicate PayPal delivery would slip through.
        """
        dialect = self._session.bind.dialect.name if self._session.bind else "postgresql"
        insert = sqlite_insert if dialect == "sqlite" else pg_insert

        statement = (
            insert(WebhookEvent)
            .values(event_id=event_id, event_type=event_type, payload=payload)
            .on_conflict_do_nothing(index_elements=["event_id"])
            .returning(WebhookEvent)
        )
        result = await self._session.execute(statement)
        return result.scalars().first()

    async def get(self, event_id: str) -> WebhookEvent | None:
        result = await self._session.execute(
            select(WebhookEvent).where(WebhookEvent.event_id == event_id)
        )
        return result.scalars().first()

    @staticmethod
    def mark_processed(event: WebhookEvent, outcome: str) -> WebhookEvent:
        """Record what the event actually caused, so an ignored event is
        still explainable in the demo."""
        event.processed_at = datetime.now(UTC)
        event.outcome = outcome[:255]
        return event
