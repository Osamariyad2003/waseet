"""Verification: trigger the agentic loop, read the report (FR-5, FR-6, FR-7)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.schemas.deals import (
    ContestRequest,
    DealResponse,
    VerificationReportResponse,
    VerificationResultResponse,
)
from app.dependencies import CurrentUserDep, DealServiceDep, VerificationServiceDep

router = APIRouter(prefix="/deals", tags=["verification"])


@router.post("/{deal_id}/verify", response_model=VerificationResultResponse)
async def verify(
    deal_id: uuid.UUID, user: CurrentUserDep, service: VerificationServiceDep
) -> VerificationResultResponse:
    """Run the verifier agent, then the decision policy.

    A confident pass auto-releases; a fail, low confidence or an unusable
    model response routes the deal to DISPUTED. The response says which
    happened and why.
    """
    result = await service.verify(deal_id=deal_id, user_id=user.id)
    return VerificationResultResponse(
        report=VerificationReportResponse.model_validate(result.report),
        state=result.deal.state,
        released=result.released,
        policy_outcome=result.decision.outcome.value,
        policy_reason=result.decision.reason,
    )


@router.get("/{deal_id}/verification", response_model=VerificationReportResponse)
async def get_verification(
    deal_id: uuid.UUID, user: CurrentUserDep, service: VerificationServiceDep
) -> VerificationReportResponse:
    report = await service.get_latest_report(deal_id=deal_id, user_id=user.id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="this deal has not been verified yet",
        )
    return VerificationReportResponse.model_validate(report)


@router.post("/{deal_id}/contest", response_model=DealResponse)
async def contest(
    deal_id: uuid.UUID,
    payload: ContestRequest,
    user: CurrentUserDep,
    service: DealServiceDep,
) -> DealResponse:
    """The buyer contests the delivery, which always opens a dispute (FR-7).

    Not in the doc's endpoint table, but the SRS lifecycle requires a buyer
    contest from FUNDED or DELIVERED, and the frontend brief lists "contest"
    as a buyer action on the verification report.
    """
    deal = await service.contest(deal_id=deal_id, user_id=user.id, reason=payload.reason)
    return DealResponse.model_validate(deal)
