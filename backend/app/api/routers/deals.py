"""Deal creation, reads, timeline and audit trail (FR-1, FR-2, FR-10, FR-11)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, status
from sqlalchemy import select

from app.api.schemas.deals import (
    AuditEntryResponse,
    CreateDealRequest,
    DealResponse,
    DealSummaryResponse,
    ActivityEntryResponse,
    DealWithTimelineResponse,
    DeliverableResponse,
    MilestoneDisputeResultResponse,
    MilestoneVerificationResultResponse,
    PayoutStatusResponse,
    PayoutViewResponse,
    ResolveDisputeRequest,
    SubmitDeliverableRequest,
)
from app.core.errors import ValidationError
from app.dependencies import (
    AuditRepoDep,
    CurrentUserDep,
    DealServiceDep,
    MilestoneServiceDep,
    NotificationsDep,
    ReviewerDep,
    SessionDep,
)
from app.domain.enums import DealState, Role
from app.models.user import User
from app.services.deal_service import CreateDealCommand, MilestoneSpec

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
            # A milestone deal derives its amount from the milestones; a simple
            # deal states it. The service recomputes the total either way.
            amount=payload.amount if payload.amount is not None else Decimal("0"),
            currency=payload.currency,
            milestones=tuple(
                MilestoneSpec(title=m.title, description=m.description, amount=m.amount)
                for m in payload.milestones
            ),
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


@router.post(
    "/{deal_id}/milestones/{milestone_id}/deliverable",
    response_model=DeliverableResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_milestone_deliverable(
    deal_id: uuid.UUID,
    milestone_id: uuid.UUID,
    payload: SubmitDeliverableRequest,
    user: CurrentUserDep,
    service: MilestoneServiceDep,
) -> DeliverableResponse:
    """The seller submits the deliverable for one milestone (FR-4, per slice)."""
    deliverable = await service.submit_deliverable(
        deal_id=deal_id,
        milestone_id=milestone_id,
        user_id=user.id,
        type_=payload.type,
        content_ref=payload.content_ref,
        note=payload.note,
    )
    return DeliverableResponse.model_validate(deliverable)


@router.post(
    "/{deal_id}/milestones/{milestone_id}/verify",
    response_model=MilestoneVerificationResultResponse,
)
async def verify_milestone(
    deal_id: uuid.UUID,
    milestone_id: uuid.UUID,
    user: CurrentUserDep,
    service: MilestoneServiceDep,
    deal_service: DealServiceDep,
    notifications: NotificationsDep,
    background: BackgroundTasks,
) -> MilestoneVerificationResultResponse:
    """Run the verifier on one milestone; a confident pass releases its slice."""
    result = await service.verify(deal_id=deal_id, milestone_id=milestone_id, user_id=user.id)
    if result.released:
        deal = await deal_service.get_deal_for_party(deal_id=deal_id, user_id=user.id)
        background.add_task(notifications.milestone_released, deal, result.milestone)
    return MilestoneVerificationResultResponse(
        milestone=result.milestone,
        released=result.released,
        policy_outcome=result.decision.outcome.value,
        policy_reason=result.decision.reason,
    )


@router.post(
    "/{deal_id}/milestones/{milestone_id}/dispute/resolve",
    response_model=MilestoneDisputeResultResponse,
)
async def resolve_milestone_dispute(
    deal_id: uuid.UUID,
    milestone_id: uuid.UUID,
    payload: ResolveDisputeRequest,
    reviewer: ReviewerDep,
    service: MilestoneServiceDep,
) -> MilestoneDisputeResultResponse:
    """A reviewer resolves a disputed milestone — release, refund or split its
    slice (FR-8, FR-9, per milestone)."""
    result = await service.resolve_dispute(
        deal_id=deal_id,
        milestone_id=milestone_id,
        reviewer_id=reviewer.id,
        is_reviewer=True,
        action=payload.action,
        reasoning=payload.reasoning,
        seller_amount=payload.seller_amount,
    )
    breakdown = result.outcome.breakdown
    return MilestoneDisputeResultResponse(
        milestone=result.milestone,
        action=payload.action,
        to_seller=breakdown.to_seller if breakdown else Decimal("0"),
        to_buyer=breakdown.to_buyer if breakdown else Decimal("0"),
        platform_fee=breakdown.platform_fee if breakdown else Decimal("0"),
        paypal_reference=result.outcome.paypal_reference,
        already_settled=result.outcome.already_settled,
    )


@router.get("/{deal_id}/payouts", response_model=list[PayoutViewResponse])
async def get_payouts(
    deal_id: uuid.UUID,
    user: CurrentUserDep,
    service: DealServiceDep,
) -> list[PayoutViewResponse]:
    """Live PayPal payout-batch status for every release this deal has made
    (whole-deal or per milestone), read from PayPal's Payouts API."""
    views = await service.get_payouts(
        deal_id=deal_id, user_id=user.id, is_reviewer=user.role is Role.REVIEWER
    )
    return [
        PayoutViewResponse(
            source=view.source,
            milestone_id=view.milestone_id,
            status=PayoutStatusResponse.model_validate(view.status) if view.status else None,
            error=view.error,
        )
        for view in views
    ]


@router.get("/{deal_id}/paypal-activity", response_model=list[ActivityEntryResponse])
async def get_paypal_activity(
    deal_id: uuid.UUID,
    user: CurrentUserDep,
    service: DealServiceDep,
) -> list[ActivityEntryResponse]:
    """The deal's full PayPal money trail — order, capture, payouts, refund —
    each read live from PayPal."""
    entries = await service.get_paypal_activity(
        deal_id=deal_id, user_id=user.id, is_reviewer=user.role is Role.REVIEWER
    )
    return [ActivityEntryResponse.model_validate(entry) for entry in entries]


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
