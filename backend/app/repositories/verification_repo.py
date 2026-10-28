"""Verification report data access."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import DecidedBy, Verdict
from app.models.verification import VerificationReport


class VerificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(
        self,
        *,
        deal_id: uuid.UUID,
        deliverable_id: uuid.UUID | None,
        verdict: Verdict,
        confidence: Decimal,
        reasoning: str,
        per_criterion: list[dict[str, Any]],
        decided_by: DecidedBy,
        recommendation: str | None = None,
        milestone_id: uuid.UUID | None = None,
        intake: dict[str, Any] | None = None,
    ) -> VerificationReport:
        report = VerificationReport(
            deal_id=deal_id,
            milestone_id=milestone_id,
            deliverable_id=deliverable_id,
            verdict=verdict,
            confidence=confidence,
            reasoning=reasoning,
            per_criterion=per_criterion,
            decided_by=decided_by,
            recommendation=recommendation,
            intake=intake,
        )
        self._session.add(report)
        return report

    async def get_latest_for_milestone(
        self, milestone_id: uuid.UUID
    ) -> VerificationReport | None:
        result = await self._session.execute(
            select(VerificationReport)
            .where(VerificationReport.milestone_id == milestone_id)
            .order_by(VerificationReport.decided_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def get_latest(self, deal_id: uuid.UUID) -> VerificationReport | None:
        result = await self._session.execute(
            select(VerificationReport)
            .where(VerificationReport.deal_id == deal_id)
            .order_by(VerificationReport.decided_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def get_latest_ai(self, deal_id: uuid.UUID) -> VerificationReport | None:
        """The AI's own verification, ignoring any later human decision."""
        result = await self._session.execute(
            select(VerificationReport)
            .where(
                VerificationReport.deal_id == deal_id,
                VerificationReport.decided_by == DecidedBy.AI,
            )
            .order_by(VerificationReport.decided_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def list_for_deal(self, deal_id: uuid.UUID) -> Sequence[VerificationReport]:
        result = await self._session.execute(
            select(VerificationReport)
            .where(VerificationReport.deal_id == deal_id)
            .order_by(VerificationReport.decided_at)
        )
        return result.scalars().all()

    async def count_for_deal(self, deal_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(VerificationReport)
            .where(VerificationReport.deal_id == deal_id)
        )
        return int(result.scalar_one())
