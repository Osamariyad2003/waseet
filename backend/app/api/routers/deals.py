"""Deal creation, reads, timeline and audit trail (FR-1, FR-2, FR-10, FR-11)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.schemas.deals import (
    AuditEntryResponse,
    CreateDealRequest,
    DealResponse,
    DealSummaryResponse,
    DealWithTimelineResponse,
)
from app.core.errors import ValidationError
from app.dependencies import (
    AuditRepoDep,
    CurrentUserDep,
    DealServiceDep,
    SessionDep,
)
from app.domain.enums import DealState, Role
from app.models.user import User
from app.services.deal_service import CreateDealCommand

router = APIRouter(prefix="/deals", tags=["deals"])


@router.post("", response_model=DealResponse, status_code=status.HTTP_201_CREATED)
async def create_deal(
    payload: CreateDealRequest,
    user: CurrentUserDep,
    service: DealServiceDep,
    session: SessionDep,
) -> DealResponse:
    """Create a deal from a plain-language description; the criteria agent
    drafts the checklist (FR-1, FR-2).

    The caller is the buyer. A seller role cannot open a deal as the buyer.
    """
    if user.role is not Role.BUYER:
        raise ValidationError("only a buyer can create a deal")

    result = await session.execute(select(User).where(User.email == payload.seller_email.lower()))
    seller = result.scalars().first()
    if seller is None:
        raise ValidationError("no seller is registered with that email")
    if seller.role is not Role.SELLER:
        raise ValidationError("the named counterparty is not registered as a seller")

    deal = await service.create_deal(
        CreateDealCommand(
            buyer_id=user.id,
            seller_id=seller.id,
            title=payload.title,
            description=payload.description,
            amount=payload.amount,
            currency=payload.currency,
        )
    )
    return DealResponse.model_validate(deal)


@router.get("", response_model=list[DealSummaryResponse])
async def list_deals(
    user: CurrentUserDep,
    service: DealServiceDep,
    state: Annotated[DealState | None, Query()] = None,
) -> list[DealSummaryResponse]:
    """The user's deals; for a reviewer, the dispute queue."""
    deals = await service.list_deals(user_id=user.id, role=user.role, state=state)
    return [DealSummaryResponse.model_validate(deal) for deal in deals]


@router.get("/{deal_id}", response_model=DealWithTimelineResponse)
async def get_deal(
    deal_id: uuid.UUID,
    user: CurrentUserDep,
    service: DealServiceDep,
    audit_repo: AuditRepoDep,
) -> DealWithTimelineResponse:
    """The whole deal in one request: state, criteria, deliverables,
    verification reports and the timeline (FR-11)."""
    deal = (
        await service.get_deal_for_reviewer(deal_id)
        if user.role is Role.REVIEWER
        else await service.get_deal_for_party(deal_id=deal_id, user_id=user.id)
    )
    timeline = await audit_repo.list_for_deal(deal_id)
    response = DealWithTimelineResponse.model_validate(deal)
    response.timeline = [AuditEntryResponse.model_validate(entry) for entry in timeline]
    return response


@router.post("/{deal_id}/criteria/confirm", response_model=DealResponse)
async def confirm_criteria(
    deal_id: uuid.UUID, user: CurrentUserDep, service: DealServiceDep
) -> DealResponse:
    """Confirm the acceptance checklist as one party (FR-2)."""
    deal = await service.confirm_criteria(deal_id=deal_id, user_id=user.id)
    return DealResponse.model_validate(deal)


@router.get("/{deal_id}/audit", response_model=list[AuditEntryResponse])
async def get_audit_trail(
    deal_id: uuid.UUID,
    user: CurrentUserDep,
    service: DealServiceDep,
    audit_repo: AuditRepoDep,
) -> list[AuditEntryResponse]:
    """The append-only audit trail (FR-10)."""
    if user.role is Role.REVIEWER:
        await service.get_deal_for_reviewer(deal_id)
    else:
        await service.get_deal_for_party(deal_id=deal_id, user_id=user.id)
    entries = await audit_repo.list_for_deal(deal_id)
    return [AuditEntryResponse.model_validate(entry) for entry in entries]
