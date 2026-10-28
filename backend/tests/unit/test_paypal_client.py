"""PayPal client: request shapes, response parsing, and failure handling.

Driven through httpx's MockTransport, so the real request-building and
response-parsing code runs — only the socket is replaced.
"""

from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest

from app.config import Settings
from app.domain.errors import PayPalError
from app.integrations.paypal.client import PayPalClient
from app.integrations.paypal.interface import PayPalGateway, WebhookHeaders

TOKEN_RESPONSE = {"access_token": "A21AA-fake-token", "expires_in": 32400, "scope": "orders"}


def make_settings(**overrides) -> Settings:
    base = {
        "paypal_client_id": "test-client-id",
        "paypal_client_secret": "test-client-secret",
        "paypal_base_url": "https://api-m.sandbox.paypal.com",
        "paypal_webhook_id": "WH-TEST-1",
        "database_url": "sqlite+aiosqlite:///:memory:",
    }
    return Settings(**{**base, **overrides})


class Recorder:
    """Captures requests and returns scripted responses."""

    def __init__(self, routes: dict[str, tuple[int, dict]]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        for path, (status, body) in self.routes.items():
            if request.url.path.endswith(path) or path in request.url.path:
                return httpx.Response(status, json=body)
        return httpx.Response(404, json={"name": "RESOURCE_NOT_FOUND"})

    def request_to(self, fragment: str) -> httpx.Request:
        for request in self.requests:
            if fragment in request.url.path:
                return request
        raise AssertionError(f"no request was made to {fragment}")

    def body_of(self, fragment: str) -> dict:
        return json.loads(self.request_to(fragment).content)


def client_for(recorder: Recorder, **settings_overrides) -> PayPalClient:
    settings = make_settings(**settings_overrides)
    http = httpx.AsyncClient(
        base_url=settings.paypal_base_url, transport=httpx.MockTransport(recorder.handler)
    )
    return PayPalClient(settings, http_client=http)


def test_the_client_satisfies_the_gateway_protocol():
    """Services depend on the Protocol; this is what keeps them swappable."""
    assert isinstance(client_for(Recorder({})), PayPalGateway)


class TestAccessToken:
    async def test_token_is_fetched_with_basic_auth_and_client_credentials(self):
        recorder = Recorder({"/v1/oauth2/token": (200, TOKEN_RESPONSE)})
        token = await client_for(recorder).get_access_token()

        assert token.token == "A21AA-fake-token"
        request = recorder.request_to("/v1/oauth2/token")
        assert request.headers["authorization"].startswith("Basic ")
        assert b"grant_type=client_credentials" in request.content

    async def test_token_is_cached_across_calls(self):
        recorder = Recorder({"/v1/oauth2/token": (200, TOKEN_RESPONSE)})
        client = client_for(recorder)
        await client.get_access_token()
        await client.get_access_token()
        assert len(recorder.requests) == 1

    async def test_the_cached_token_expires_early(self):
        """A 60s safety margin, so a token never expires mid-request."""
        recorder = Recorder({"/v1/oauth2/token": (200, {**TOKEN_RESPONSE, "expires_in": 30})})
        client = client_for(recorder)
        token = await client.get_access_token()
        # expires_in is below the margin, so the token is already stale.
        await client.get_access_token()
        assert len(recorder.requests) == 2
        assert token.token not in repr(token)

    async def test_a_token_never_appears_in_its_own_repr(self):
        """Tokens must not reach a log line via an accidental repr()."""
        recorder = Recorder({"/v1/oauth2/token": (200, TOKEN_RESPONSE)})
        token = await client_for(recorder).get_access_token()
        assert "A21AA-fake-token" not in repr(token)

    async def test_rejected_credentials_raise_without_echoing_the_body(self):
        recorder = Recorder(
            {"/v1/oauth2/token": (401, {"error": "invalid_client", "client_id": "leaky"})}
        )
        with pytest.raises(PayPalError) as exc:
            await client_for(recorder).get_access_token()
        assert "HTTP 401" in str(exc.value)
        assert "leaky" not in str(exc.value)

    async def test_missing_credentials_raise_before_any_network_call(self):
        recorder = Recorder({})
        client = client_for(recorder, paypal_client_id="", paypal_client_secret="")
        with pytest.raises(PayPalError, match="not configured"):
            await client.get_access_token()
        assert recorder.requests == []

    async def test_a_network_error_becomes_a_typed_paypal_error(self):
        def boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        settings = make_settings()
        http = httpx.AsyncClient(
            base_url=settings.paypal_base_url, transport=httpx.MockTransport(boom)
        )
        with pytest.raises(PayPalError, match="could not reach PayPal"):
            await PayPalClient(settings, http_client=http).get_access_token()


ORDER_OK = {"id": "ORDER-1", "status": "CREATED", "links": []}

PAYOUT_STATUS_BODY = {
    "batch_header": {
        "payout_batch_id": "BATCH-9",
        "batch_status": "SUCCESS",
        "time_created": "2026-01-01T00:00:00Z",
        "amount": {"value": "243.75", "currency": "USD"},
    },
    "items": [
        {
            "transaction_id": "TX-1",
            "transaction_status": "SUCCESS",
            "payout_item": {
                "amount": {"value": "243.75", "currency": "USD"},
                "receiver": "seller@sandbox.example.com",
            },
        }
    ],
}


class TestPayoutStatus:
    async def test_payout_status_is_read_and_parsed(self):
        recorder = Recorder(
            {
                "/v1/oauth2/token": (200, TOKEN_RESPONSE),
                "/v1/payments/payouts/BATCH-9": (200, PAYOUT_STATUS_BODY),
            }
        )
        status = await client_for(recorder).get_payout_status(payout_batch_id="BATCH-9")
        assert status.batch_status == "SUCCESS"
        assert status.amount == Decimal("243.75")
        assert status.currency == "USD"
        assert len(status.items) == 1
        assert status.items[0].transaction_status == "SUCCESS"
        assert status.items[0].receiver == "seller@sandbox.example.com"
        # A GET carries no request body.
        request = recorder.request_to("/v1/payments/payouts/BATCH-9")
        assert request.method == "GET"
        assert request.content == b""

    async def test_an_unknown_batch_raises_a_typed_error(self):
        recorder = Recorder({"/v1/oauth2/token": (200, TOKEN_RESPONSE)})
        with pytest.raises(PayPalError, match="read the payout status"):
            await client_for(recorder).get_payout_status(payout_batch_id="NOPE")


class TestReferenceStatus:
    async def test_order_status_is_read(self):
        recorder = Recorder(
            {
                "/v1/oauth2/token": (200, TOKEN_RESPONSE),
                "/v2/checkout/orders/ORDER-7": (
                    200,
                    {
                        "id": "ORDER-7",
                        "status": "COMPLETED",
                        "purchase_units": [{"amount": {"value": "250.00", "currency_code": "USD"}}],
                    },
                ),
            }
        )
        status = await client_for(recorder).get_order_status(order_id="ORDER-7")
        assert status.status == "COMPLETED"
        assert status.amount == Decimal("250.00")
        assert recorder.request_to("/v2/checkout/orders/ORDER-7").method == "GET"

    async def test_capture_status_is_read(self):
        recorder = Recorder(
            {
                "/v1/oauth2/token": (200, TOKEN_RESPONSE),
                "/v2/payments/captures/CAP-3": (
                    200,
                    {"id": "CAP-3", "status": "COMPLETED", "amount": {"value": "250.00", "currency_code": "USD"}},
                ),
            }
        )
        status = await client_for(recorder).get_capture_status(capture_id="CAP-3")
        assert status.status == "COMPLETED"
        assert status.amount == Decimal("250.00")
        assert status.currency == "USD"

    async def test_refund_status_is_read(self):
        recorder = Recorder(
            {
                "/v1/oauth2/token": (200, TOKEN_RESPONSE),
                "/v2/payments/refunds/REF-5": (
                    200,
                    {"id": "REF-5", "status": "COMPLETED", "amount": {"value": "100.00", "currency_code": "USD"}},
                ),
            }
        )
        status = await client_for(recorder).get_refund_status(refund_id="REF-5")
        assert status.reference_id == "REF-5"
        assert status.amount == Decimal("100.00")


class TestSuppliedToken:
    """PAYPAL_SANDBOX_ACCESS_TOKEN — the token the PayPal AI Toolkit mints —
    used directly instead of the client's own OAuth exchange."""

    async def test_a_supplied_token_is_used_without_an_oauth_exchange(self):
        # No token route is registered, so any OAuth call would 404; it must
        # not happen at all.
        recorder = Recorder({})
        client = client_for(recorder, paypal_sandbox_access_token="SUPPLIED-123")
        token = await client.get_access_token()
        assert token.token == "SUPPLIED-123"
        assert recorder.requests == []

    async def test_a_supplied_token_authorizes_a_rest_call(self):
        recorder = Recorder({"/v2/checkout/orders": (201, ORDER_OK)})
        client = client_for(recorder, paypal_sandbox_access_token="SUPPLIED-123")
        await client.create_order(
            amount=Decimal("10.00"),
            currency="USD",
            reference_id="d1",
            description="x",
            request_id="r1",
        )
        request = recorder.request_to("/v2/checkout/orders")
        assert request.headers["authorization"] == "Bearer SUPPLIED-123"
        with pytest.raises(AssertionError):
            recorder.request_to("/v1/oauth2/token")

    async def test_a_supplied_token_works_without_client_credentials(self):
        recorder = Recorder({})
        client = client_for(
            recorder,
            paypal_client_id="",
            paypal_client_secret="",
            paypal_sandbox_access_token="SUPPLIED",
        )
        token = await client.get_access_token()
        assert token.token == "SUPPLIED"
        assert recorder.requests == []

    async def test_a_rejected_supplied_token_falls_back_to_minting_one(self):
        """A lapsed supplied token 401s; the client mints one from the client
        id/secret and retries, and the retry carries the minted token."""
        requests: list[httpx.Request] = []
        orders_seen = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            path = request.url.path
            if path.endswith("/v1/oauth2/token"):
                return httpx.Response(200, json=TOKEN_RESPONSE)
            if path.endswith("/v2/checkout/orders"):
                orders_seen["n"] += 1
                if orders_seen["n"] == 1:
                    return httpx.Response(401, json={"name": "AUTHENTICATION_FAILURE"})
                return httpx.Response(201, json=ORDER_OK)
            return httpx.Response(404, json={})

        settings = make_settings(paypal_sandbox_access_token="LAPSED")
        http = httpx.AsyncClient(
            base_url=settings.paypal_base_url, transport=httpx.MockTransport(handler)
        )
        client = PayPalClient(settings, http_client=http)
        result = await client.create_order(
            amount=Decimal("10.00"),
            currency="USD",
            reference_id="d",
            description="x",
            request_id="r",
        )
        assert result.order_id == "ORDER-1"
        # It minted an OAuth token for the retry.
        assert any(r.url.path.endswith("/v1/oauth2/token") for r in requests)
        # The retry used the minted token, not the lapsed supplied one.
        order_reqs = [r for r in requests if r.url.path.endswith("/v2/checkout/orders")]
        assert order_reqs[0].headers["authorization"] == "Bearer LAPSED"
        assert order_reqs[-1].headers["authorization"] == "Bearer A21AA-fake-token"


class TestCreateOrder:
    async def test_order_request_has_capture_intent_and_exact_money(self):
        recorder = Recorder(
            {
                "/v1/oauth2/token": (200, TOKEN_RESPONSE),
                "/v2/checkout/orders": (
                    201,
                    {
                        "id": "5O190127TN364715T",
                        "status": "CREATED",
                        "links": [
                            {"rel": "approve", "href": "https://sandbox.paypal.com/approve/1"}
                        ],
                    },
                ),
            }
        )
        result = await client_for(recorder).create_order(
            amount=Decimal("250.5"),
            currency="USD",
            reference_id="deal-abc",
            description="Logo design",
            request_id="waseet-order-deal-abc",
        )

        assert result.order_id == "5O190127TN364715T"
        assert result.approve_url == "https://sandbox.paypal.com/approve/1"

        body = recorder.body_of("/v2/checkout/orders")
        assert body["intent"] == "CAPTURE"
        unit = body["purchase_units"][0]
        assert unit["amount"] == {"currency_code": "USD", "value": "250.50"}
        assert unit["custom_id"] == "deal-abc"

    async def test_create_order_sends_an_idempotency_key(self):
        recorder = Recorder(
            {
                "/v1/oauth2/token": (200, TOKEN_RESPONSE),
                "/v2/checkout/orders": (201, {"id": "ORDER-1", "status": "CREATED"}),
            }
        )
        await client_for(recorder).create_order(
            amount=Decimal("10"),
            currency="USD",
            reference_id="deal-1",
            description="x",
            request_id="waseet-order-deal-1",
        )
        request = recorder.request_to("/v2/checkout/orders")
        assert request.headers["paypal-request-id"] == "waseet-order-deal-1"
        assert request.headers["authorization"] == "Bearer A21AA-fake-token"

    async def test_an_order_without_an_id_is_rejected(self):
        recorder = Recorder(
            {
                "/v1/oauth2/token": (200, TOKEN_RESPONSE),
                "/v2/checkout/orders": (201, {"status": "CREATED"}),
            }
        )
        with pytest.raises(PayPalError, match="without an id"):
            await client_for(recorder).create_order(
                amount=Decimal("10"),
                currency="USD",
                reference_id="d",
                description="x",
                request_id="r",
            )

    async def test_a_paypal_error_surfaces_its_name_and_debug_id(self):
        recorder = Recorder(
            {
                "/v1/oauth2/token": (200, TOKEN_RESPONSE),
                "/v2/checkout/orders": (
                    422,
                    {
                        "name": "UNPROCESSABLE_ENTITY",
                        "debug_id": "abc123",
                        "details": [{"issue": "CURRENCY_NOT_SUPPORTED"}],
                    },
                ),
            }
        )
        with pytest.raises(PayPalError) as exc:
            await client_for(recorder).create_order(
                amount=Decimal("10"),
                currency="XXX",
                reference_id="d",
                description="x",
                request_id="r",
            )
        message = str(exc.value)
        assert "UNPROCESSABLE_ENTITY" in message
        assert "CURRENCY_NOT_SUPPORTED" in message
        assert "abc123" in message


class TestCaptureOrder:
    CAPTURE_OK = {
        "id": "5O190127TN364715T",
        "status": "COMPLETED",
        "purchase_units": [
            {
                "payments": {
                    "captures": [
                        {
                            "id": "3C679366HH908993F",
                            "status": "COMPLETED",
                            "amount": {"currency_code": "USD", "value": "250.50"},
                        }
                    ]
                }
            }
        ],
    }

    async def test_capture_extracts_the_capture_id_and_amount(self):
        recorder = Recorder(
            {
                "/v1/oauth2/token": (200, TOKEN_RESPONSE),
                "/capture": (201, self.CAPTURE_OK),
            }
        )
        result = await client_for(recorder).capture_order(
            order_id="5O190127TN364715T", request_id="waseet-capture-deal-1"
        )

        assert result.capture_id == "3C679366HH908993F"
        assert result.amount == Decimal("250.50")
        assert result.currency == "USD"
        assert result.is_completed

    async def test_a_capture_amount_is_parsed_as_decimal_not_float(self):
        """Money is never a float — 0.1 + 0.2 problems do not belong here."""
        recorder = Recorder(
            {"/v1/oauth2/token": (200, TOKEN_RESPONSE), "/capture": (201, self.CAPTURE_OK)}
        )
        result = await client_for(recorder).capture_order(order_id="O", request_id="r")
        assert isinstance(result.amount, Decimal)

    async def test_a_declined_capture_is_reported_not_treated_as_completed(self):
        declined = {
            "purchase_units": [
                {
                    "payments": {
                        "captures": [
                            {
                                "id": "CAP-1",
                                "status": "DECLINED",
                                "amount": {"currency_code": "USD", "value": "10.00"},
                            }
                        ]
                    }
                }
            ]
        }
        recorder = Recorder(
            {"/v1/oauth2/token": (200, TOKEN_RESPONSE), "/capture": (201, declined)}
        )
        result = await client_for(recorder).capture_order(order_id="O", request_id="r")
        assert not result.is_completed

    async def test_a_capture_response_with_no_capture_is_rejected(self):
        recorder = Recorder(
            {
                "/v1/oauth2/token": (200, TOKEN_RESPONSE),
                "/capture": (201, {"status": "COMPLETED", "purchase_units": []}),
            }
        )
        with pytest.raises(PayPalError, match="did not contain a capture"):
            await client_for(recorder).capture_order(order_id="O", request_id="r")


class TestPayout:
    async def test_payout_is_keyed_on_a_deterministic_sender_batch_id(self):
        """This is what makes release idempotent at the rail: PayPal itself
        rejects a second batch with the same sender_batch_id."""
        recorder = Recorder(
            {
                "/v1/oauth2/token": (200, TOKEN_RESPONSE),
                "/v1/payments/payouts": (
                    201,
                    {
                        "batch_header": {
                            "payout_batch_id": "5UXD7PNLB8S3E",
                            "batch_status": "PENDING",
                        }
                    },
                ),
            }
        )
        result = await client_for(recorder).create_payout(
            receiver_email="seller@sandbox.test",
            amount=Decimal("97.5"),
            currency="USD",
            sender_batch_id="waseet-release-deal-abc",
            note="Escrow release",
        )

        assert result.payout_batch_id == "5UXD7PNLB8S3E"
        assert result.sender_batch_id == "waseet-release-deal-abc"
        assert result.is_accepted

        body = recorder.body_of("/v1/payments/payouts")
        assert body["sender_batch_header"]["sender_batch_id"] == "waseet-release-deal-abc"
        item = body["items"][0]
        assert item["recipient_type"] == "EMAIL"
        assert item["receiver"] == "seller@sandbox.test"
        assert item["amount"] == {"currency": "USD", "value": "97.50"}

    async def test_a_payout_without_a_batch_id_is_rejected(self):
        recorder = Recorder(
            {
                "/v1/oauth2/token": (200, TOKEN_RESPONSE),
                "/v1/payments/payouts": (201, {"batch_header": {}}),
            }
        )
        with pytest.raises(PayPalError, match="without a batch id"):
            await client_for(recorder).create_payout(
                receiver_email="s@t.test",
                amount=Decimal("1"),
                currency="USD",
                sender_batch_id="b",
                note="n",
            )

    async def test_a_duplicate_batch_id_rejected_by_paypal_surfaces_as_an_error(self):
        recorder = Recorder(
            {
                "/v1/oauth2/token": (200, TOKEN_RESPONSE),
                "/v1/payments/payouts": (
                    400,
                    {"name": "BATCH_ID_ALREADY_EXISTS", "debug_id": "dup-1"},
                ),
            }
        )
        with pytest.raises(PayPalError, match="BATCH_ID_ALREADY_EXISTS"):
            await client_for(recorder).create_payout(
                receiver_email="s@t.test",
                amount=Decimal("1"),
                currency="USD",
                sender_batch_id="waseet-release-deal-abc",
                note="n",
            )


class TestRefund:
    async def test_refund_posts_the_amount_against_the_capture(self):
        recorder = Recorder(
            {
                "/v1/oauth2/token": (200, TOKEN_RESPONSE),
                "/refund": (
                    201,
                    {
                        "id": "1JU08902781691324",
                        "status": "COMPLETED",
                        "amount": {"currency_code": "USD", "value": "250.50"},
                    },
                ),
            }
        )
        result = await client_for(recorder).refund_capture(
            capture_id="3C679366HH908993F",
            amount=Decimal("250.5"),
            currency="USD",
            request_id="waseet-refund-deal-abc",
            note="Dispute resolved in the buyer's favour",
        )

        assert result.refund_id == "1JU08902781691324"
        assert result.amount == Decimal("250.50")
        assert result.is_completed

        request = recorder.request_to("/refund")
        assert "3C679366HH908993F" in str(request.url)
        assert request.headers["paypal-request-id"] == "waseet-refund-deal-abc"
        assert json.loads(request.content)["amount"] == {
            "value": "250.50",
            "currency_code": "USD",
        }

    async def test_a_partial_refund_sends_only_the_partial_amount(self):
        """The split path refunds the remainder, not the whole capture."""
        recorder = Recorder(
            {
                "/v1/oauth2/token": (200, TOKEN_RESPONSE),
                "/refund": (
                    201,
                    {
                        "id": "REFUND-1",
                        "status": "COMPLETED",
                        "amount": {"currency_code": "USD", "value": "80.00"},
                    },
                ),
            }
        )
        result = await client_for(recorder).refund_capture(
            capture_id="CAP-1",
            amount=Decimal("80"),
            currency="USD",
            request_id="r",
            note="partial",
        )
        assert result.amount == Decimal("80.00")
        assert json.loads(recorder.request_to("/refund").content)["amount"]["value"] == "80.00"


class TestWebhookVerification:
    EVENT = {"id": "WH-1", "event_type": "PAYMENT.CAPTURE.COMPLETED"}
    HEADERS = WebhookHeaders(
        transmission_id="t-1",
        transmission_time="2026-10-20T10:00:00Z",
        transmission_sig="sig",
        cert_url="https://api.sandbox.paypal.com/cert.pem",
        auth_algo="SHA256withRSA",
    )

    async def test_a_genuine_signature_verifies(self):
        recorder = Recorder(
            {
                "/v1/oauth2/token": (200, TOKEN_RESPONSE),
                "/verify-webhook-signature": (200, {"verification_status": "SUCCESS"}),
            }
        )
        assert await client_for(recorder).verify_webhook(
            headers=self.HEADERS, event_body=self.EVENT, webhook_id="WH-TEST-1"
        )
        body = recorder.body_of("/verify-webhook-signature")
        assert body["webhook_id"] == "WH-TEST-1"
        assert body["transmission_sig"] == "sig"
        assert body["webhook_event"] == self.EVENT

    async def test_a_forged_signature_does_not_verify(self):
        recorder = Recorder(
            {
                "/v1/oauth2/token": (200, TOKEN_RESPONSE),
                "/verify-webhook-signature": (200, {"verification_status": "FAILURE"}),
            }
        )
        assert not await client_for(recorder).verify_webhook(
            headers=self.HEADERS, event_body=self.EVENT, webhook_id="WH-TEST-1"
        )

    async def test_verification_that_cannot_be_completed_fails_closed(self):
        """An error talking to PayPal must never read as a pass."""
        recorder = Recorder(
            {
                "/v1/oauth2/token": (200, TOKEN_RESPONSE),
                "/verify-webhook-signature": (500, {"name": "INTERNAL_SERVER_ERROR"}),
            }
        )
        assert not await client_for(recorder).verify_webhook(
            headers=self.HEADERS, event_body=self.EVENT, webhook_id="WH-TEST-1"
        )

    async def test_a_missing_webhook_id_fails_closed_without_a_call(self):
        recorder = Recorder({"/v1/oauth2/token": (200, TOKEN_RESPONSE)})
        assert not await client_for(recorder).verify_webhook(
            headers=self.HEADERS, event_body=self.EVENT, webhook_id=""
        )
        assert recorder.requests == []


class TestWebhookHeaders:
    def test_headers_are_read_from_a_request_mapping(self):
        headers = WebhookHeaders.from_mapping(
            {
                "paypal-transmission-id": "t-1",
                "paypal-transmission-time": "2026-10-20T10:00:00Z",
                "paypal-transmission-sig": "sig",
                "paypal-cert-url": "https://api.sandbox.paypal.com/cert.pem",
                "paypal-auth-algo": "SHA256withRSA",
            }
        )
        assert headers is not None
        assert headers.transmission_id == "t-1"

    @pytest.mark.parametrize(
        "missing",
        [
            "paypal-transmission-id",
            "paypal-transmission-time",
            "paypal-transmission-sig",
            "paypal-cert-url",
            "paypal-auth-algo",
        ],
    )
    def test_any_missing_header_means_no_headers(self, missing):
        """A missing signature header is a failed verification, not a pass."""
        complete = {
            "paypal-transmission-id": "t-1",
            "paypal-transmission-time": "2026-10-20T10:00:00Z",
            "paypal-transmission-sig": "sig",
            "paypal-cert-url": "https://api.sandbox.paypal.com/cert.pem",
            "paypal-auth-algo": "SHA256withRSA",
        }
        del complete[missing]
        assert WebhookHeaders.from_mapping(complete) is None

    def test_blank_headers_are_treated_as_missing(self):
        assert (
            WebhookHeaders.from_mapping(
                {
                    "paypal-transmission-id": "   ",
                    "paypal-transmission-time": "t",
                    "paypal-transmission-sig": "s",
                    "paypal-cert-url": "c",
                    "paypal-auth-algo": "a",
                }
            )
            is None
        )
