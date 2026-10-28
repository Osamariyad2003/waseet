"""The Deal Terms Acknowledgment endpoint.

A read-only, plain-language summary of what both parties agreed to, pinned to
the confirmed checklist with a SHA-256. It binds nothing and moves no money —
the actual agreement is the existing two-party criteria confirmation; this
just renders it honestly, with a hash so the terms can't drift.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.schemas.deals import DealTermsResponse
from app.dependencies import CurrentUserDep, DealRepoDep
from app.domain.errors import DealNotFound, NotAuthorizedForDeal
from app.domain.terms import PROCESS_STEPS, RIGHTS_NOTICE, build_terms

router = APIRouter(prefix="/deals", tags=["terms"])


@router.get("/{deal_id}/terms", response_model=DealTermsResponse)
async def get_terms(
    deal_id: uuid.UUID,
    user: CurrentUserDep,
    deals: DealRepoDep,
) -> DealTermsResponse:
    deal = await deals.get(deal_id)
    if deal is None:
        raise DealNotFound("no such deal")
    if not deal.is_party(user.id):
        raise NotAuthorizedForDeal("you are not a party to this deal")

    criteria = await deals.list_criteria(deal_id)
    descriptions = tuple(c.text for c in criteria)
    terms = build_terms(
        descriptions=descriptions,
        buyer_confirmed=bool(criteria) and all(c.confirmed_by_buyer for c in criteria),
        seller_confirmed=bool(criteria) and all(c.confirmed_by_seller for c in criteria),
    )

    return DealTermsResponse(
        deal_id=deal.id,
        amount=deal.amount,
        currency=deal.currency,
        criteria=list(terms.criteria),
        canonical_checklist=terms.canonical_checklist,
        checklist_sha256=terms.checklist_sha256,
        buyer_confirmed=terms.buyer_confirmed,
        seller_confirmed=terms.seller_confirmed,
        both_confirmed=terms.both_confirmed,
        process_steps=list(PROCESS_STEPS),
        rights_notice=RIGHTS_NOTICE,
    )
