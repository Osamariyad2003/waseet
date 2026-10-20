"""Deal and acceptance-criteria data access.

Repositories do not commit. The service owns the transaction, because a
state change, its money movement and its audit entry have to land together.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import DealState
from app.models.deal import AcceptanceCriterion, Deal


class DealRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, deal: Deal) -> Deal:
        self._session.add(deal)
        return deal

    async def get(self, deal_id: uuid.UUID) -> Deal | None:
        result = await self._session.execute(
            select(Deal)
            .where(Deal.id == deal_id)
            .options(
                selectinload(Deal.criteria),
                selectinload(Deal.deliverables),
                selectinload(Deal.verification_reports),
            )
        )
        return result.unique().scalar_one_or_none()

    async def get_for_update(self, deal_id: uuid.UUID) -> Deal | None:
        """Lock the deal row for the duration of the transaction.

        Every money-moving path loads the deal this way, so two concurrent
        requests — a webhook replay racing the verification that triggered
        it — cannot both read FUNDED and both decide to pay.
        """
        result = await self._session.execute(
            select(Deal).where(Deal.id == deal_id).with_for_update()
        )
        deal = result.scalar_one_or_none()
        if deal is not None:
            # Relationships are loaded separately: FOR UPDATE and an outer
            # join to a nullable side do not mix on Postgres.
            await self._session.refresh(deal, ["criteria", "deliverables", "verification_reports"])
        return deal

    async def get_by_order_id(self, order_id: str) -> Deal | None:
        result = await self._session.execute(select(Deal).where(Deal.paypal_order_id == order_id))
        return result.scalar_one_or_none()

    async def get_by_capture_id(self, capture_id: str) -> Deal | None:
        result = await self._session.execute(
            select(Deal).where(Deal.paypal_capture_id == capture_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self, user_id: uuid.UUID, *, state: DealState | None = None
    ) -> Sequence[Deal]:
        """Deals the user is a party to, newest first."""
        query = (
            select(Deal)
            .where(or_(Deal.buyer_id == user_id, Deal.seller_id == user_id))
            .order_by(Deal.created_at.desc())
            .options(selectinload(Deal.criteria))
        )
        if state is not None:
            query = query.where(Deal.state == state)
        result = await self._session.execute(query)
        return result.unique().scalars().all()

    async def list_by_state(self, state: DealState) -> Sequence[Deal]:
        """Used by the reviewer queue (DISPUTED deals)."""
        result = await self._session.execute(
            select(Deal)
            .where(Deal.state == state)
            .order_by(Deal.updated_at.desc())
            .options(selectinload(Deal.criteria))
        )
        return result.unique().scalars().all()

    # --- acceptance criteria ---------------------------------------------

    def add_criteria(self, deal_id: uuid.UUID, texts: Sequence[str]) -> list[AcceptanceCriterion]:
        criteria = [
            AcceptanceCriterion(deal_id=deal_id, text=text, position=position)
            for position, text in enumerate(texts)
        ]
        self._session.add_all(criteria)
        return criteria

    async def list_criteria(self, deal_id: uuid.UUID) -> Sequence[AcceptanceCriterion]:
        result = await self._session.execute(
            select(AcceptanceCriterion)
            .where(AcceptanceCriterion.deal_id == deal_id)
            .order_by(AcceptanceCriterion.position)
        )
        return result.scalars().all()

    async def count_criteria(self, deal_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(AcceptanceCriterion)
            .where(AcceptanceCriterion.deal_id == deal_id)
        )
        return int(result.scalar_one())
