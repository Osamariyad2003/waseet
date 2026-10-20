"""Funding: create and capture the PayPal order (FR-3)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.schemas.deals import (
    CaptureOrderRequest,
    CreateOrderResponse,
    DealResponse,
)
from app.dependencies import CurrentUserDep, DealServiceDep

router = APIRouter(prefix="/deals", tags=["funding"])


@router.post(
    "/{deal_id}/order", response_model=CreateOrderResponse, status_code=status.HTTP_201_CREATED
)
async def create_order(
    deal_id: uuid.UUID, user: CurrentUserDep, service: DealServiceDep
) -> CreateOrderResponse:
    """Create the order the buyer approves with the PayPal JS SDK."""
    created = await service.create_order(deal_id=deal_id, user_id=user.id)
    return CreateOrderResponse(paypal_order_id=created.order_id, approve_url=created.approve_url)


@router.post("/{deal_id}/capture", response_model=DealResponse)
async def capture_order(
    deal_id: uuid.UUID,
    payload: CaptureOrderRequest,
    user: CurrentUserDep,
    service: DealServiceDep,
) -> DealResponse:
    """Capture the approved order into the platform account — the deal
    becomes FUNDED and the money is held in escrow."""
    deal = await service.capture_order(
        deal_id=deal_id, user_id=user.id, order_id=payload.paypal_order_id
    )
    return DealResponse.model_validate(deal)
