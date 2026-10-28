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
    PayoutItemStatus,
    PayoutResult,
    PayoutStatus,
    ReferenceStatus,
    RefundResult,
    WebhookHeaders,
)

logger = structlog.get_logger(__name__)

# Refresh a little early so a token never expires mid-request.
TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS = 60
# A supplied token carries no expiry, so assume a conservative life (PayPal
# sandbox tokens last ~9h). A 401 falls back to a freshly minted token anyway.
SUPPLIED_TOKEN_ASSUMED_TTL_SECONDS = 8 * 3600


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
        self._token_source: str | None = None
        # Set once a supplied token is rejected (401), so we stop reaching for
        # it and mint our own from here on.
        self._supplied_token_rejected = False

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http.aclose()

    # --- auth -------------------------------------------------------------

    async def get_access_token(self, *, force_refresh: bool = False) -> AccessToken:
        if force_refresh and self._token_source == "supplied":
            # The token handed to us (PAYPAL_SANDBOX_ACCESS_TOKEN) was
            # rejected. Drop it for good and fall through to a minted one.
            self._supplied_token_rejected = True
            self._token = None

        if not force_refresh and self._token and self._token.expires_at_epoch > time.time():
            return self._token

        supplied = self._settings.paypal_sandbox_access_token.get_secret_value()
        if supplied and not self._supplied_token_rejected:
            self._token = AccessToken(
                token=supplied,
                expires_at_epoch=time.time() + SUPPLIED_TOKEN_ASSUMED_TTL_SECONDS,
                scope="(supplied)",
            )
            self._token_source = "supplied"
            logger.info("paypal.token_supplied")
            return self._token

        if not self._settings.paypal_configured:
            raise PayPalError(
                "PayPal credentials are not configured; set PAYPAL_CLIENT_ID and "
                "PAYPAL_CLIENT_SECRET (or PAYPAL_SANDBOX_ACCESS_TOKEN) in the environment"
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
        self._token_source = "oauth"
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

    async def get_payout_status(self, *, payout_batch_id: str) -> PayoutStatus:
        payload = await self._request(
            "GET",
            f"/v1/payments/payouts/{payout_batch_id}",
            what="read the payout status",
        )
        header = payload.get("batch_header") or {}
        amount_obj = header.get("amount") or {}
        amount = amount_obj.get("value")
        items: list[PayoutItemStatus] = []
        for raw in payload.get("items") or []:
            detail = raw.get("payout_item") or {}
            item_amount = detail.get("amount") or {}
            items.append(
                PayoutItemStatus(
                    transaction_id=raw.get("transaction_id"),
                    transaction_status=str(raw.get("transaction_status", "")),
                    amount=Decimal(str(item_amount.get("value", "0") or "0")),
                    currency=str(item_amount.get("currency", "") or ""),
                    receiver=str(detail.get("receiver", "") or ""),
                )
            )
        logger.info(
            "paypal.payout_status_read",
            payout_batch_id=payout_batch_id,
            batch_status=header.get("batch_status"),
        )
        return PayoutStatus(
            payout_batch_id=header.get("payout_batch_id", payout_batch_id),
            batch_status=str(header.get("batch_status", "")),
            amount=Decimal(str(amount)) if amount is not None else None,
            currency=amount_obj.get("currency"),
            time_created=header.get("time_created"),
            items=tuple(items),
        )

    async def get_order_status(self, *, order_id: str) -> ReferenceStatus:
        payload = await self._request(
            "GET", f"/v2/checkout/orders/{order_id}", what="read the order status"
        )
        amount = None
        currency = None
        units = payload.get("purchase_units") or []
        if units:
            money = units[0].get("amount") or {}
            amount = money.get("value")
            currency = money.get("currency_code")
        return ReferenceStatus(
            reference_id=payload.get("id", order_id),
            status=str(payload.get("status", "")),
            amount=Decimal(str(amount)) if amount is not None else None,
            currency=currency,
        )

    async def get_capture_status(self, *, capture_id: str) -> ReferenceStatus:
        payload = await self._request(
            "GET", f"/v2/payments/captures/{capture_id}", what="read the capture status"
        )
        return self._reference_from_amount(payload, capture_id)

    async def get_refund_status(self, *, refund_id: str) -> ReferenceStatus:
        payload = await self._request(
            "GET", f"/v2/payments/refunds/{refund_id}", what="read the refund status"
        )
        return self._reference_from_amount(payload, refund_id)

    @staticmethod
    def _reference_from_amount(payload: dict[str, Any], fallback_id: str) -> ReferenceStatus:
        money = payload.get("amount") or {}
        amount = money.get("value")
        return ReferenceStatus(
            reference_id=payload.get("id", fallback_id),
            status=str(payload.get("status", "")),
            amount=Decimal(str(amount)) if amount is not None else None,
            currency=money.get("currency_code"),
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
        json: dict[str, Any] | None = None,
        what: str,
        request_id: str | None = None,
        _retried: bool = False,
    ) -> dict[str, Any]:
        token = await self.get_access_token(force_refresh=_retried)
        request_headers = {
            "Authorization": f"Bearer {token.token}",
            "Accept": "application/json",
        }
        if json is not None:
            request_headers["Content-Type"] = "application/json"
        if request_id:
            request_headers["PayPal-Request-Id"] = request_id

        try:
            response = await self._http.request(method, path, json=json, headers=request_headers)
        except httpx.HTTPError as exc:
            raise PayPalError(f"could not reach PayPal to {what}: {exc!s}") from exc

        # An expired or rejected token (most likely a supplied one that lapsed)
        # is retried once with a freshly minted token before giving up.
        if response.status_code == httpx.codes.UNAUTHORIZED and not _retried:
            logger.info("paypal.token_rejected_retrying", what=what)
            return await self._request(
                method, path, json=json, what=what, request_id=request_id, _retried=True
            )

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
