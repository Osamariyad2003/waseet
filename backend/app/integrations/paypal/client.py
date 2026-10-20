"""PayPal REST client (sandbox). Orders v2, Payouts, Payments v2 refunds,
webhook signature verification.

Rules this module holds to:
  * credentials come from settings (environment) and are never logged;
  * every call has a timeout and raises `PayPalError` on failure;
  * logs carry status codes and PayPal ids, never tokens or full payloads;
  * money-moving calls carry an idempotency key.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

import httpx
import structlog

from app.config import Settings
from app.domain.entities import Money
from app.domain.errors import PayPalError
from app.integrations.paypal.interface import (
    AccessToken,
    CaptureResult,
    OrderResult,
    PayoutResult,
    RefundResult,
    WebhookHeaders,
)

logger = structlog.get_logger(__name__)

# Refresh a little early so a token never expires mid-request.
TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS = 60


class PayPalClient:
    """Implements `PayPalGateway` against the PayPal REST API."""

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._base_url = settings.paypal_base_url.rstrip("/")
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(settings.paypal_timeout_seconds),
        )
        self._token: AccessToken | None = None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http.aclose()

    # --- auth -------------------------------------------------------------

    async def get_access_token(self) -> AccessToken:
        if self._token and self._token.expires_at_epoch > time.time():
            return self._token

        if not self._settings.paypal_configured:
            raise PayPalError(
                "PayPal credentials are not configured; set PAYPAL_CLIENT_ID and "
                "PAYPAL_CLIENT_SECRET in the environment"
            )

        try:
            response = await self._http.post(
                "/v1/oauth2/token",
                auth=(
                    self._settings.paypal_client_id,
                    self._settings.paypal_client_secret.get_secret_value(),
                ),
                data={"grant_type": "client_credentials"},
                headers={"Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise PayPalError(f"could not reach PayPal for an access token: {exc!s}") from exc

        if response.status_code != httpx.codes.OK:
            # Deliberately does not echo the body — it can contain the client id.
            raise PayPalError(f"PayPal rejected the credentials (HTTP {response.status_code})")

        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise PayPalError("PayPal returned no access token")

        expires_in = float(payload.get("expires_in", 0) or 0)
        self._token = AccessToken(
            token=token,
            expires_at_epoch=time.time() + max(expires_in - TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS, 0),
            scope=payload.get("scope", ""),
        )
        logger.info("paypal.token_acquired", expires_in=int(expires_in))
        return self._token

    async def get_client_token(self) -> str:
        """Browser-safe token for the JS SDK v6.

        Same token endpoint, `response_type=client_token`. Deliberately not
        cached: it is short-lived by design, and the whole point is that the
        browser gets something disposable instead of a credential.
        """
        if not self._settings.paypal_configured:
            raise PayPalError(
                "PayPal credentials are not configured; set PAYPAL_CLIENT_ID and "
                "PAYPAL_CLIENT_SECRET in the environment"
            )
        try:
            response = await self._http.post(
                "/v1/oauth2/token",
                auth=(
                    self._settings.paypal_client_id,
                    self._settings.paypal_client_secret.get_secret_value(),
                ),
                data={"grant_type": "client_credentials", "response_type": "client_token"},
                headers={"Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise PayPalError(f"could not reach PayPal for a client token: {exc!s}") from exc

        if response.status_code != httpx.codes.OK:
            raise PayPalError(
                f"PayPal would not issue a client token (HTTP {response.status_code})"
            )

        token = response.json().get("access_token")
        if not token:
            raise PayPalError("PayPal returned no client token")
        logger.info("paypal.client_token_issued")
        return token

    # --- orders -----------------------------------------------------------

    async def create_order(
        self,
        *,
        amount: Decimal,
        currency: str,
        reference_id: str,
        description: str,
        request_id: str,
    ) -> OrderResult:
        money = Money(amount, currency)
        body = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": reference_id,
                    "custom_id": reference_id,
                    "description": description[:127],
                    "amount": {"currency_code": currency, "value": money.paypal_value},
                }
            ],
        }
        payload = await self._request(
            "POST",
            "/v2/checkout/orders",
            json=body,
            request_id=request_id,
            what="create order",
        )

        order_id = payload.get("id")
        if not order_id:
            raise PayPalError("PayPal returned an order without an id")

        approve_url = next(
            (
                link.get("href")
                for link in payload.get("links", [])
                if link.get("rel") in {"approve", "payer-action"}
            ),
            None,
        )
        logger.info(
            "paypal.order_created",
            paypal_order_id=order_id,
            deal_reference=reference_id,
            status=payload.get("status"),
        )
        return OrderResult(
            order_id=order_id, status=payload.get("status", "CREATED"), approve_url=approve_url
        )

    async def capture_order(self, *, order_id: str, request_id: str) -> CaptureResult:
        payload = await self._request(
            "POST",
            f"/v2/checkout/orders/{order_id}/capture",
            json={},
            request_id=request_id,
            what="capture order",
        )
        return self._parse_capture(order_id, payload)

    @staticmethod
    def _parse_capture(order_id: str, payload: dict[str, Any]) -> CaptureResult:
        try:
            capture = payload["purchase_units"][0]["payments"]["captures"][0]
            amount = capture["amount"]
        except (KeyError, IndexError, TypeError) as exc:
            raise PayPalError("PayPal capture response did not contain a capture") from exc

        capture_id = capture.get("id")
        if not capture_id:
            raise PayPalError("PayPal capture response did not contain a capture id")

        logger.info(
            "paypal.order_captured",
            paypal_order_id=order_id,
            paypal_capture_id=capture_id,
            status=capture.get("status"),
        )
        return CaptureResult(
            order_id=order_id,
            capture_id=capture_id,
            status=capture.get("status", payload.get("status", "")),
            amount=Decimal(str(amount["value"])),
            currency=amount["currency_code"],
        )

    # --- payouts ----------------------------------------------------------

    async def create_payout(
        self,
        *,
        receiver_email: str,
        amount: Decimal,
        currency: str,
        sender_batch_id: str,
        note: str,
    ) -> PayoutResult:
        money = Money(amount, currency)
        body = {
            "sender_batch_header": {
                # Derived from the deal id. PayPal rejects a duplicate batch
                # id, which is what makes release idempotent at the rail.
                "sender_batch_id": sender_batch_id,
                "email_subject": "Waseet escrow release",
                "email_message": note[:1000],
            },
            "items": [
                {
                    "recipient_type": "EMAIL",
                    "receiver": receiver_email,
                    "amount": {"currency": currency, "value": money.paypal_value},
                    "note": note[:1000],
                    "sender_item_id": sender_batch_id,
                }
            ],
        }
        payload = await self._request(
            "POST", "/v1/payments/payouts", json=body, what="create payout"
        )

        header = payload.get("batch_header") or {}
        batch_id = header.get("payout_batch_id")
        if not batch_id:
            raise PayPalError("PayPal returned a payout without a batch id")

        logger.info(
            "paypal.payout_created",
            payout_batch_id=batch_id,
            batch_status=header.get("batch_status"),
            sender_batch_id=sender_batch_id,
        )
        return PayoutResult(
            payout_batch_id=batch_id,
            batch_status=header.get("batch_status", ""),
            sender_batch_id=sender_batch_id,
        )

    # --- refunds ----------------------------------------------------------

    async def refund_capture(
        self,
        *,
        capture_id: str,
        amount: Decimal,
        currency: str,
        request_id: str,
        note: str,
    ) -> RefundResult:
        money = Money(amount, currency)
        body = {
            "amount": {"value": money.paypal_value, "currency_code": currency},
            "note_to_payer": note[:255],
        }
        payload = await self._request(
            "POST",
            f"/v2/payments/captures/{capture_id}/refund",
            json=body,
            request_id=request_id,
            what="refund capture",
        )

        refund_id = payload.get("id")
        if not refund_id:
            raise PayPalError("PayPal returned a refund without an id")

        refunded = payload.get("amount") or {}
        logger.info(
            "paypal.refund_created",
            refund_id=refund_id,
            paypal_capture_id=capture_id,
            status=payload.get("status"),
        )
        return RefundResult(
            refund_id=refund_id,
            status=payload.get("status", ""),
            amount=Decimal(str(refunded.get("value", money.paypal_value))),
            currency=refunded.get("currency_code", currency),
        )

    # --- webhooks ---------------------------------------------------------

    async def verify_webhook(
        self, *, headers: WebhookHeaders, event_body: dict[str, Any], webhook_id: str
    ) -> bool:
        if not webhook_id:
            logger.warning("paypal.webhook_unverifiable", reason="PAYPAL_WEBHOOK_ID is not set")
            return False

        body = {
            "auth_algo": headers.auth_algo,
            "cert_url": headers.cert_url,
            "transmission_id": headers.transmission_id,
            "transmission_sig": headers.transmission_sig,
            "transmission_time": headers.transmission_time,
            "webhook_id": webhook_id,
            "webhook_event": event_body,
        }
        try:
            payload = await self._request(
                "POST",
                "/v1/notifications/verify-webhook-signature",
                json=body,
                what="verify webhook signature",
            )
        except PayPalError as exc:
            # A verification that cannot be completed is a verification that
            # failed. Never act on an unverified event.
            logger.warning("paypal.webhook_verification_error", error=str(exc))
            return False

        verified = payload.get("verification_status") == "SUCCESS"
        logger.info(
            "paypal.webhook_verified",
            verified=verified,
            transmission_id=headers.transmission_id,
        )
        return verified

    # --- plumbing ---------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any],
        what: str,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        token = await self.get_access_token()
        request_headers = {
            "Authorization": f"Bearer {token.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if request_id:
            request_headers["PayPal-Request-Id"] = request_id

        try:
            response = await self._http.request(method, path, json=json, headers=request_headers)
        except httpx.HTTPError as exc:
            raise PayPalError(f"could not reach PayPal to {what}: {exc!s}") from exc

        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise PayPalError(self._describe_failure(what, response))

        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise PayPalError(f"PayPal returned a non-JSON response to {what}") from exc

    @staticmethod
    def _describe_failure(what: str, response: httpx.Response) -> str:
        """A message safe to surface: PayPal's own error name and debug id,
        never the full payload."""
        name = debug_id = ""
        detail = ""
        try:
            body = response.json()
            name = body.get("name") or body.get("error") or ""
            debug_id = body.get("debug_id") or ""
            issues = body.get("details") or []
            if issues and isinstance(issues, list):
                detail = str(issues[0].get("issue") or issues[0].get("description") or "")
        except ValueError:
            pass

        parts = [f"PayPal could not {what} (HTTP {response.status_code}"]
        if name:
            parts.append(f", {name}")
        if detail:
            parts.append(f": {detail}")
        parts.append(")")
        if debug_id:
            parts.append(f" [debug_id={debug_id}]")
        return "".join(parts)
