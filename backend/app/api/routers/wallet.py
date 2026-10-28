"""User wallet router — balances held in escrow, released, refunded, and pending."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter

from app.api.schemas.deals import DealSummaryResponse, StatTile, WalletOverviewResponse
from app.dependencies import CurrentUserDep, DealRepoDep
from app.domain.enums import DealState

router = APIRouter(prefix="/wallet", tags=["wallet"])

HELD_STATES = (
    DealState.FUNDED,
    DealState.DELIVERED,
    DealState.VERIFYING,
    DealState.DISPUTED,
)
RELEASED_STATES = (DealState.RELEASED, DealState.SPLIT)
REFUNDED_STATES = (DealState.REFUNDED,)
PENDING_STATES = (DealState.DRAFT,)


@router.get("/overview", response_model=WalletOverviewResponse)
@router.get("", response_model=WalletOverviewResponse)
async def get_wallet_overview(
    user: CurrentUserDep,
    deal_repo: DealRepoDep,
) -> WalletOverviewResponse:
    """Aggregated escrow balances and deals breakdown for the authenticated user."""
    totals = await deal_repo.state_totals_for_user(user.id)
    deals = await deal_repo.list_for_user(user.id)

    currency = deals[0].currency if deals else "USD"

    def tile(key: str, states: tuple[DealState, ...]) -> StatTile:
        count = sum(totals.get(state, (0, Decimal("0")))[0] for state in states)
        amount = sum((totals.get(state, (0, Decimal("0")))[1] for state in states), Decimal("0"))
        return StatTile(key=key, count=count, amount=amount, currency=currency)

    return WalletOverviewResponse(
        held=tile("held", HELD_STATES),
        released=tile("released", RELEASED_STATES),
        refunded=tile("refunded", REFUNDED_STATES),
        pending=tile("pending", PENDING_STATES),
        deals=[DealSummaryResponse.model_validate(deal) for deal in deals],
    )
