"""Deal and acceptance-criteria data access.

Repositories do not commit. The service owns the transaction, because a
state change, its money movement and its audit entry have to land together.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import DealState
from app.models.deal import AcceptanceCriterion, Deal
from app.models.milestone import Milestone


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
            await self._session.refresh(
                deal, ["criteria", "deliverables", "verification_reports", "milestones"]
            )
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

    async def list_all(self) -> Sequence[Deal]:
        """Every deal, newest first — the reviewer's admin grid reads this."""
        result = await self._session.execute(
            select(Deal).order_by(Deal.updated_at.desc()).options(selectinload(Deal.criteria))
        )
        return result.unique().scalars().all()

    async def state_totals(self) -> dict[DealState, tuple[int, Decimal]]:
        """Count and summed amount per state, for the dashboard's stat tiles.

        Aggregated in one query rather than loading every deal. Amounts are
        summed as-is; mixing currencies is out of scope (single currency per
        deployment in this prototype), so the caller reports the dominant one.
        """
        result = await self._session.execute(
            select(Deal.state, func.count(), func.coalesce(func.sum(Deal.amount), 0)).group_by(
                Deal.state
            )
        )
        return {row[0]: (int(row[1]), Decimal(row[2])) for row in result.all()}

    async def state_totals_for_user(
        self, user_id: uuid.UUID
    ) -> dict[DealState, tuple[int, Decimal]]:
        """Count and summed amount per state for deals the user is a party to."""
        result = await self._session.execute(
            select(Deal.state, func.count(), func.coalesce(func.sum(Deal.amount), 0))
            .where(or_(Deal.buyer_id == user_id, Deal.seller_id == user_id))
            .group_by(Deal.state)
        )
        return {row[0]: (int(row[1]), Decimal(row[2])) for row in result.all()}

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

    def add_milestone_criteria(
        self, deal_id: uuid.UUID, milestone_id: uuid.UUID, texts: Sequence[str]
    ) -> list[AcceptanceCriterion]:
        """Criteria scoped to one milestone. `position` is global across the
        deal so the confirmed checklist keeps a stable order."""
        criteria = [
            AcceptanceCriterion(
                deal_id=deal_id, milestone_id=milestone_id, text=text, position=position
            )
            for position, text in enumerate(texts)
        ]
        self._session.add_all(criteria)
        return criteria

    async def list_milestone_criteria(
        self, milestone_id: uuid.UUID
    ) -> Sequence[AcceptanceCriterion]:
        result = await self._session.execute(
            select(AcceptanceCriterion)
            .where(AcceptanceCriterion.milestone_id == milestone_id)
            .order_by(AcceptanceCriterion.position)
        )
        return result.scalars().all()

    # --- milestones -------------------------------------------------------

    def add_milestone(
        self,
        *,
        deal_id: uuid.UUID,
        position: int,
        title: str,
        description: str,
        amount: Decimal,
        state: DealState = DealState.DRAFT,
    ) -> Milestone:
        milestone = Milestone(
            deal_id=deal_id,
            position=position,
            title=title,
            description=description,
            amount=amount,
            state=state,
        )
        self._session.add(milestone)
        return milestone

    async def get_milestone(self, milestone_id: uuid.UUID) -> Milestone | None:
        result = await self._session.execute(
            select(Milestone).where(Milestone.id == milestone_id)
        )
        return result.scalar_one_or_none()

    async def get_milestone_for_update(self, milestone_id: uuid.UUID) -> Milestone | None:
        """Lock one milestone row for the settling transaction."""
        result = await self._session.execute(
            select(Milestone).where(Milestone.id == milestone_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_milestones(self, deal_id: uuid.UUID) -> Sequence[Milestone]:
        result = await self._session.execute(
            select(Milestone).where(Milestone.deal_id == deal_id).order_by(Milestone.position)
        )
        return result.scalars().all()
