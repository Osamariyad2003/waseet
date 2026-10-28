"""Home landing router — quick dashboard summary and recent deals for the user."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.schemas.deals import DealSummaryResponse, HomeSummaryResponse, UserResponse
from app.core.errors import AuthenticationError
from app.dependencies import CurrentUserDep, DealRepoDep, SessionDep
from app.domain.enums import DealState, Role
from app.models.user import User

router = APIRouter(prefix="/home", tags=["home"])

ACTIVE_STATES = (
    DealState.DRAFT,
    DealState.FUNDED,
    DealState.DELIVERED,
    DealState.VERIFYING,
    DealState.DISPUTED,
)


@router.get("/summary", response_model=HomeSummaryResponse)
@router.get("", response_model=HomeSummaryResponse)
async def get_home_summary(
    user: CurrentUserDep,
    session: SessionDep,
    deal_repo: DealRepoDep,
) -> HomeSummaryResponse:
    """Home landing summary: active deals, action items, and recent deal list."""
    result = await session.execute(select(User).where(User.id == user.id))
    db_user = result.scalars().first()
    if db_user is None:
        raise AuthenticationError("the authentication token is not valid")

    deals = await deal_repo.list_for_user(user.id)
    active_deals = [d for d in deals if d.state in ACTIVE_STATES]

    # Calculate deals needing action from this party
    action_required = 0
    for deal in active_deals:
        if deal.state is DealState.DRAFT:
            # Need criteria confirmation from user if unconfirmed
            buyer_unconfirmed = any(not c.confirmed_by_buyer for c in deal.criteria)
            seller_unconfirmed = any(not c.confirmed_by_seller for c in deal.criteria)
            if user.role is Role.BUYER and buyer_unconfirmed:
                action_required += 1
            elif user.role is Role.SELLER and seller_unconfirmed:
                action_required += 1
            elif not buyer_unconfirmed and not seller_unconfirmed and user.role is Role.BUYER:
                # Confirmed: ready for buyer to fund
                action_required += 1
        elif deal.state is DealState.FUNDED and user.role is Role.SELLER:
            # Ready for seller to deliver
            action_required += 1

    return HomeSummaryResponse(
        user=UserResponse.model_validate(db_user),
        active_deals_count=len(active_deals),
        action_required_count=action_required,
        recent_deals=[DealSummaryResponse.model_validate(deal) for deal in deals[:5]],
    )
