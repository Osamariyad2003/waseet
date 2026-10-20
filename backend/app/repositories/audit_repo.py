"""Append-only audit log access (FR-10).

This repository exposes append and read. There is deliberately no update or
delete method, and the database rejects both anyway.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import Actor, DealState
from app.models.audit import AuditLogEntry


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def append(
        self,
        *,
        deal_id: uuid.UUID,
        from_state: DealState | None,
        to_state: DealState,
        actor: Actor,
        event: str,
        reason: str,
        paypal_reference: str | None = None,
    ) -> AuditLogEntry:
        """Record one transition or decision.

        Not committed here: the caller commits it in the same transaction as
        the state change and money movement it describes.
        """
        entry = AuditLogEntry(
            deal_id=deal_id,
            from_state=from_state,
            to_state=to_state,
            actor=actor,
            event=event,
            reason=reason,
            paypal_reference=paypal_reference,
        )
        self._session.add(entry)
        return entry

    async def list_for_deal(self, deal_id: uuid.UUID) -> Sequence[AuditLogEntry]:
        """The deal's history, oldest first — the timeline reads this."""
        result = await self._session.execute(
            select(AuditLogEntry)
            .where(AuditLogEntry.deal_id == deal_id)
            .order_by(AuditLogEntry.created_at, AuditLogEntry.id)
        )
        return result.scalars().all()
