"""Disputes: the mediator's recommendation and the human's decision (FR-8, FR-9).

The point of these tests is that the human is genuinely in the loop — the
agent's recommendation has no power of its own, and only a reviewer's
decision moves money.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.enums import SettlementAction, Verdict
from tests.conftest import auth
from tests.integration.test_funding_flow import confirm_both, create_deal, fund
from tests.integration.test_verification_flow import deliver


async def disputed_deal(client, tokens, deal_payload, fake_ai) -> dict:
    """A deal that failed verification and is sitting in DISPUTED."""
    fake_ai.verdict = Verdict.FAIL
    fake_ai.confidence = Decimal("0.91")
    fake_ai.reasoning = "The logo is a raster PNG, not the agreed vector file."

    deal = await create_deal(client, tokens, deal_payload)
    await confirm_both(client, tokens, deal["id"])
    await fund(client, tokens, deal["id"])
    await deliver(client, tokens, deal["id"])
    result = await client.post(f"/deals/{deal['id']}/verify", headers=auth(tokens["seller"]))
    assert result.json()["state"] == "DISPUTED"
    return deal


async def resolve(client, tokens, deal_id: str, **payload):
    return await client.post(
        f"/deals/{deal_id}/dispute/resolve", json=payload, headers=auth(tokens["reviewer"])
    )


class TestReviewerQueue:
    async def test_disputed_deals_appear_in_the_reviewer_queue(
        self, client, tokens, deal_payload, fake_ai
    ):
        await disputed_deal(client, tokens, deal_payload, fake_ai)

        queue = await client.get("/deals", headers=auth(tokens["reviewer"]))
        assert len(queue.json()) == 1
        assert queue.json()[0]["state"] == "DISPUTED"

    async def test_the_reviewer_can_read_the_whole_deal(
        self, client, tokens, deal_payload, fake_ai
    ):
        deal = await disputed_deal(client, tokens, deal_payload, fake_ai)

        response = await client.get(f"/deals/{deal['id']}", headers=auth(tokens["reviewer"]))
        assert response.status_code == 200
        body = response.json()
        assert body["verification_reports"]
        assert body["timeline"]


class TestMediatorRecommendation:
    async def test_the_mediator_recommends_an_outcome_with_reasoning(
        self, client, tokens, deal_payload, fake_ai
    ):
        fake_ai.recommendation = SettlementAction.REFUND
        fake_ai.recommendation_reasoning = "The agreed vector file was never delivered."
        deal = await disputed_deal(client, tokens, deal_payload, fake_ai)

        response = await client.get(
            f"/deals/{deal['id']}/dispute/recommendation", headers=auth(tokens["reviewer"])
        )
        assert response.status_code == 200
        body = response.json()
        assert body["recommendation"] == "refund"
        assert body["reasoning"] == "The agreed vector file was never delivered."
        assert "final decision" in body["advisory_notice"]

    async def test_the_recommendation_alone_moves_no_money(
        self, client, tokens, deal_payload, fake_ai, fake_paypal
    ):
        """ "Decide, don't disburse" — asking the agent changes nothing."""
        fake_ai.recommendation = SettlementAction.RELEASE
        deal = await disputed_deal(client, tokens, deal_payload, fake_ai)

        await client.get(
            f"/deals/{deal['id']}/dispute/recommendation", headers=auth(tokens["reviewer"])
        )

        assert fake_paypal.payouts == []
        assert fake_paypal.refunds == []
        current = await client.get(f"/deals/{deal['id']}", headers=auth(tokens["reviewer"]))
        assert current.json()["state"] == "DISPUTED"

    @pytest.mark.parametrize("role", ["buyer", "seller"])
    async def test_only_a_reviewer_can_see_the_recommendation(
        self, client, tokens, deal_payload, fake_ai, role
    ):
        deal = await disputed_deal(client, tokens, deal_payload, fake_ai)
        response = await client.get(
            f"/deals/{deal['id']}/dispute/recommendation", headers=auth(tokens[role])
        )
        assert response.status_code == 403


class TestHumanRefund:
    async def test_a_refund_returns_the_money_to_the_buyer(
        self, client, tokens, deal_payload, fake_ai, fake_paypal
    ):
        """FR-9, the dispute path of the demo."""
        deal = await disputed_deal(client, tokens, deal_payload, fake_ai)

        response = await resolve(
            client,
            tokens,
            deal["id"],
            action="refund",
            reasoning="The deliverable does not meet criterion two; the buyer is refunded.",
        )
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["state"] == "REFUNDED"
        assert body["to_buyer"] == "250.00"
        assert body["to_seller"] == "0.00"
        assert len(fake_paypal.refunds) == 1
        assert fake_paypal.refunds[0]["amount"] == Decimal("250.00")
        assert fake_paypal.payouts == []

    async def test_the_human_decision_is_recorded_as_its_own_report(
        self, client, tokens, deal_payload, fake_ai
    ):
        deal = await disputed_deal(client, tokens, deal_payload, fake_ai)
        await resolve(
            client,
            tokens,
            deal["id"],
            action="refund",
            reasoning="Reviewed the file; it is a PNG.",
        )

        current = await client.get(f"/deals/{deal['id']}", headers=auth(tokens["reviewer"]))
        reports = current.json()["verification_reports"]
        assert len(reports) == 2
        assert [report["decided_by"] for report in reports] == ["ai", "human"]
        assert reports[-1]["reasoning"] == "Reviewed the file; it is a PNG."

    async def test_the_refund_is_explained_in_the_audit_trail(
        self, client, tokens, deal_payload, fake_ai
    ):
        deal = await disputed_deal(client, tokens, deal_payload, fake_ai)
        await resolve(client, tokens, deal["id"], action="refund", reasoning="Not as agreed.")

        audit = await client.get(f"/deals/{deal['id']}/audit", headers=auth(tokens["buyer"]))
        entries = audit.json()
        refunded = next(entry for entry in entries if entry["to_state"] == "REFUNDED")

        assert refunded["actor"] == "reviewer"
        assert "Not as agreed." in refunded["reason"]
        assert refunded["paypal_reference"] is not None

        states = [entry["to_state"] for entry in entries]
        assert states[-2:] == ["DISPUTED", "REFUNDED"]


class TestHumanRelease:
    async def test_a_reviewer_can_release_despite_a_failed_verification(
        self, client, tokens, deal_payload, fake_ai, fake_paypal
    ):
        """The human overrules the agent, which is the whole point of the loop."""
        deal = await disputed_deal(client, tokens, deal_payload, fake_ai)

        response = await resolve(
            client,
            tokens,
            deal["id"],
            action="release",
            reasoning="The buyer's criteria were ambiguous; the work is acceptable.",
        )
        assert response.status_code == 200
        assert response.json()["state"] == "RELEASED"
        assert len(fake_paypal.payouts) == 1
        assert fake_paypal.payouts[0]["amount"] == Decimal("250.00")


class TestHumanSplit:
    async def test_a_split_pays_the_seller_and_refunds_the_remainder(
        self, client, tokens, deal_payload, fake_ai, fake_paypal
    ):
        deal = await disputed_deal(client, tokens, deal_payload, fake_ai)

        response = await resolve(
            client,
            tokens,
            deal["id"],
            action="split",
            reasoning="Part of the work is usable.",
            seller_amount="100.00",
        )
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["state"] == "SPLIT"
        assert body["to_seller"] == "100.00"
        assert body["to_buyer"] == "150.00"
        assert fake_paypal.total_paid_out == Decimal("100.00")
        assert fake_paypal.total_refunded == Decimal("150.00")

    async def test_a_split_without_an_amount_is_rejected(
        self, client, tokens, deal_payload, fake_ai, fake_paypal
    ):
        deal = await disputed_deal(client, tokens, deal_payload, fake_ai)
        response = await resolve(client, tokens, deal["id"], action="split", reasoning="Partial.")
        assert response.status_code == 422
        assert fake_paypal.payouts == []

    @pytest.mark.parametrize("amount", ["0.00", "250.00", "400.00"])
    async def test_a_split_outside_the_deal_amount_is_rejected(
        self, client, tokens, deal_payload, fake_ai, fake_paypal, amount
    ):
        deal = await disputed_deal(client, tokens, deal_payload, fake_ai)
        response = await resolve(
            client,
            tokens,
            deal["id"],
            action="split",
            reasoning="Partial.",
            seller_amount=amount,
        )
        assert response.status_code in {422, 502}
        assert fake_paypal.payouts == []
        assert fake_paypal.refunds == []

    async def test_a_seller_amount_on_a_non_split_is_rejected(
        self, client, tokens, deal_payload, fake_ai
    ):
        deal = await disputed_deal(client, tokens, deal_payload, fake_ai)
        response = await resolve(
            client,
            tokens,
            deal["id"],
            action="refund",
            reasoning="Full refund.",
            seller_amount="100.00",
        )
        assert response.status_code == 422


class TestAuthorizationAndGuards:
    @pytest.mark.parametrize("role", ["buyer", "seller"])
    async def test_a_party_cannot_resolve_its_own_dispute(
        self, client, tokens, deal_payload, fake_ai, fake_paypal, role
    ):
        deal = await disputed_deal(client, tokens, deal_payload, fake_ai)
        response = await client.post(
            f"/deals/{deal['id']}/dispute/resolve",
            json={"action": "release", "reasoning": "Please pay me."},
            headers=auth(tokens[role]),
        )
        assert response.status_code == 403
        assert fake_paypal.payouts == []

    async def test_a_decision_must_carry_reasoning(self, client, tokens, deal_payload, fake_ai):
        """Explainability is enforced, not encouraged."""
        deal = await disputed_deal(client, tokens, deal_payload, fake_ai)
        response = await resolve(client, tokens, deal["id"], action="refund", reasoning="")
        assert response.status_code == 422

    async def test_a_deal_that_is_not_disputed_cannot_be_resolved(
        self, client, tokens, deal_payload, fake_paypal
    ):
        deal = await create_deal(client, tokens, deal_payload)
        await confirm_both(client, tokens, deal["id"])
        await fund(client, tokens, deal["id"])

        response = await resolve(
            client, tokens, deal["id"], action="refund", reasoning="Just because."
        )
        assert response.status_code == 409
        assert fake_paypal.refunds == []

    async def test_an_already_resolved_dispute_cannot_be_resolved_again(
        self, client, tokens, deal_payload, fake_ai, fake_paypal
    ):
        """Terminal states are terminal, so no second payout is possible."""
        deal = await disputed_deal(client, tokens, deal_payload, fake_ai)
        first = await resolve(
            client, tokens, deal["id"], action="refund", reasoning="Not as agreed."
        )
        assert first.status_code == 200

        second = await resolve(
            client, tokens, deal["id"], action="release", reasoning="Changed my mind."
        )
        assert second.status_code == 409
        assert len(fake_paypal.refunds) == 1
        assert fake_paypal.payouts == []

    async def test_a_failed_refund_rolls_back_the_resolution(
        self, client, tokens, deal_payload, fake_ai, fake_paypal
    ):
        deal = await disputed_deal(client, tokens, deal_payload, fake_ai)

        fake_paypal.fail_next_refund = True
        response = await resolve(
            client, tokens, deal["id"], action="refund", reasoning="Not as agreed."
        )
        assert response.status_code == 502

        current = await client.get(f"/deals/{deal['id']}", headers=auth(tokens["reviewer"]))
        assert current.json()["state"] == "DISPUTED"
        assert fake_paypal.refunds == []
        # The human report must not survive a settlement that did not happen.
        assert len(current.json()["verification_reports"]) == 1
