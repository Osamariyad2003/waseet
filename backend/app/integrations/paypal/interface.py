"""The PayPalGateway contract.

Services depend on this Protocol, never on httpx or a PayPal SDK type, so
the business logic is unit-testable without the network and the vendor can
be swapped behind the interface.

Every method raises `PayPalError` on failure — no vendor exception escapes
this boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class OrderResult:
    """A created PayPal order, ready for the buyer to approve in the JS SDK."""

    order_id: str
    status: str
    approve_url: str | None = None


@dataclass(frozen=True, slots=True)
class CaptureResult:
    """A captured payment — the money now sits in the platform account."""

    order_id: str
    capture_id: str
    status: str
    amount: Decimal
    currency: str

    @property
    def is_completed(self) -> bool:
        return self.status.upper() == "COMPLETED"


@dataclass(frozen=True, slots=True)
class PayoutResult:
    """A payout batch sent to the seller."""

    payout_batch_id: str
    batch_status: str
    # Echoed back so a replay can be recognised: the sender_batch_id is
    # derived from the deal id, which is what makes a payout idempotent.
    sender_batch_id: str

    @property
    def is_accepted(self) -> bool:
        return self.batch_status.upper() in {"PENDING", "PROCESSING", "SUCCESS"}


@dataclass(frozen=True, slots=True)
class RefundResult:
    """A refund of a capture, returning funds to the buyer."""

    refund_id: str
    status: str
    amount: Decimal
    currency: str

    @property
    def is_completed(self) -> bool:
        return self.status.upper() in {"COMPLETED", "PENDING"}


@dataclass(frozen=True, slots=True)
class WebhookHeaders:
    """The transmission headers PayPal signs an event with.

    Kept as a value object so the router can validate shape at the edge and
    the gateway never reads a raw request.
    """

    transmission_id: str
    transmission_time: str
    transmission_sig: str
    cert_url: str
    auth_algo: str

    @classmethod
    def from_mapping(cls, headers: Any) -> WebhookHeaders | None:
        """Build from request headers, or None when any are missing.

        A missing header is a failed verification, never a pass.
        """

        def read(name: str) -> str:
            return (headers.get(name) or "").strip()

        values = {
            "transmission_id": read("paypal-transmission-id"),
            "transmission_time": read("paypal-transmission-time"),
            "transmission_sig": read("paypal-transmission-sig"),
            "cert_url": read("paypal-cert-url"),
            "auth_algo": read("paypal-auth-algo"),
        }
        if not all(values.values()):
            return None
        return cls(**values)


@dataclass(frozen=True, slots=True)
class AccessToken:
    token: str
    expires_at_epoch: float
    scope: str = field(default="", repr=False)

    def __repr__(self) -> str:  # never let a token reach a log line
        return f"AccessToken(expires_at_epoch={self.expires_at_epoch})"


@runtime_checkable
class PayPalGateway(Protocol):
    """Money rails. The only path from Waseet to PayPal."""

    async def get_access_token(self) -> AccessToken:
        """Fetch (or reuse a cached) OAuth2 client-credentials token."""
        ...

    async def get_client_token(self) -> str:
        """Mint a browser-safe token for the PayPal JS SDK v6.

        v6 authenticates the browser SDK with a short-lived client token
        rather than exposing the client id alone. This token is safe to send
        to the browser; the client secret never leaves the server.
        """
        ...

    async def create_order(
        self,
        *,
        amount: Decimal,
        currency: str,
        reference_id: str,
        description: str,
        request_id: str,
    ) -> OrderResult:
        """Create a CAPTURE-intent order for the buyer to approve.

        `request_id` is sent as PayPal-Request-Id so a retried create does
        not produce a second order.
        """
        ...

    async def capture_order(self, *, order_id: str, request_id: str) -> CaptureResult:
        """Capture an approved order into the platform account ("escrow")."""
        ...

    async def create_payout(
        self,
        *,
        receiver_email: str,
        amount: Decimal,
        currency: str,
        sender_batch_id: str,
        note: str,
    ) -> PayoutResult:
        """Release funds to the seller.

        `sender_batch_id` is derived from the deal id, so PayPal itself
        rejects a duplicate batch — a replayed webhook cannot double-pay.
        """
        ...

    async def refund_capture(
        self,
        *,
        capture_id: str,
        amount: Decimal,
        currency: str,
        request_id: str,
        note: str,
    ) -> RefundResult:
        """Return captured funds to the buyer, in full or in part."""
        ...

    async def verify_webhook(
        self, *, headers: WebhookHeaders, event_body: dict[str, Any], webhook_id: str
    ) -> bool:
        """Ask PayPal whether this event's signature is genuine.

        Returns False rather than raising on a failed verification, so the
        caller treats "not verified" as a normal rejection path.
        """
        ...
