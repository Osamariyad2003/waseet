"""Disputes: the AI recommendation and the human decision (FR-8, FR-9).

Both endpoints require the reviewer role.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter

from app.api.schemas.deals import (
    MediationResponse,
    ResolveDisputeRequest,
    ResolveDisputeResponse,
)
from app.dependencies import DisputeServiceDep, ReviewerDep
from app.domain.errors import SettlementError

router = APIRouter(prefix="/deals", tags=["disputes"])

# A replayed resolve settled nothing new, so every figure is zero.
ZERO = Decimal("0.00")


@router.get("/{deal_id}/dispute/recommendation", response_model=MediationResponse)
async def get_recommendation(
    deal_id: uuid.UUID, reviewer: ReviewerDep, service: DisputeServiceDep
) -> MediationResponse:
    """The mediator agent's advisory recommendation for the reviewer."""
    recommendation = await service.get_recommendation(deal_id)
    return MediationResponse(
        recommendation=recommendation.recommendation,
        reasoning=recommendation.reasoning,
        suggested_seller_amount=recommendation.suggested_seller_amount,
    )


@router.post("/{deal_id}/dispute/resolve", response_model=ResolveDisputeResponse)
async def resolve_dispute(
    deal_id: uuid.UUID,
    payload: ResolveDisputeRequest,
    reviewer: ReviewerDep,
    service: DisputeServiceDep,
) -> ResolveDisputeResponse:
    """Execute the reviewer's decision: release, refund or split."""
    resolution = await service.resolve(
        deal_id=deal_id,
        reviewer_id=reviewer.id,
        is_reviewer=reviewer.is_reviewer,
        action=payload.action,
        reasoning=payload.reasoning,
        seller_amount=payload.seller_amount,
    )

    breakdown = resolution.outcome.breakdown
    if breakdown is None and not resolution.outcome.already_settled:  # pragma: no cover
        raise SettlementError("the settlement produced no breakdown")

    return ResolveDisputeResponse(
        state=resolution.outcome.state,
        action=payload.action,
        to_seller=breakdown.to_seller if breakdown else ZERO,
        to_buyer=breakdown.to_buyer if breakdown else ZERO,
        platform_fee=breakdown.platform_fee if breakdown else ZERO,
        paypal_reference=resolution.outcome.paypal_reference,
        already_settled=resolution.outcome.already_settled,
    )
