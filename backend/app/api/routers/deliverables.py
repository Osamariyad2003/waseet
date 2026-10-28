"""Deliverable submission (FR-4)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, status

from app.api.schemas.deals import DeliverableResponse, SubmitDeliverableRequest
from app.dependencies import CurrentUserDep, DealServiceDep, NotificationsDep

router = APIRouter(prefix="/deals", tags=["deliverables"])


@router.post(
    "/{deal_id}/deliverable",
    response_model=DeliverableResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_deliverable(
    deal_id: uuid.UUID,
    payload: SubmitDeliverableRequest,
    user: CurrentUserDep,
    service: DealServiceDep,
    notifications: NotificationsDep,
    background: BackgroundTasks,
) -> DeliverableResponse:
    """The seller submits their work; the deal moves to DELIVERED.

    The content is stored verbatim and is never interpreted as an
    instruction — only the verifier reads it, as data to judge.
    """
    deliverable = await service.submit_deliverable(
        deal_id=deal_id,
        user_id=user.id,
        type_=payload.type,
        content_ref=payload.content_ref,
        note=payload.note,
    )
    # Email the buyer that work was submitted, after the response is sent.
    deal = await service.get_deal_for_party(deal_id=deal_id, user_id=user.id)
    background.add_task(notifications.deliverable_submitted, deal)
    return DeliverableResponse.model_validate(deliverable)
