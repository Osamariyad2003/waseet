"""PayPal webhooks: signature verification and idempotency (FR-12).

The requirement under test is the SRS reliability clause — "a replayed
webhook never double-pays or double-refunds".
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.enums import Verdict
from tests.conftest import auth
from tests.integration.test_funding_flow import confirm_both, create_deal, fund
from tests.integration.test_verification_flow import deliver

SIGNATURE_HEADERS = {
    "paypal-transmission-id": "transmission-1",
    "paypal-transmission-time": "2026-10-20T10:00:00Z",
    "paypal-transmission-sig": "a-signature",
    "paypal-cert-url": "https://api.sandbox.paypal.com/cert.pem",
    "paypal-auth-algo": "SHA256withRSA",
}


def capture_event(deal_id: str, *, event_id: str = "WH-CAPTURE-1", capture_id: str = "CAPTURE-1"):
    return {
        "id": event_id,
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "id": capture_id,
            "custom_id": deal_id,
            "amount": {"currency_code": "USD", "value": "250.00"},
        },
    }


async def draft_deal_with_order(client, tokens, deal_payload) -> dict:
    """A confirmed deal with an order created but not yet captured."""
    deal = await create_deal(client, tokens, deal_payload)
    await confirm_both(client, tokens, deal["id"])
    await client.post(f"/deals/{deal['id']}/order", headers=auth(tokens["buyer"]))
    return deal


class TestSignatureVerification:
    async def test_a_verified_event_is_processed(self, client, tokens, deal_payload, fake_paypal):
        deal = await draft_deal_with_order(client, tokens, deal_payload)
        fake_paypal.webhook_verifies = True

        response = await client.post(
            "/webhooks/paypal", json=capture_event(deal["id"]), headers=SIGNATURE_HEADERS
        )
        assert response.status_code == 200
        assert response.json()["status"] == "processed"

    async def test_an_unverified_signature_is_rejected_and_changes_nothing(
        self, client, tokens, deal_payload, fake_paypal
    ):
        deal = await draft_deal_with_order(client, tokens, deal_payload)
        fake_paypal.webhook_verifies = False

        response = await client.post(
            "/webhooks/paypal", json=capture_event(deal["id"]), headers=SIGNATURE_HEADERS
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "webhook_verification_failed"

        current = await client.get(f"/deals/{deal['id']}", headers=auth(tokens["buyer"]))
        assert current.json()["state"] == "DRAFT"

    async def test_missing_signature_headers_are_rejected(self, client, tokens, deal_payload):
        deal = await draft_deal_with_order(client, tokens, deal_payload)
        response = await client.post("/webhooks/paypal", json=capture_event(deal["id"]))
        assert response.status_code == 401

    @pytest.mark.parametrize("missing", sorted(SIGNATURE_HEADERS))
    async def test_any_single_missing_header_is_rejected(
        self, client, tokens, deal_payload, missing
    ):
        deal = await draft_deal_with_order(client, tokens, deal_payload)
        headers = {k: v for k, v in SIGNATURE_HEADERS.items() if k != missing}

        response = await client.post(
            "/webhooks/paypal", json=capture_event(deal["id"]), headers=headers
        )
        assert response.status_code == 401

    async def test_a_malformed_body_is_rejected(self, client):
        response = await client.post(
            "/webhooks/paypal", content=b"not json", headers=SIGNATURE_HEADERS
        )
        assert response.status_code == 422

    async def test_a_body_without_an_event_id_is_rejected(self, client):
        response = await client.post(
            "/webhooks/paypal",
            json={"event_type": "PAYMENT.CAPTURE.COMPLETED"},
            headers=SIGNATURE_HEADERS,
        )
        assert response.status_code == 422


class TestIdempotency:
    async def test_a_redelivered_event_is_ignored(self, client, tokens, deal_payload):
        deal = await draft_deal_with_order(client, tokens, deal_payload)
        event = capture_event(deal["id"])

        first = await client.post("/webhooks/paypal", json=event, headers=SIGNATURE_HEADERS)
        second = await client.post("/webhooks/paypal", json=event, headers=SIGNATURE_HEADERS)
        third = await client.post("/webhooks/paypal", json=event, headers=SIGNATURE_HEADERS)

        assert first.json()["status"] == "processed"
        assert second.json()["status"] == "ignored"
        assert third.json()["status"] == "ignored"
        assert "already been processed" in second.json()["reason"]

    async def test_a_redelivered_capture_produces_one_audit_entry(
        self, client, tokens, deal_payload
    ):
        deal = await draft_deal_with_order(client, tokens, deal_payload)
        event = capture_event(deal["id"])

        for _ in range(3):
            await client.post("/webhooks/paypal", json=event, headers=SIGNATURE_HEADERS)

        audit = await client.get(f"/deals/{deal['id']}/audit", headers=auth(tokens["buyer"]))
        captures = [entry for entry in audit.json() if entry["event"] == "payment_captured"]
        assert len(captures) == 1

    async def test_a_capture_webhook_racing_the_api_capture_does_not_double_fund(
        self, client, tokens, deal_payload, fake_paypal
    ):
        """Both paths lead to FUNDED, and the second one is a no-op."""
        deal = await create_deal(client, tokens, deal_payload)
        await confirm_both(client, tokens, deal["id"])
        await fund(client, tokens, deal["id"])  # API capture wins

        capture_id = next(iter(fake_paypal.captures))
        response = await client.post(
            "/webhooks/paypal",
            json=capture_event(deal["id"], capture_id=capture_id),
            headers=SIGNATURE_HEADERS,
        )
        assert response.status_code == 200
        assert "already applied" in response.json()["outcome"]

        audit = await client.get(f"/deals/{deal['id']}/audit", headers=auth(tokens["buyer"]))
        captures = [entry for entry in audit.json() if entry["event"] == "payment_captured"]
        assert len(captures) == 1

    async def test_a_payout_webhook_after_release_never_pays_again(
        self, client, tokens, deal_payload, fake_paypal, fake_ai
    ):
        """The money-movement guarantee: a webhook confirms, it does not pay."""
        fake_ai.verdict = Verdict.PASS
        fake_ai.confidence = Decimal("0.95")

        deal = await create_deal(client, tokens, deal_payload)
        await confirm_both(client, tokens, deal["id"])
        await fund(client, tokens, deal["id"])
        await deliver(client, tokens, deal["id"])
        await client.post(f"/deals/{deal['id']}/verify", headers=auth(tokens["seller"]))
        assert len(fake_paypal.payouts) == 1

        for index in range(3):
            response = await client.post(
                "/webhooks/paypal",
                json={
                    "id": f"WH-PAYOUT-{index}",
                    "event_type": "PAYMENT.PAYOUTSBATCH.SUCCESS",
                    "resource": {"custom_id": deal["id"]},
                },
                headers=SIGNATURE_HEADERS,
            )
            assert response.status_code == 200

        assert len(fake_paypal.payouts) == 1
        current = await client.get(f"/deals/{deal['id']}", headers=auth(tokens["buyer"]))
        assert current.json()["state"] == "RELEASED"


class TestEventHandling:
    async def test_an_unhandled_event_type_is_recorded_and_ignored(
        self, client, tokens, deal_payload
    ):
        deal = await draft_deal_with_order(client, tokens, deal_payload)
        response = await client.post(
            "/webhooks/paypal",
            json={
                "id": "WH-OTHER-1",
                "event_type": "BILLING.SUBSCRIPTION.CREATED",
                "resource": {"custom_id": deal["id"]},
            },
            headers=SIGNATURE_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"
        assert "not handled" in response.json()["reason"]

    async def test_an_event_for_an_unknown_deal_is_ignored(self, client):
        response = await client.post(
            "/webhooks/paypal",
            json={
                "id": "WH-ORPHAN-1",
                "event_type": "PAYMENT.CAPTURE.COMPLETED",
                "resource": {"custom_id": "11111111-1111-1111-1111-111111111111"},
            },
            headers=SIGNATURE_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"

    async def test_a_non_uuid_custom_id_does_not_crash_the_handler(self, client):
        response = await client.post(
            "/webhooks/paypal",
            json={
                "id": "WH-JUNK-1",
                "event_type": "PAYMENT.CAPTURE.COMPLETED",
                "resource": {"custom_id": "'; DROP TABLE deals; --"},
            },
            headers=SIGNATURE_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"

    async def test_a_capture_webhook_funds_a_draft_deal(self, client, tokens, deal_payload):
        """The webhook can drive the transition if the API call never arrives."""
        deal = await draft_deal_with_order(client, tokens, deal_payload)

        response = await client.post(
            "/webhooks/paypal", json=capture_event(deal["id"]), headers=SIGNATURE_HEADERS
        )
        assert "FUNDED" in response.json()["outcome"]

        current = await client.get(f"/deals/{deal['id']}", headers=auth(tokens["buyer"]))
        assert current.json()["state"] == "FUNDED"

    async def test_a_denied_payout_is_surfaced_for_a_human_not_auto_reversed(
        self, client, tokens, deal_payload, fake_paypal, fake_ai
    ):
        deal = await create_deal(client, tokens, deal_payload)
        await confirm_both(client, tokens, deal["id"])
        await fund(client, tokens, deal["id"])
        await deliver(client, tokens, deal["id"])
        await client.post(f"/deals/{deal['id']}/verify", headers=auth(tokens["seller"]))

        response = await client.post(
            "/webhooks/paypal",
            json={
                "id": "WH-PAYOUT-DENIED-1",
                "event_type": "PAYMENT.PAYOUTSBATCH.DENIED",
                "resource": {"custom_id": deal["id"]},
            },
            headers=SIGNATURE_HEADERS,
        )
        assert response.status_code == 200

        audit = await client.get(f"/deals/{deal['id']}/audit", headers=auth(tokens["buyer"]))
        denied = next(
            entry for entry in audit.json() if entry["event"] == "PAYMENT.PAYOUTSBATCH.DENIED"
        )
        assert "reviewer" in denied["reason"]
        # The state is untouched: nothing silently reverses a terminal state.
        assert denied["from_state"] == denied["to_state"] == "RELEASED"


class TestSimulator:
    async def test_the_simulator_applies_an_event_without_a_signature(
        self, client, tokens, deal_payload
    ):
        """So the demo does not depend on a public tunnel being up."""
        deal = await draft_deal_with_order(client, tokens, deal_payload)

        response = await client.post("/webhooks/paypal/simulate", json=capture_event(deal["id"]))
        assert response.status_code == 200
        assert response.json()["status"] == "processed"

    async def test_the_simulator_is_still_idempotent(self, client, tokens, deal_payload):
        deal = await draft_deal_with_order(client, tokens, deal_payload)
        event = capture_event(deal["id"])

        await client.post("/webhooks/paypal/simulate", json=event)
        second = await client.post("/webhooks/paypal/simulate", json=event)
        assert second.json()["status"] == "ignored"

    async def test_the_simulator_is_unreachable_when_disabled(
        self, client, tokens, deal_payload, monkeypatch
    ):
        from app.config import get_settings

        deal = await draft_deal_with_order(client, tokens, deal_payload)

        get_settings.cache_clear()
        monkeypatch.setenv("ENABLE_WEBHOOK_SIMULATOR", "false")
        try:
            response = await client.post(
                "/webhooks/paypal/simulate", json=capture_event(deal["id"])
            )
            assert response.status_code == 404
        finally:
            monkeypatch.setenv("ENABLE_WEBHOOK_SIMULATOR", "true")
            get_settings.cache_clear()


class TestCaptureReferenceIsRecorded:
    """A deal funded by the webhook alone must still be settleable.

    If PayPal captured but our own capture call never ran, the deal would
    otherwise reach FUNDED with no capture reference — and then release and
    refund would both refuse it as having no captured payment.
    """

    async def test_the_capture_id_is_taken_from_the_event(self, client, tokens, deal_payload):
        deal = await draft_deal_with_order(client, tokens, deal_payload)

        await client.post(
            "/webhooks/paypal",
            json=capture_event(deal["id"], capture_id="3C679366HH908993F"),
            headers=SIGNATURE_HEADERS,
        )

        current = await client.get(f"/deals/{deal['id']}", headers=auth(tokens["buyer"]))
        body = current.json()
        assert body["state"] == "FUNDED"
        assert body["paypal_capture_id"] == "3C679366HH908993F"

    async def test_the_audit_entry_carries_that_reference(self, client, tokens, deal_payload):
        deal = await draft_deal_with_order(client, tokens, deal_payload)
        await client.post(
            "/webhooks/paypal",
            json=capture_event(deal["id"], capture_id="CAPTURE-FROM-WEBHOOK"),
            headers=SIGNATURE_HEADERS,
        )

        audit = await client.get(f"/deals/{deal['id']}/audit", headers=auth(tokens["buyer"]))
        funded = next(entry for entry in audit.json() if entry["to_state"] == "FUNDED")
        assert funded["paypal_reference"] == "CAPTURE-FROM-WEBHOOK"

    async def test_an_existing_capture_id_is_not_overwritten(
        self, client, tokens, deal_payload, fake_paypal
    ):
        """The API capture is the authority; a later event cannot repoint it."""
        deal = await create_deal(client, tokens, deal_payload)
        await confirm_both(client, tokens, deal["id"])
        funded = await fund(client, tokens, deal["id"])
        original = funded["paypal_capture_id"]

        await client.post(
            "/webhooks/paypal",
            json=capture_event(deal["id"], capture_id="SOMETHING-ELSE"),
            headers=SIGNATURE_HEADERS,
        )

        current = await client.get(f"/deals/{deal['id']}", headers=auth(tokens["buyer"]))
        assert current.json()["paypal_capture_id"] == original
