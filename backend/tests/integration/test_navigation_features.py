"""Integration tests for the four navigation features: Home, Explore, Wallet, and Account."""

from __future__ import annotations

from decimal import Decimal

from tests.conftest import auth
from tests.integration.test_funding_flow import confirm_both, create_deal, fund


class TestWalletFeature:
    async def test_wallet_requires_auth(self, client):
        response = await client.get("/wallet/overview")
        assert response.status_code == 401

    async def test_wallet_empty_overview(self, client, tokens):
        response = await client.get("/wallet/overview", headers=auth(tokens["buyer"]))
        assert response.status_code == 200
        body = response.json()
        assert body["held"]["count"] == 0
        assert body["held"]["amount"] == "0"
        assert body["released"]["count"] == 0
        assert body["refunded"]["count"] == 0
        assert body["pending"]["count"] == 0
        assert body["deals"] == []

    async def test_wallet_aggregates_balances(self, client, tokens, deal_payload):
        # Create a draft deal (pending)
        deal = await create_deal(client, tokens, deal_payload)

        response = await client.get("/wallet/overview", headers=auth(tokens["buyer"]))
        assert response.status_code == 200
        body = response.json()
        assert body["pending"]["count"] == 1
        assert Decimal(body["pending"]["amount"]) == Decimal(deal_payload["amount"])
        assert body["held"]["count"] == 0
        assert len(body["deals"]) == 1

        # Fund the deal -> moves from pending to held
        await confirm_both(client, tokens, deal["id"])
        await fund(client, tokens, deal["id"])

        response_funded = await client.get("/wallet/overview", headers=auth(tokens["buyer"]))
        assert response_funded.status_code == 200
        body_funded = response_funded.json()
        assert body_funded["held"]["count"] == 1
        assert Decimal(body_funded["held"]["amount"]) == Decimal(deal_payload["amount"])
        assert body_funded["pending"]["count"] == 0


class TestExploreFeature:
    async def test_explore_is_publicly_accessible(self, client):
        response = await client.get("/explore")
        assert response.status_code == 200
        body = response.json()

        assert body["title"] == "How Waseet Works"
        assert len(body["steps"]) == 4
        step_keys = [s["key"] for s in body["steps"]]
        assert step_keys == ["create", "fund", "deliver", "settle"]

        assert len(body["safety_pillars"]) == 4
        pillar_keys = [p["key"] for p in body["safety_pillars"]]
        assert pillar_keys == ["decide", "gate", "failsafe", "bounded"]

        assert body["platform_info"]["sandbox_mode"] is True
        assert "confidence_threshold" in body["platform_info"]
        assert "total_deals" in body["stats"]


class TestAccountFeature:
    async def test_account_profile_requires_auth(self, client):
        response = await client.get("/account/profile")
        assert response.status_code == 401

    async def test_get_and_update_account_profile(self, client, tokens, deal_payload):
        # Get profile
        get_res = await client.get("/account/profile", headers=auth(tokens["buyer"]))
        assert get_res.status_code == 200
        profile = get_res.json()
        assert profile["role"] == "buyer"
        assert profile["total_deals"] == 0

        # Create a deal as buyer
        await create_deal(client, tokens, deal_payload)

        updated_profile_res = await client.get("/account/profile", headers=auth(tokens["buyer"]))
        assert updated_profile_res.status_code == 200
        updated_profile = updated_profile_res.json()
        assert updated_profile["total_deals"] == 1
        assert updated_profile["deals_as_buyer"] == 1
        assert updated_profile["deals_as_seller"] == 0

        # Update profile name
        patch_res = await client.patch(
            "/account/profile",
            json={"full_name": "Verified Buyer Name", "paypal_account_ref": "buyer-sb@test.com"},
            headers=auth(tokens["buyer"]),
        )
        assert patch_res.status_code == 200
        patched = patch_res.json()
        assert patched["full_name"] == "Verified Buyer Name"
        assert patched["paypal_account_ref"] == "buyer-sb@test.com"


class TestHomeFeature:
    async def test_home_summary_requires_auth(self, client):
        response = await client.get("/home/summary")
        assert response.status_code == 401

    async def test_home_summary_metrics(self, client, tokens, deal_payload):
        res = await client.get("/home/summary", headers=auth(tokens["buyer"]))
        assert res.status_code == 200
        body = res.json()
        assert body["active_deals_count"] == 0
        assert body["action_required_count"] == 0
        assert body["recent_deals"] == []

        # Create deal -> in DRAFT, buyer unconfirmed -> action required
        deal = await create_deal(client, tokens, deal_payload)

        res_after = await client.get("/home/summary", headers=auth(tokens["buyer"]))
        assert res_after.status_code == 200
        body_after = res_after.json()
        assert body_after["active_deals_count"] == 1
        assert body_after["action_required_count"] == 1
        assert len(body_after["recent_deals"]) == 1
        assert body_after["recent_deals"][0]["id"] == deal["id"]
