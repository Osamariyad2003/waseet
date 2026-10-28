"""Deliverable data access."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import DeliverableType
from app.models.deliverable import Deliverable


class DeliverableRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(
        self,
        *,
        deal_id: uuid.UUID,
        type_: DeliverableType,
        content_ref: str,
        note: str | None = None,
        milestone_id: uuid.UUID | None = None,
    ) -> Deliverable:
        deliverable = Deliverable(
            deal_id=deal_id,
            milestone_id=milestone_id,
            type=type_,
            content_ref=content_ref,
            note=note,
        )
        self._session.add(deliverable)
        return deliverable

    async def get_latest_for_milestone(self, milestone_id: uuid.UUID) -> Deliverable | None:
        result = await self._session.execute(
            select(Deliverable)
            .where(Deliverable.milestone_id == milestone_id)
            .order_by(Deliverable.submitted_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest(self, deal_id: uuid.UUID) -> Deliverable | None:
        """The submission a verification judges: the most recent one."""
        result = await self._session.execute(
            select(Deliverable)
            .where(Deliverable.deal_id == deal_id)
            .order_by(Deliverable.submitted_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_for_deal(self, deal_id: uuid.UUID) -> Sequence[Deliverable]:
        result = await self._session.execute(
            select(Deliverable)
            .where(Deliverable.deal_id == deal_id)
            .order_by(Deliverable.submitted_at)
        )
        return result.scalars().all()
