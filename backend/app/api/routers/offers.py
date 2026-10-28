"""The marketplace: seller service offers a buyer can start a deal from.

Offers are listings only — they hold no money and drive no state. The escrow
lifecycle begins when a buyer creates a deal (optionally pre-filled from an
offer), so none of the guardrails live here.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.schemas.deals import CreateOfferRequest, OfferResponse
from app.core.errors import ValidationError
from app.dependencies import CurrentUserDep, OfferRepoDep, SessionDep
from app.domain.enums import Role

router = APIRouter(prefix="/offers", tags=["marketplace"])

MIN_AMOUNT = 1
MAX_AMOUNT = 10_000


@router.get("", response_model=list[OfferResponse])
async def list_offers(user: CurrentUserDep, offers: OfferRepoDep) -> list[OfferResponse]:
    """Every live offer — the marketplace any signed-in user browses."""
    rows = await offers.list_active()
    return [OfferResponse.model_validate(offer) for offer in rows]


@router.get("/mine", response_model=list[OfferResponse])
async def list_my_offers(user: CurrentUserDep, offers: OfferRepoDep) -> list[OfferResponse]:
    """A seller's own offers, active or not."""
    rows = await offers.list_for_seller(user.id)
    return [OfferResponse.model_validate(offer) for offer in rows]


@router.post("", response_model=OfferResponse, status_code=status.HTTP_201_CREATED)
async def create_offer(
    payload: CreateOfferRequest,
    user: CurrentUserDep,
    offers: OfferRepoDep,
    session: SessionDep,
) -> OfferResponse:
    """A seller lists a service in the marketplace."""
    if user.role is not Role.SELLER:
        raise ValidationError("only a seller can post an offer")
    if not (MIN_AMOUNT <= payload.amount <= MAX_AMOUNT):
        raise ValidationError(f"the price must be between {MIN_AMOUNT} and {MAX_AMOUNT}")

    offer = offers.add(
        seller_id=user.id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        category=payload.category.strip().lower() or "other",
        amount=payload.amount,
        currency=payload.currency,
    )
    await session.commit()
    created = await offers.get(offer.id)
    return OfferResponse.model_validate(created)


@router.delete("/{offer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delist_offer(
    offer_id: uuid.UUID,
    user: CurrentUserDep,
    offers: OfferRepoDep,
    session: SessionDep,
) -> None:
    """Delist one of the seller's own offers (soft delete — kept, hidden)."""
    offer = await offers.get(offer_id)
    if offer is None or offer.seller_id != user.id:
        # Don't reveal offers that aren't the caller's.
        raise ValidationError("no such offer")
    offer.active = False
    await session.commit()
