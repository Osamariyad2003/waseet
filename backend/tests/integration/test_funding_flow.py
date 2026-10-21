"""Deal creation, criteria confirmation and funding, through the real API."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.conftest import auth


async def create_deal(client, tokens, deal_payload) -> dict:
    response = await client.post("/deals", json=deal_payload, headers=auth(tokens["buyer"]))
    assert response.status_code == 201, response.text
    return response.json()


async def confirm_both(client, tokens, deal_id: str) -> None:
    for role in ("buyer", "seller"):
        response = await client.post(
            f"/deals/{deal_id}/criteria/confirm", headers=auth(tokens[role])
        )
        assert response.status_code == 200, response.text


async def fund(client, tokens, deal_id: str) -> dict:
    order = await client.post(f"/deals/{deal_id}/order", headers=auth(tokens["buyer"]))
    assert order.status_code == 201, order.text
    capture = await client.post(
        f"/deals/{deal_id}/capture",
        json={"paypal_order_id": order.json()["paypal_order_id"]},
        headers=auth(tokens["buyer"]),
    )
    assert capture.status_code == 200, capture.text
    return capture.json()


class TestDealCreation:
    async def test_a_deal_is_created_with_ai_drafted_criteria(
        self, client, tokens, deal_payload, fake_ai
    ):
        deal = await create_deal(client, tokens, deal_payload)

        assert deal["state"] == "DRAFT"
        assert deal["amount"] == "250.00"
        assert len(deal["criteria"]) == len(fake_ai.criteria)
        assert fake_ai.draft_calls == 1
        assert all(
            not criterion["confirmed_by_buyer"] and not criterion["confirmed_by_seller"]
            for criterion in deal["criteria"]
        )

    async def test_creation_writes_an_audit_entry(self, client, tokens, deal_payload):
        deal = await create_deal(client, tokens, deal_payload)
        audit = await client.get(f"/deals/{deal['id']}/audit", headers=auth(tokens["buyer"]))

        entries = audit.json()
        assert len(entries) == 1
        assert entries[0]["to_state"] == "DRAFT"
        assert entries[0]["actor"] == "ai"
        assert "drafted" in entries[0]["reason"]

    async def test_a_failing_criteria_agent_leaves_no_half_built_deal(
        self, client, tokens, deal_payload, fake_ai
    ):
        """The deal and its criteria commit together or not at all."""
        fake_ai.raise_on_draft = True
        response = await client.post("/deals", json=deal_payload, headers=auth(tokens["buyer"]))
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "ai_error"

        listed = await client.get("/deals", headers=auth(tokens["buyer"]))
        assert listed.json() == []

    async def test_a_seller_cannot_create_a_deal(self, client, tokens, deal_payload):
        response = await client.post("/deals", json=deal_payload, headers=auth(tokens["seller"]))
        assert response.status_code == 422

    async def test_an_unknown_seller_is_rejected(self, client, tokens, deal_payload):
        response = await client.post(
            "/deals",
            json={**deal_payload, "seller_email": "nobody@sandbox.example.com"},
            headers=auth(tokens["buyer"]),
        )
        assert response.status_code == 422
        assert "seller" in response.json()["error"]["message"]

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("amount", "0"),
            ("amount", "-5.00"),
            ("amount", "999999.00"),
            ("currency", "XYZ"),
            ("description", "too short"),
            ("title", ""),
        ],
    )
    async def test_invalid_input_is_rejected_at_the_edge(
        self, client, tokens, deal_payload, field, value
    ):
        response = await client.post(
            "/deals", json={**deal_payload, field: value}, headers=auth(tokens["buyer"])
        )
        assert response.status_code == 422

    async def test_an_unauthenticated_request_is_refused(self, client, deal_payload):
        response = await client.post("/deals", json=deal_payload)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "authentication_failed"


class TestCriteriaConfirmation:
    async def test_each_party_confirms_its_own_side(self, client, tokens, deal_payload):
        deal = await create_deal(client, tokens, deal_payload)

        after_buyer = await client.post(
            f"/deals/{deal['id']}/criteria/confirm", headers=auth(tokens["buyer"])
        )
        criteria = after_buyer.json()["criteria"]
        assert all(criterion["confirmed_by_buyer"] for criterion in criteria)
        assert not any(criterion["confirmed_by_seller"] for criterion in criteria)

        after_seller = await client.post(
            f"/deals/{deal['id']}/criteria/confirm", headers=auth(tokens["seller"])
        )
        criteria = after_seller.json()["criteria"]
        assert all(
            criterion["confirmed_by_buyer"] and criterion["confirmed_by_seller"]
            for criterion in criteria
        )

    async def test_a_stranger_cannot_confirm_or_even_see_the_deal(
        self, client, tokens, deal_payload
    ):
        """A deal that belongs to someone else reads as not found, so the
        endpoint does not confirm which deal ids exist."""
        deal = await create_deal(client, tokens, deal_payload)
        response = await client.post(
            f"/deals/{deal['id']}/criteria/confirm", headers=auth(tokens["reviewer"])
        )
        assert response.status_code == 404


class TestFunding:
    async def test_funding_captures_into_escrow(self, client, tokens, deal_payload, fake_paypal):
        deal = await create_deal(client, tokens, deal_payload)
        await confirm_both(client, tokens, deal["id"])
        funded = await fund(client, tokens, deal["id"])

        assert funded["state"] == "FUNDED"
        assert funded["paypal_capture_id"] is not None
        assert len(fake_paypal.captures) == 1
        captured = next(iter(fake_paypal.captures.values()))
        assert captured["amount"] == Decimal("250.00")

    async def test_funding_is_refused_until_both_parties_confirm(
        self, client, tokens, deal_payload, fake_paypal
    ):
        """FR-2: both parties confirm before funding."""
        deal = await create_deal(client, tokens, deal_payload)

        response = await client.post(f"/deals/{deal['id']}/order", headers=auth(tokens["buyer"]))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "transition_guard_failed"
        assert fake_paypal.orders == {}

        # One side alone is not enough either.
        await client.post(f"/deals/{deal['id']}/criteria/confirm", headers=auth(tokens["buyer"]))
        response = await client.post(f"/deals/{deal['id']}/order", headers=auth(tokens["buyer"]))
        assert response.status_code == 409

    async def test_only_the_buyer_can_fund(self, client, tokens, deal_payload):
        deal = await create_deal(client, tokens, deal_payload)
        await confirm_both(client, tokens, deal["id"])

        response = await client.post(f"/deals/{deal['id']}/order", headers=auth(tokens["seller"]))
        assert response.status_code == 403

    async def test_the_order_is_created_with_a_deterministic_idempotency_key(
        self, client, tokens, deal_payload, fake_paypal
    ):
        """A retried create returns the same order, never a second one."""
        deal = await create_deal(client, tokens, deal_payload)
        await confirm_both(client, tokens, deal["id"])

        first = await client.post(f"/deals/{deal['id']}/order", headers=auth(tokens["buyer"]))
        second = await client.post(f"/deals/{deal['id']}/order", headers=auth(tokens["buyer"]))

        assert first.json()["paypal_order_id"] == second.json()["paypal_order_id"]
        assert len(fake_paypal.orders) == 1

    async def test_a_replayed_capture_does_not_fund_twice(
        self, client, tokens, deal_payload, fake_paypal
    ):
        deal = await create_deal(client, tokens, deal_payload)
        await confirm_both(client, tokens, deal["id"])
        await fund(client, tokens, deal["id"])

        again = await client.post(
            f"/deals/{deal['id']}/capture", json={}, headers=auth(tokens["buyer"])
        )
        assert again.status_code == 200
        assert again.json()["state"] == "FUNDED"
        assert len(fake_paypal.captures) == 1

        audit = await client.get(f"/deals/{deal['id']}/audit", headers=auth(tokens["buyer"]))
        captures = [entry for entry in audit.json() if entry["event"] == "payment_captured"]
        assert len(captures) == 1

    async def test_a_capture_for_someone_elses_order_is_refused(self, client, tokens, deal_payload):
        """The client cannot nominate a different order to capture."""
        deal = await create_deal(client, tokens, deal_payload)
        await confirm_both(client, tokens, deal["id"])
        await client.post(f"/deals/{deal['id']}/order", headers=auth(tokens["buyer"]))

        response = await client.post(
            f"/deals/{deal['id']}/capture",
            json={"paypal_order_id": "ORDER-9999"},
            headers=auth(tokens["buyer"]),
        )
        assert response.status_code == 422

    async def test_a_failed_capture_leaves_the_deal_in_draft(
        self, client, tokens, deal_payload, fake_paypal
    ):
        deal = await create_deal(client, tokens, deal_payload)
        await confirm_both(client, tokens, deal["id"])
        await client.post(f"/deals/{deal['id']}/order", headers=auth(tokens["buyer"]))

        fake_paypal.fail_next_capture = True
        response = await client.post(
            f"/deals/{deal['id']}/capture", json={}, headers=auth(tokens["buyer"])
        )
        assert response.status_code == 502

        current = await client.get(f"/deals/{deal['id']}", headers=auth(tokens["buyer"]))
        assert current.json()["state"] == "DRAFT"
        assert current.json()["paypal_capture_id"] is None

    async def test_a_declined_capture_does_not_fund_the_deal(
        self, client, tokens, deal_payload, fake_paypal
    ):
        deal = await create_deal(client, tokens, deal_payload)
        await confirm_both(client, tokens, deal["id"])
        await client.post(f"/deals/{deal['id']}/order", headers=auth(tokens["buyer"]))

        fake_paypal.capture_status = "DECLINED"
        response = await client.post(
            f"/deals/{deal['id']}/capture", json={}, headers=auth(tokens["buyer"])
        )
        assert response.status_code == 502

        current = await client.get(f"/deals/{deal['id']}", headers=auth(tokens["buyer"]))
        assert current.json()["state"] == "DRAFT"


class TestTimelineAndListing:
    async def test_both_parties_see_the_deal_and_its_timeline(self, client, tokens, deal_payload):
        deal = await create_deal(client, tokens, deal_payload)
        await confirm_both(client, tokens, deal["id"])

        for role in ("buyer", "seller"):
            response = await client.get(f"/deals/{deal['id']}", headers=auth(tokens[role]))
            assert response.status_code == 200
            body = response.json()
            assert body["state"] == "DRAFT"
            assert len(body["timeline"]) >= 3  # created + two confirmations

    async def test_a_party_only_lists_their_own_deals(self, client, tokens, deal_payload):
        await create_deal(client, tokens, deal_payload)

        buyer_deals = await client.get("/deals", headers=auth(tokens["buyer"]))
        seller_deals = await client.get("/deals", headers=auth(tokens["seller"]))
        reviewer_deals = await client.get("/deals", headers=auth(tokens["reviewer"]))

        assert len(buyer_deals.json()) == 1
        assert len(seller_deals.json()) == 1
        # The reviewer queue is DISPUTED deals, and there are none yet.
        assert reviewer_deals.json() == []

    async def test_deals_can_be_filtered_by_state(self, client, tokens, deal_payload):
        await create_deal(client, tokens, deal_payload)

        drafts = await client.get("/deals?state=DRAFT", headers=auth(tokens["buyer"]))
        funded = await client.get("/deals?state=FUNDED", headers=auth(tokens["buyer"]))

        assert len(drafts.json()) == 1
        assert funded.json() == []

    async def test_an_unknown_deal_is_a_404(self, client, tokens):
        response = await client.get(
            "/deals/11111111-1111-1111-1111-111111111111", headers=auth(tokens["buyer"])
        )
        assert response.status_code == 404


class TestClientToken:
    """PayPal JS SDK v6 authenticates the browser with a short-lived client
    token, so the client secret never reaches the browser."""

    async def test_an_authenticated_user_gets_a_browser_safe_token(self, client, tokens):
        response = await client.get("/paypal/client-token", headers=auth(tokens["buyer"]))
        assert response.status_code == 200
        assert response.json()["client_token"] == "fake-browser-safe-client-token"

    async def test_the_response_names_the_sandbox_sdk_url(self, client, tokens):
        """So the browser loads the sandbox SDK, not production, against a
        sandbox order."""
        response = await client.get("/paypal/client-token", headers=auth(tokens["buyer"]))
        assert response.json()["sdk_url"] == "https://www.sandbox.paypal.com/web-sdk/v6/core"

    async def test_an_anonymous_caller_cannot_mint_tokens(self, client):
        """Otherwise anyone could burn through the platform's credentials."""
        response = await client.get("/paypal/client-token")
        assert response.status_code == 401

    async def test_a_paypal_failure_surfaces_as_a_gateway_error(self, client, tokens, fake_paypal):
        fake_paypal.fail_next_client_token = True
        response = await client.get("/paypal/client-token", headers=auth(tokens["buyer"]))
        assert response.status_code == 502
