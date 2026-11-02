"""Integration tests for the /auth/signup endpoint."""

from __future__ import annotations

from tests.conftest import auth


class TestAuthSignup:
    async def test_signup_buyer_success(self, client):
        payload = {
            "email": "newbuyer@example.com",
            "password": "strong-password-123",
            "full_name": "New Buyer",
            "role": "buyer",
        }
        response = await client.post("/auth/signup", json=payload)
        assert response.status_code == 201
        body = response.json()

        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["expires_in"] > 0
        assert body["user"]["email"] == "newbuyer@example.com"
        assert body["user"]["full_name"] == "New Buyer"
        assert body["user"]["role"] == "buyer"

        # Verify token can access protected endpoints like /auth/me
        me_resp = await client.get("/auth/me", headers=auth(body["access_token"]))
        assert me_resp.status_code == 200
        assert me_resp.json()["email"] == "newbuyer@example.com"

    async def test_signup_seller_with_paypal_ref(self, client):
        payload = {
            "email": "newseller@example.com",
            "password": "seller-secure-password",
            "full_name": "Artisan Studio",
            "role": "seller",
            "paypal_account_ref": "sandbox-seller@personal.example.com",
        }
        response = await client.post("/auth/signup", json=payload)
        assert response.status_code == 201
        body = response.json()

        assert body["user"]["email"] == "newseller@example.com"
        assert body["user"]["role"] == "seller"

        # Can immediately sign in with the credentials
        login_resp = await client.post(
            "/auth/login",
            json={"email": "newseller@example.com", "password": "seller-secure-password"},
        )
        assert login_resp.status_code == 200
        assert login_resp.json()["user"]["email"] == "newseller@example.com"

    async def test_signup_duplicate_email_conflict(self, client):
        payload = {
            "email": "duplicate@example.com",
            "password": "valid-password-123",
            "full_name": "First User",
            "role": "buyer",
        }
        res1 = await client.post("/auth/signup", json=payload)
        assert res1.status_code == 201

        # Attempt to sign up with the exact same email
        res2 = await client.post("/auth/signup", json=payload)
        assert res2.status_code == 409
        body = res2.json()
        assert body["error"]["code"] == "conflict"
        assert "already exists" in body["error"]["message"]

        # Attempt with different case
        res3 = await client.post(
            "/auth/signup",
            json={**payload, "email": "DUPLICATE@EXAMPLE.COM", "full_name": "Other User"},
        )
        assert res3.status_code == 409

    async def test_signup_reviewer_role_rejected(self, client):
        payload = {
            "email": "sneaky-reviewer@example.com",
            "password": "password-12345",
            "full_name": "Fake Reviewer",
            "role": "reviewer",
        }
        response = await client.post("/auth/signup", json=payload)
        assert response.status_code == 422

    async def test_signup_short_password_rejected(self, client):
        payload = {
            "email": "shortpw@example.com",
            "password": "short",
            "full_name": "Short Password",
            "role": "buyer",
        }
        response = await client.post("/auth/signup", json=payload)
        assert response.status_code == 422

    async def test_signup_invalid_email_rejected(self, client):
        payload = {
            "email": "not-an-email",
            "password": "valid-password-123",
            "full_name": "Bad Email",
            "role": "buyer",
        }
        response = await client.post("/auth/signup", json=payload)
        assert response.status_code == 422
