"""Milestone-based deals, end to end.

A deal is split into milestones, funded once for the whole amount, then each
milestone is delivered, verified and released on its own slice. The real app,
the real state machine and the real settlement path run; only PayPal and the
AI are faked (the fake verifier passes with high confidence by default, so the
policy auto-releases each milestone).

The load-bearing guarantee is the last assertion of `test_full_flow`: the two
milestone releases sum to exactly the captured amount and no more — the spend
mandate's cumulative cap in action.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.conftest import auth
from tests.integration.test_funding_flow import confirm_both, fund

pytestmark = pytest.mark.asyncio


MILESTONE_PAYLOAD = {
    "seller_email": "seller@sandbox.example.com",
    "title": "Brand package",
    "description": (
        "A full brand package delivered in two milestones: the logo first, "
        "then the website, each verified and paid on its own."
    ),
    "currency": "USD",
    "milestones": [
        {
            "title": "Logo",
            "description": "A vector logo for the coffee shop.",
            "amount": "150.00",
        },
        {
            "title": "Website",
            "description": "A one-page marketing site using the logo.",
            "amount": "100.00",
        },
    ],
}


async def create_milestone_deal(client, tokens) -> dict:
    response = await client.post("/deals", json=MILESTONE_PAYLOAD, headers=auth(tokens["buyer"]))
    assert response.status_code == 201, response.text
    return response.json()


class TestCreation:
    async def test_the_deal_amount_is_the_sum_of_the_milestones(self, client, tokens):
        deal = await create_milestone_deal(client, tokens)
        assert deal["amount"] == "250.00"
        assert len(deal["milestones"]) == 2
        assert [m["title"] for m in deal["milestones"]] == ["Logo", "Website"]
        assert [m["amount"] for m in deal["milestones"]] == ["150.00", "100.00"]

    async def test_each_milestone_gets_its_own_checklist(self, client, tokens):
        deal = await create_milestone_deal(client, tokens)
        for milestone in deal["milestones"]:
            assert milestone["criteria"], "every milestone has AI-drafted criteria"
            assert milestone["state"] == "DRAFT"

    async def test_a_single_milestone_is_rejected(self, client, tokens):
        payload = {**MILESTONE_PAYLOAD, "milestones": [MILESTONE_PAYLOAD["milestones"][0]]}
        response = await client.post("/deals", json=payload, headers=auth(tokens["buyer"]))
        assert response.status_code == 422


class TestFunding:
    async def test_funding_moves_every_milestone_to_funded(self, client, tokens):
        deal = await create_milestone_deal(client, tokens)
        await confirm_both(client, tokens, deal["id"])
        await fund(client, tokens, deal["id"])

        current = await client.get(f"/deals/{deal['id']}", headers=auth(tokens["buyer"]))
        body = current.json()
        assert body["state"] == "FUNDED"
        assert all(m["state"] == "FUNDED" for m in body["milestones"])


class TestReleasePerMilestone:
    async def test_full_flow(self, client, tokens, fake_paypal):
        deal = await create_milestone_deal(client, tokens)
        await confirm_both(client, tokens, deal["id"])
        await fund(client, tokens, deal["id"])

        milestones = (await client.get(f"/deals/{deal['id']}", headers=auth(tokens["buyer"]))).json()[
            "milestones"
        ]
        for milestone in milestones:
            # The seller delivers this milestone's work.
            delivered = await client.post(
                f"/deals/{deal['id']}/milestones/{milestone['id']}/deliverable",
                json={"type": "text", "content_ref": f"Completed: {milestone['title']}."},
                headers=auth(tokens["seller"]),
            )
            assert delivered.status_code == 201, delivered.text

            # Verification auto-releases this milestone's slice.
            verified = await client.post(
                f"/deals/{deal['id']}/milestones/{milestone['id']}/verify",
                headers=auth(tokens["seller"]),
            )
            assert verified.status_code == 200, verified.text
            body = verified.json()
            assert body["released"] is True
            assert body["milestone"]["state"] == "RELEASED"

        # Two payouts, one per milestone, to the designated seller — summing to
        # exactly the captured amount and no more.
        assert len(fake_paypal.payouts) == 2
        assert {p["amount"] for p in fake_paypal.payouts} == {Decimal("150.00"), Decimal("100.00")}
        assert all(p["receiver_email"] == "seller@sandbox.example.com" for p in fake_paypal.payouts)
        assert fake_paypal.total_paid_out == Decimal("250.00")

    async def test_a_second_verify_of_a_released_milestone_does_not_double_pay(
        self, client, tokens, fake_paypal
    ):
        deal = await create_milestone_deal(client, tokens)
        await confirm_both(client, tokens, deal["id"])
        await fund(client, tokens, deal["id"])
        milestone = (await client.get(f"/deals/{deal['id']}", headers=auth(tokens["buyer"]))).json()[
            "milestones"
        ][0]

        await client.post(
            f"/deals/{deal['id']}/milestones/{milestone['id']}/deliverable",
            json={"type": "text", "content_ref": "Completed the logo."},
            headers=auth(tokens["seller"]),
        )
        first = await client.post(
            f"/deals/{deal['id']}/milestones/{milestone['id']}/verify",
            headers=auth(tokens["seller"]),
        )
        assert first.json()["released"] is True

        # Re-verifying a released milestone resolves to the stored result, and
        # never issues a second payout.
        second = await client.post(
            f"/deals/{deal['id']}/milestones/{milestone['id']}/verify",
            headers=auth(tokens["seller"]),
        )
        assert second.status_code == 200
        assert len(fake_paypal.payouts) == 1
