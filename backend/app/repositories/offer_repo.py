"""Marketplace offer data access."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.offer import Offer


class OfferRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(
        self,
        *,
        seller_id: uuid.UUID,
        title: str,
        description: str,
        category: str,
        amount: Decimal,
        currency: str,
    ) -> Offer:
        offer = Offer(
            seller_id=seller_id,
            title=title,
            description=description,
            category=category,
            amount=amount,
            currency=currency,
            active=True,
        )
        self._session.add(offer)
        return offer

    async def get(self, offer_id: uuid.UUID) -> Offer | None:
        result = await self._session.execute(select(Offer).where(Offer.id == offer_id))
        return result.scalar_one_or_none()

    async def list_active(self) -> Sequence[Offer]:
        """The marketplace: every live offer, newest first."""
        result = await self._session.execute(
            select(Offer).where(Offer.active.is_(True)).order_by(Offer.created_at.desc())
        )
        return result.scalars().all()

    async def list_for_seller(self, seller_id: uuid.UUID) -> Sequence[Offer]:
        result = await self._session.execute(
            select(Offer).where(Offer.seller_id == seller_id).order_by(Offer.created_at.desc())
        )
        return result.scalars().all()
