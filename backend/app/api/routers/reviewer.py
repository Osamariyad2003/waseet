"""The reviewer dashboard — an admin/audit overview (SRS optional add-on).

One endpoint powers the whole view: the KPI tiles and every deal for the
grid. Reviewer-only, like the dispute endpoints.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter

from app.api.schemas.deals import (
    DealSummaryWithParties,
    ReviewerOverviewResponse,
    StatTile,
)
from app.dependencies import DealRepoDep, ReviewerDep
from app.domain.enums import DealState

router = APIRouter(prefix="/reviewer", tags=["reviewer"])

# Money is held from the moment it is captured until the deal settles.
HELD_STATES = (
    DealState.FUNDED,
    DealState.DELIVERED,
    DealState.VERIFYING,
    DealState.DISPUTED,
)


@router.get("/overview", response_model=ReviewerOverviewResponse)
async def overview(reviewer: ReviewerDep, deal_repo: DealRepoDep) -> ReviewerOverviewResponse:
    """The reviewer's dashboard: KPI tiles over every deal."""
    totals = await deal_repo.state_totals()
    deals = await deal_repo.list_all()

    # A single currency per deployment in this prototype, so report the one
    # the deals actually use rather than inventing an FX total.
    currency = deals[0].currency if deals else "USD"

    def tile(key: str, states: tuple[DealState, ...]) -> StatTile:
        count = sum(totals.get(state, (0, Decimal("0")))[0] for state in states)
        amount = sum((totals.get(state, (0, Decimal("0")))[1] for state in states), Decimal("0"))
        return StatTile(key=key, count=count, amount=amount, currency=currency)

    return ReviewerOverviewResponse(
        held_in_escrow=tile("held_in_escrow", HELD_STATES),
        open_disputes=tile("open_disputes", (DealState.DISPUTED,)),
        released=tile("released", (DealState.RELEASED, DealState.SPLIT)),
        refunded=tile("refunded", (DealState.REFUNDED,)),
        deals=[DealSummaryWithParties.model_validate(deal) for deal in deals],
    )
