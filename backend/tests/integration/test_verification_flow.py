"""The agentic loop end to end: deliver -> verify -> policy -> release or dispute.

These are the tests that matter most. Every one of them is really asking the
same question from a different angle: can anything other than a confident,
consistent pass get money out of escrow?
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.enums import Verdict
from tests.conftest import auth
from tests.integration.test_funding_flow import confirm_both, create_deal, fund


async def funded_deal(client, tokens, deal_payload) -> dict:
    deal = await create_deal(client, tokens, deal_payload)
    await confirm_both(client, tokens, deal["id"])
    return await fund(client, tokens, deal["id"])


async def deliver(client, tokens, deal_id: str, **overrides) -> dict:
    payload = {
        "type": "url",
        "content_ref": "https://files.example.com/logo.svg",
        **overrides,
    }
    response = await client.post(
        f"/deals/{deal_id}/deliverable", json=payload, headers=auth(tokens["seller"])
    )
    assert response.status_code == 201, response.text
    return response.json()


async def verify(client, tokens, deal_id: str, role: str = "seller") -> dict:
    response = await client.post(f"/deals/{deal_id}/verify", headers=auth(tokens[role]))
    assert response.status_code == 200, response.text
    return response.json()


class TestDelivery:
    async def test_the_seller_submits_and_the_deal_becomes_delivered(
        self, client, tokens, deal_payload
    ):
        deal = await funded_deal(client, tokens, deal_payload)
        await deliver(client, tokens, deal["id"])

        current = await client.get(f"/deals/{deal['id']}", headers=auth(tokens["seller"]))
        assert current.json()["state"] == "DELIVERED"

    async def test_the_buyer_cannot_submit_the_deliverable(self, client, tokens, deal_payload):
        deal = await funded_deal(client, tokens, deal_payload)
        response = await client.post(
            f"/deals/{deal['id']}/deliverable",
            json={"type": "text", "content_ref": "done"},
            headers=auth(tokens["buyer"]),
        )
        assert response.status_code == 403

    async def test_an_unfunded_deal_cannot_be_delivered(self, client, tokens, deal_payload):
        """No delivery before the money is actually held."""
        deal = await create_deal(client, tokens, deal_payload)
        await confirm_both(client, tokens, deal["id"])

        response = await client.post(
            f"/deals/{deal['id']}/deliverable",
            json={"type": "text", "content_ref": "done"},
            headers=auth(tokens["seller"]),
        )
        assert response.status_code == 409

    @pytest.mark.parametrize("content", ["", "   "])
    async def test_an_empty_deliverable_is_rejected(self, client, tokens, deal_payload, content):
        deal = await funded_deal(client, tokens, deal_payload)
        response = await client.post(
            f"/deals/{deal['id']}/deliverable",
            json={"type": "text", "content_ref": content},
            headers=auth(tokens["seller"]),
        )
        assert response.status_code == 422


class TestAutoRelease:
    async def test_a_confident_pass_auto_releases_to_the_seller(
        self, client, tokens, deal_payload, fake_paypal, fake_ai
    ):
        """FR-6, the happy path."""
        fake_ai.verdict = Verdict.PASS
        fake_ai.confidence = Decimal("0.95")

        deal = await funded_deal(client, tokens, deal_payload)
        await deliver(client, tokens, deal["id"])
        result = await verify(client, tokens, deal["id"])

        assert result["released"] is True
        assert result["state"] == "RELEASED"
        assert result["policy_outcome"] == "auto_release"
        assert result["report"]["verdict"] == "pass"
        assert result["report"]["decided_by"] == "ai"

        assert len(fake_paypal.payouts) == 1
        payout = fake_paypal.payouts[0]
        assert payout["amount"] == Decimal("250.00")
        assert payout["receiver_email"] == "seller@sandbox.example.com"
        assert fake_paypal.refunds == []

    async def test_the_release_is_explained_in_the_audit_trail(self, client, tokens, deal_payload):
        deal = await funded_deal(client, tokens, deal_payload)
        await deliver(client, tokens, deal["id"])
        await verify(client, tokens, deal["id"])

        audit = await client.get(f"/deals/{deal['id']}/audit", headers=auth(tokens["buyer"]))
        entries = audit.json()
        released = next(entry for entry in entries if entry["to_state"] == "RELEASED")

        assert released["actor"] == "ai"
        assert "confidence" in released["reason"]
        assert released["paypal_reference"] is not None

        states = [entry["to_state"] for entry in entries]
        assert states[-3:] == ["DELIVERED", "VERIFYING", "RELEASED"]

    async def test_the_verifier_receives_the_deliverable_as_data(
        self, client, tokens, deal_payload, fake_ai
    ):
        deal = await funded_deal(client, tokens, deal_payload)
        await deliver(client, tokens, deal["id"], content_ref="https://files.example.com/brand.svg")
        await verify(client, tokens, deal["id"])

        assert fake_ai.verify_calls == 1
        assert fake_ai.last_deliverable is not None
        assert fake_ai.last_deliverable.content_ref == "https://files.example.com/brand.svg"

    async def test_the_response_states_that_the_verdict_is_advisory(
        self, client, tokens, deal_payload
    ):
        """SRS honesty requirement: never presented as a guarantee."""
        deal = await funded_deal(client, tokens, deal_payload)
        await deliver(client, tokens, deal["id"])
        result = await verify(client, tokens, deal["id"])

        assert "advisory" in result["advisory_notice"].lower()
        assert "human reviewer" in result["advisory_notice"]

    async def test_the_platform_fee_is_taken_out_of_the_release(
        self, client, tokens, deal_payload, fake_paypal, monkeypatch
    ):
        """FR-13, optional and off by default."""
        from app.config import get_settings

        get_settings.cache_clear()
        monkeypatch.setenv("PLATFORM_FEE_PERCENT", "2.5")
        try:
            deal = await funded_deal(client, tokens, deal_payload)
            await deliver(client, tokens, deal["id"])
            await verify(client, tokens, deal["id"])

            assert fake_paypal.payouts[0]["amount"] == Decimal("243.75")
        finally:
            monkeypatch.delenv("PLATFORM_FEE_PERCENT", raising=False)
            get_settings.cache_clear()


class TestFailsSafeNotOpen:
    async def test_a_failed_verification_disputes_and_holds_the_money(
        self, client, tokens, deal_payload, fake_paypal, fake_ai
    ):
        """FR-7: a high-confidence fail routes to DISPUTED."""
        fake_ai.verdict = Verdict.FAIL
        fake_ai.confidence = Decimal("0.93")
        fake_ai.reasoning = "The logo is a raster PNG, not a vector file."

        deal = await funded_deal(client, tokens, deal_payload)
        await deliver(client, tokens, deal["id"])
        result = await verify(client, tokens, deal["id"])

        assert result["released"] is False
        assert result["state"] == "DISPUTED"
        assert result["policy_outcome"] == "dispute"
        assert fake_paypal.payouts == []
        assert fake_paypal.refunds == []

    async def test_a_low_confidence_pass_disputes_and_holds_the_money(
        self, client, tokens, deal_payload, fake_paypal, fake_ai
    ):
        fake_ai.verdict = Verdict.PASS
        fake_ai.confidence = Decimal("0.55")

        deal = await funded_deal(client, tokens, deal_payload)
        await deliver(client, tokens, deal["id"])
        result = await verify(client, tokens, deal["id"])

        assert result["state"] == "DISPUTED"
        assert "below the auto-release threshold" in result["policy_reason"]
        assert fake_paypal.payouts == []

    async def test_an_unavailable_verifier_disputes_rather_than_failing_the_request(
        self, client, tokens, deal_payload, fake_paypal, fake_ai
    ):
        """A broken model must never 500 the flow or release the funds."""
        fake_ai.return_inconclusive = True

        deal = await funded_deal(client, tokens, deal_payload)
        await deliver(client, tokens, deal["id"])
        result = await verify(client, tokens, deal["id"])

        assert result["state"] == "DISPUTED"
        assert result["report"]["verdict"] == "inconclusive"
        assert fake_paypal.payouts == []

    async def test_the_reasoning_is_stored_even_when_the_deal_disputes(
        self, client, tokens, deal_payload, fake_ai
    ):
        """Explainability does not depend on the outcome being good news."""
        fake_ai.verdict = Verdict.FAIL
        fake_ai.reasoning = "Criterion two is unmet: the file is not a vector."

        deal = await funded_deal(client, tokens, deal_payload)
        await deliver(client, tokens, deal["id"])
        await verify(client, tokens, deal["id"])

        report = await client.get(
            f"/deals/{deal['id']}/verification", headers=auth(tokens["buyer"])
        )
        body = report.json()
        assert body["reasoning"] == "Criterion two is unmet: the file is not a vector."
        assert body["per_criterion"]

    async def test_a_dispute_records_which_criteria_were_unmet(
        self, client, tokens, deal_payload, fake_ai
    ):
        deal = await funded_deal(client, tokens, deal_payload)
        await deliver(client, tokens, deal["id"])

        # Fail the second criterion specifically.
        current = await client.get(f"/deals/{deal['id']}", headers=auth(tokens["buyer"]))
        second = current.json()["criteria"][1]
        fake_ai.verdict = Verdict.FAIL
        fake_ai.failed_criteria_ids = (second["id"],)

        await verify(client, tokens, deal["id"])

        audit = await client.get(f"/deals/{deal['id']}/audit", headers=auth(tokens["buyer"]))
        disputed = next(entry for entry in audit.json() if entry["to_state"] == "DISPUTED")
        assert second["text"] in disputed["reason"]

    async def test_a_failed_payout_rolls_back_the_release(
        self, client, tokens, deal_payload, fake_paypal
    ):
        """If PayPal refuses, the deal must not claim RELEASED."""
        deal = await funded_deal(client, tokens, deal_payload)
        await deliver(client, tokens, deal["id"])

        fake_paypal.fail_next_payout = True
        response = await client.post(f"/deals/{deal['id']}/verify", headers=auth(tokens["seller"]))
        assert response.status_code == 502

        current = await client.get(f"/deals/{deal['id']}", headers=auth(tokens["buyer"]))
        # The deal is left in VERIFYING — mid-flight, not falsely settled —
        # and no money moved.
        assert current.json()["state"] == "VERIFYING"
        assert fake_paypal.payouts == []


class TestBuyerContest:
    async def test_the_buyer_can_contest_a_delivery(
        self, client, tokens, deal_payload, fake_paypal
    ):
        deal = await funded_deal(client, tokens, deal_payload)
        await deliver(client, tokens, deal["id"])

        response = await client.post(
            f"/deals/{deal['id']}/contest",
            json={"reason": "The file will not open."},
            headers=auth(tokens["buyer"]),
        )
        assert response.status_code == 200
        assert response.json()["state"] == "DISPUTED"
        assert fake_paypal.payouts == []

    async def test_the_buyer_can_contest_before_delivery(self, client, tokens, deal_payload):
        """The SRS allows a contest from FUNDED as well as DELIVERED."""
        deal = await funded_deal(client, tokens, deal_payload)
        response = await client.post(
            f"/deals/{deal['id']}/contest",
            json={"reason": "The seller has gone quiet."},
            headers=auth(tokens["buyer"]),
        )
        assert response.status_code == 200
        assert response.json()["state"] == "DISPUTED"

    async def test_the_seller_cannot_contest(self, client, tokens, deal_payload):
        deal = await funded_deal(client, tokens, deal_payload)
        response = await client.post(
            f"/deals/{deal['id']}/contest",
            json={"reason": "I want out."},
            headers=auth(tokens["seller"]),
        )
        assert response.status_code == 403

    async def test_a_contest_needs_a_reason(self, client, tokens, deal_payload):
        deal = await funded_deal(client, tokens, deal_payload)
        response = await client.post(
            f"/deals/{deal['id']}/contest", json={"reason": ""}, headers=auth(tokens["buyer"])
        )
        assert response.status_code == 422

    async def test_a_released_deal_cannot_be_contested(self, client, tokens, deal_payload):
        """Terminal is terminal."""
        deal = await funded_deal(client, tokens, deal_payload)
        await deliver(client, tokens, deal["id"])
        await verify(client, tokens, deal["id"])

        response = await client.post(
            f"/deals/{deal['id']}/contest",
            json={"reason": "I changed my mind."},
            headers=auth(tokens["buyer"]),
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_transition"


class TestVerificationIdempotency:
    async def test_re_verifying_a_released_deal_does_not_pay_again(
        self, client, tokens, deal_payload, fake_paypal, fake_ai
    ):
        deal = await funded_deal(client, tokens, deal_payload)
        await deliver(client, tokens, deal["id"])
        await verify(client, tokens, deal["id"])

        again = await verify(client, tokens, deal["id"])
        assert again["state"] == "RELEASED"
        assert len(fake_paypal.payouts) == 1
        assert fake_ai.verify_calls == 1  # the agent is not re-run either

    async def test_re_verifying_a_disputed_deal_does_not_change_it(
        self, client, tokens, deal_payload, fake_paypal, fake_ai
    ):
        fake_ai.verdict = Verdict.FAIL

        deal = await funded_deal(client, tokens, deal_payload)
        await deliver(client, tokens, deal["id"])
        await verify(client, tokens, deal["id"])

        again = await verify(client, tokens, deal["id"])
        assert again["state"] == "DISPUTED"
        assert fake_paypal.payouts == []
        assert fake_ai.verify_calls == 1

    async def test_verification_before_delivery_is_refused(
        self, client, tokens, deal_payload, fake_ai
    ):
        deal = await funded_deal(client, tokens, deal_payload)
        response = await client.post(f"/deals/{deal['id']}/verify", headers=auth(tokens["seller"]))
        assert response.status_code == 409
        assert fake_ai.verify_calls == 0

    async def test_a_stranger_cannot_trigger_verification(
        self, client, tokens, deal_payload, fake_ai
    ):
        deal = await funded_deal(client, tokens, deal_payload)
        await deliver(client, tokens, deal["id"])

        response = await client.post(
            f"/deals/{deal['id']}/verify", headers=auth(tokens["reviewer"])
        )
        assert response.status_code == 403
        assert fake_ai.verify_calls == 0


class TestDeliverableIsInspected:
    """FR-5 end to end: the link is resolved before the verifier judges it."""

    async def test_a_submitted_link_is_fetched_before_verification(
        self, client, tokens, deal_payload, fake_fetcher
    ):
        deal = await funded_deal(client, tokens, deal_payload)
        await deliver(client, tokens, deal["id"], content_ref="https://files.example.com/logo.svg")
        await verify(client, tokens, deal["id"])

        assert fake_fetcher.fetched == ["https://files.example.com/logo.svg"]

    async def test_the_verifier_receives_the_retrieved_content(
        self, client, tokens, deal_payload, fake_fetcher, fake_ai
    ):
        fake_fetcher.text = "A scalable vector logo with a transparent background."

        deal = await funded_deal(client, tokens, deal_payload)
        await deliver(client, tokens, deal["id"])
        await verify(client, tokens, deal["id"])

        assert fake_ai.last_deliverable is not None
        inspected = fake_ai.last_deliverable.inspected
        assert inspected is not None
        assert inspected.text == "A scalable vector logo with a transparent background."

    async def test_a_text_deliverable_is_not_fetched(
        self, client, tokens, deal_payload, fake_fetcher
    ):
        deal = await funded_deal(client, tokens, deal_payload)
        await deliver(client, tokens, deal["id"], type="text", content_ref="The finished copy.")
        await verify(client, tokens, deal["id"])

        assert fake_fetcher.fetched == []

    async def test_an_unreachable_link_still_reaches_a_human_not_a_payout(
        self, client, tokens, deal_payload, fake_fetcher, fake_ai, fake_paypal
    ):
        """A deliverable nobody could open must not be released on trust.

        The fetcher reports why, the verifier is told it has not seen the
        work, and in a real run that becomes a fail at low confidence. Here
        the gateway is faked, so the test pins the part the system controls:
        the reason reaches the verifier, and nothing pays out when it comes
        back unconvinced.
        """
        fake_fetcher.unavailable_reason = "the link points at a private or internal address"
        fake_ai.verdict = Verdict.FAIL
        fake_ai.confidence = Decimal("0.2")

        deal = await funded_deal(client, tokens, deal_payload)
        await deliver(client, tokens, deal["id"])
        result = await verify(client, tokens, deal["id"])

        inspected = fake_ai.last_deliverable.inspected
        assert inspected is not None and not inspected.is_available
        assert result["state"] == "DISPUTED"
        assert fake_paypal.payouts == []
