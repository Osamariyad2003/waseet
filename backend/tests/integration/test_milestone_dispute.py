"""Reviewer resolution of a disputed milestone.

A milestone that fails verification goes to DISPUTED with its slice held. A
reviewer then releases, refunds or splits that slice — the same decisions a
whole-deal dispute offers, scoped to the milestone and capped by the deal's
remaining balance.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.enums import Verdict
from tests.conftest import auth
from tests.integration.test_funding_flow import confirm_both, fund
from tests.integration.test_milestone_flow import MILESTONE_PAYLOAD, create_milestone_deal

pytestmark = pytest.mark.asyncio


async def _dispute_first_milestone(client, tokens, fake_ai) -> tuple[dict, str]:
    """Fund a milestone deal and drive its first milestone to DISPUTED."""
    deal = await create_milestone_deal(client, tokens)
    await confirm_both(client, tokens, deal["id"])
    await fund(client, tokens, deal["id"])
    milestone = (await client.get(f"/deals/{deal['id']}", headers=auth(tokens["buyer"]))).json()[
        "milestones"
    ][0]  # Logo, 150.00

    # The verifier fails this milestone, so the policy disputes it.
    fake_ai.verdict = Verdict.FAIL
    await client.post(
        f"/deals/{deal['id']}/milestones/{milestone['id']}/deliverable",
        json={"type": "text", "content_ref": "Incomplete work."},
        headers=auth(tokens["seller"]),
    )
    result = await client.post(
        f"/deals/{deal['id']}/milestones/{milestone['id']}/verify",
        headers=auth(tokens["seller"]),
    )
    assert result.json()["milestone"]["state"] == "DISPUTED"
    return deal, milestone["id"]


async def test_a_reviewer_releases_a_disputed_milestone(client, tokens, fake_ai, fake_paypal):
    deal, mid = await _dispute_first_milestone(client, tokens, fake_ai)
    resp = await client.post(
        f"/deals/{deal['id']}/milestones/{mid}/dispute/resolve",
        json={"action": "release", "reasoning": "The work is acceptable on review."},
        headers=auth(tokens["reviewer"]),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["milestone"]["state"] == "RELEASED"
    assert fake_paypal.total_paid_out == Decimal("150.00")
    assert fake_paypal.refunds == []


async def test_a_reviewer_refunds_a_disputed_milestone(client, tokens, fake_ai, fake_paypal):
    deal, mid = await _dispute_first_milestone(client, tokens, fake_ai)
    resp = await client.post(
        f"/deals/{deal['id']}/milestones/{mid}/dispute/resolve",
        json={"action": "refund", "reasoning": "The work was not delivered."},
        headers=auth(tokens["reviewer"]),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["milestone"]["state"] == "REFUNDED"
    assert fake_paypal.total_refunded == Decimal("150.00")
    assert fake_paypal.payouts == []


async def test_a_reviewer_splits_a_disputed_milestone(client, tokens, fake_ai, fake_paypal):
    deal, mid = await _dispute_first_milestone(client, tokens, fake_ai)
    resp = await client.post(
        f"/deals/{deal['id']}/milestones/{mid}/dispute/resolve",
        json={"action": "split", "reasoning": "Partly done.", "seller_amount": "90.00"},
        headers=auth(tokens["reviewer"]),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["milestone"]["state"] == "SPLIT"
    assert fake_paypal.total_paid_out == Decimal("90.00")
    assert fake_paypal.total_refunded == Decimal("60.00")


async def test_a_non_reviewer_cannot_resolve_a_milestone_dispute(client, tokens, fake_ai):
    deal, mid = await _dispute_first_milestone(client, tokens, fake_ai)
    resp = await client.post(
        f"/deals/{deal['id']}/milestones/{mid}/dispute/resolve",
        json={"action": "release", "reasoning": "let me"},
        headers=auth(tokens["seller"]),
    )
    assert resp.status_code == 403


async def test_the_whole_deal_cannot_overpay_across_milestone_settlements(
    client, tokens, fake_ai, fake_paypal
):
    """Release milestone 2 normally, then release the disputed milestone 1 —
    the two payouts must sum to the capture and no more."""
    deal = await create_milestone_deal(client, tokens)
    await confirm_both(client, tokens, deal["id"])
    await fund(client, tokens, deal["id"])
    milestones = (await client.get(f"/deals/{deal['id']}", headers=auth(tokens["buyer"]))).json()[
        "milestones"
    ]
    logo, website = milestones[0], milestones[1]

    # Website (100) passes and releases normally.
    fake_ai.verdict = Verdict.PASS
    await client.post(
        f"/deals/{deal['id']}/milestones/{website['id']}/deliverable",
        json={"type": "text", "content_ref": "Site delivered."},
        headers=auth(tokens["seller"]),
    )
    await client.post(
        f"/deals/{deal['id']}/milestones/{website['id']}/verify",
        headers=auth(tokens["seller"]),
    )

    # Logo (150) fails, is disputed, then the reviewer releases it.
    fake_ai.verdict = Verdict.FAIL
    await client.post(
        f"/deals/{deal['id']}/milestones/{logo['id']}/deliverable",
        json={"type": "text", "content_ref": "Incomplete."},
        headers=auth(tokens["seller"]),
    )
    await client.post(
        f"/deals/{deal['id']}/milestones/{logo['id']}/verify", headers=auth(tokens["seller"])
    )
    await client.post(
        f"/deals/{deal['id']}/milestones/{logo['id']}/dispute/resolve",
        json={"action": "release", "reasoning": "Acceptable."},
        headers=auth(tokens["reviewer"]),
    )

    assert fake_paypal.total_paid_out == Decimal("250.00")  # 100 + 150, the full capture
