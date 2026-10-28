"""Funding: create and capture the PayPal order (FR-3)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, status

from app.api.schemas.deals import (
    CaptureOrderRequest,
    ClientTokenResponse,
    CreateOrderResponse,
    DealResponse,
)
from app.dependencies import (
    CurrentUserDep,
    DealServiceDep,
    NotificationsDep,
    PayPalDep,
    SettingsDep,
)

router = APIRouter(tags=["funding"])

# The v6 Web SDK loads from an environment-specific core URL. A production
# SDK cannot load a sandbox order (and vice versa), so the browser must load
# the one that matches the credentials the backend is using.
_SANDBOX_SDK_URL = "https://www.sandbox.paypal.com/web-sdk/v6/core"
_LIVE_SDK_URL = "https://www.paypal.com/web-sdk/v6/core"


@router.get("/paypal/client-token", response_model=ClientTokenResponse)
async def get_client_token(
    user: CurrentUserDep, paypal: PayPalDep, settings: SettingsDep
) -> ClientTokenResponse:
    """Mint a browser-safe token for the PayPal JS SDK v6, and tell the
    browser which SDK environment to load.

    Authenticated, so an anonymous caller cannot burn through tokens on the
    platform's credentials. The client secret stays on the server. The SDK
    URL is derived from PAYPAL_BASE_URL so the browser can never load a
    production SDK against a sandbox order.
    """
    token = await paypal.get_client_token()
    is_sandbox = "sandbox" in settings.paypal_base_url
    return ClientTokenResponse(
        client_token=token,
        sdk_url=_SANDBOX_SDK_URL if is_sandbox else _LIVE_SDK_URL,
    )


@router.post(
    "/deals/{deal_id}/order",
    response_model=CreateOrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    deal_id: uuid.UUID, user: CurrentUserDep, service: DealServiceDep
) -> CreateOrderResponse:
    """Create the order the buyer approves with the PayPal JS SDK."""
    created = await service.create_order(deal_id=deal_id, user_id=user.id)
    return CreateOrderResponse(paypal_order_id=created.order_id, approve_url=created.approve_url)


@router.post("/deals/{deal_id}/capture", response_model=DealResponse)
async def capture_order(
    deal_id: uuid.UUID,
    payload: CaptureOrderRequest,
    user: CurrentUserDep,
    service: DealServiceDep,
    notifications: NotificationsDep,
    background: BackgroundTasks,
) -> DealResponse:
    """Capture the approved order into the platform account — the deal
    becomes FUNDED and the money is held in escrow."""
    deal = await service.capture_order(
        deal_id=deal_id, user_id=user.id, order_id=payload.paypal_order_id
    )
    # Email the seller that work can begin, after the response is sent.
    background.add_task(notifications.deal_funded, deal)
    return DealResponse.model_validate(deal)
