"""The public Proof-of-Escrow certificate.

A single unauthenticated, read-only endpoint. Given a settled deal's id it
returns a privacy-safe record of the outcome and the AI verifier's audit
summary, so a link can be shared and checked without signing in. Only settled
deals are exposed — an in-progress or disputed deal is 404, so the endpoint
never leaks a deal that has not reached a final state.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.schemas.deals import CertificateResponse
from app.dependencies import DealRepoDep, VerificationRepoDep
from app.domain.enums import DealState

router = APIRouter(tags=["certificate"])

# The terminal states where money has moved. These are the only deals a
# certificate is issued for.
_SETTLED = {DealState.RELEASED, DealState.REFUNDED, DealState.SPLIT}


def _seal(deal_id: uuid.UUID) -> str:
    """A short, human-readable reference for the certificate."""
    return f"WST-{str(deal_id).split('-')[0].upper()}"


@router.get("/verify/{deal_id}", response_model=CertificateResponse)
async def get_certificate(
    deal_id: uuid.UUID,
    deals: DealRepoDep,
    verifications: VerificationRepoDep,
) -> CertificateResponse:
    deal = await deals.get(deal_id)
    if deal is None or deal.state not in _SETTLED:
        # One 404 for "no such deal" and "not settled yet" alike — the
        # endpoint never confirms that an unsettled deal exists.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no settled deal with this reference",
        )

    report = await verifications.get_latest(deal_id)
    verified: list[str] = []
    unmet: list[str] = []
    if report is not None:
        for finding in report.per_criterion:
            text = str(finding.get("text", ""))
            (verified if finding.get("pass") else unmet).append(text)

    return CertificateResponse(
        deal_id=deal.id,
        seal=_seal(deal.id),
        title=deal.title,
        amount=deal.amount,
        currency=deal.currency,
        outcome=deal.state.value.lower(),
        state=deal.state,
        created_at=deal.created_at,
        verdict=report.verdict if report else None,
        confidence=report.confidence if report else None,
        reasoning=report.reasoning if report else None,
        verified_criteria=verified,
        unmet_or_missing_criteria=unmet,
        decided_by=report.decided_by if report else None,
        decided_at=report.decided_at if report else None,
    )
