"""Account router — user profile, activity stats, and settings."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import select

from app.api.schemas.deals import AccountProfileResponse, UpdateAccountProfileRequest
from app.core.errors import AuthenticationError
from app.dependencies import CurrentUserDep, DealRepoDep, SessionDep
from app.models.user import User

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/profile", response_model=AccountProfileResponse)
@router.get("", response_model=AccountProfileResponse)
async def get_account_profile(
    user: CurrentUserDep,
    session: SessionDep,
    deal_repo: DealRepoDep,
) -> AccountProfileResponse:
    """Detailed profile with transacted volume and deal activity counts."""
    result = await session.execute(select(User).where(User.id == user.id))
    db_user = result.scalars().first()
    if db_user is None:
        raise AuthenticationError("the authentication token is not valid")

    deals = await deal_repo.list_for_user(user.id)
    deals_as_buyer = sum(1 for d in deals if d.buyer_id == user.id)
    deals_as_seller = sum(1 for d in deals if d.seller_id == user.id)
    total_volume = sum((d.amount for d in deals), Decimal("0"))
    currency = deals[0].currency if deals else "USD"

    return AccountProfileResponse(
        id=db_user.id,
        email=db_user.email,
        full_name=db_user.full_name,
        role=db_user.role,
        paypal_account_ref=db_user.paypal_account_ref,
        created_at=db_user.created_at,
        total_deals=len(deals),
        deals_as_buyer=deals_as_buyer,
        deals_as_seller=deals_as_seller,
        total_transacted_volume=total_volume,
        currency=currency,
    )


@router.patch("/profile", response_model=AccountProfileResponse)
@router.patch("", response_model=AccountProfileResponse)
async def update_account_profile(
    payload: UpdateAccountProfileRequest,
    user: CurrentUserDep,
    session: SessionDep,
    deal_repo: DealRepoDep,
) -> AccountProfileResponse:
    """Updates account profile attributes (full_name, paypal_account_ref)."""
    result = await session.execute(select(User).where(User.id == user.id))
    db_user = result.scalars().first()
    if db_user is None:
        raise AuthenticationError("the authentication token is not valid")

    if payload.full_name is not None:
        db_user.full_name = payload.full_name.strip()
    if payload.paypal_account_ref is not None:
        db_user.paypal_account_ref = payload.paypal_account_ref.strip() or None

    await session.commit()
    await session.refresh(db_user)

    deals = await deal_repo.list_for_user(user.id)
    deals_as_buyer = sum(1 for d in deals if d.buyer_id == user.id)
    deals_as_seller = sum(1 for d in deals if d.seller_id == user.id)
    total_volume = sum((d.amount for d in deals), Decimal("0"))
    currency = deals[0].currency if deals else "USD"

    return AccountProfileResponse(
        id=db_user.id,
        email=db_user.email,
        full_name=db_user.full_name,
        role=db_user.role,
        paypal_account_ref=db_user.paypal_account_ref,
        created_at=db_user.created_at,
        total_deals=len(deals),
        deals_as_buyer=deals_as_buyer,
        deals_as_seller=deals_as_seller,
        total_transacted_volume=total_volume,
        currency=currency,
    )
