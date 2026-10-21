"""In-memory gateway fakes.

Both gateways sit behind Protocols precisely so the critical business logic
can be tested without a network call. These fakes record what they were
asked to do, which is how the suite asserts that a replayed webhook does not
pay twice and that an agent never moves money on its own.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.domain.enums import SettlementAction, Verdict
from app.domain.errors import AIError, PayPalError
from app.integrations.ai.interface import (
    CriterionJudgment,
    DealContext,
    DeliverableContext,
    DraftedCriterion,
    MediationRecommendation,
    VerificationJudgment,
)
from app.integrations.content.interface import FetchedContent
from app.integrations.paypal.interface import (
    AccessToken,
    CaptureResult,
    OrderResult,
    PayoutResult,
    RefundResult,
    WebhookHeaders,
)


@dataclass
class FakePayPalGateway:
    """Implements `PayPalGateway` in memory.

    `payouts` and `refunds` are the ledgers the idempotency tests assert on:
    a double release has to show up here as two entries, so a passing test
    means it did not happen.
    """

    orders: dict[str, dict[str, Any]] = field(default_factory=dict)
    captures: dict[str, dict[str, Any]] = field(default_factory=dict)
    payouts: list[dict[str, Any]] = field(default_factory=list)
    refunds: list[dict[str, Any]] = field(default_factory=list)
    seen_request_ids: set[str] = field(default_factory=set)

    webhook_verifies: bool = True
    fail_next_payout: bool = False
    fail_next_refund: bool = False
    fail_next_capture: bool = False
    fail_next_client_token: bool = False
    capture_status: str = "COMPLETED"
    _counter: int = 0

    def _next_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}-{self._counter:04d}"

    async def get_access_token(self) -> AccessToken:
        return AccessToken(token="fake-token", expires_at_epoch=time.time() + 3600)

    async def get_client_token(self) -> str:
        if self.fail_next_client_token:
            self.fail_next_client_token = False
            raise PayPalError("PayPal would not issue a client token (simulated failure)")
        return "fake-browser-safe-client-token"

    async def create_order(
        self,
        *,
        amount: Decimal,
        currency: str,
        reference_id: str,
        description: str,
        request_id: str,
    ) -> OrderResult:
        # PayPal-Request-Id semantics: the same key returns the same order.
        for order_id, order in self.orders.items():
            if order["request_id"] == request_id:
                return OrderResult(order_id=order_id, status="CREATED")

        order_id = self._next_id("ORDER")
        self.orders[order_id] = {
            "amount": amount,
            "currency": currency,
            "reference_id": reference_id,
            "description": description,
            "request_id": request_id,
            "captured": False,
        }
        self.seen_request_ids.add(request_id)
        return OrderResult(
            order_id=order_id,
            status="CREATED",
            approve_url=f"https://sandbox.paypal.test/checkout/{order_id}",
        )

    async def capture_order(self, *, order_id: str, request_id: str) -> CaptureResult:
        if self.fail_next_capture:
            self.fail_next_capture = False
            raise PayPalError("PayPal could not capture order (simulated failure)")

        order = self.orders.get(order_id)
        if order is None:
            raise PayPalError(f"unknown order {order_id}")

        # A replayed capture returns the original capture, as PayPal does.
        for capture_id, capture in self.captures.items():
            if capture["order_id"] == order_id:
                return CaptureResult(
                    order_id=order_id,
                    capture_id=capture_id,
                    status=self.capture_status,
                    amount=capture["amount"],
                    currency=capture["currency"],
                )

        capture_id = self._next_id("CAPTURE")
        self.captures[capture_id] = {
            "order_id": order_id,
            "amount": order["amount"],
            "currency": order["currency"],
            "refunded": Decimal("0.00"),
        }
        order["captured"] = True
        return CaptureResult(
            order_id=order_id,
            capture_id=capture_id,
            status=self.capture_status,
            amount=order["amount"],
            currency=order["currency"],
        )

    async def create_payout(
        self,
        *,
        receiver_email: str,
        amount: Decimal,
        currency: str,
        sender_batch_id: str,
        note: str,
    ) -> PayoutResult:
        if self.fail_next_payout:
            self.fail_next_payout = False
            raise PayPalError("PayPal could not create payout (simulated failure)")

        # PayPal rejects a duplicate sender_batch_id; so does this fake.
        for payout in self.payouts:
            if payout["sender_batch_id"] == sender_batch_id:
                raise PayPalError(f"a payout with sender_batch_id {sender_batch_id} already exists")

        batch_id = self._next_id("PAYOUT")
        self.payouts.append(
            {
                "payout_batch_id": batch_id,
                "sender_batch_id": sender_batch_id,
                "receiver_email": receiver_email,
                "amount": amount,
                "currency": currency,
                "note": note,
            }
        )
        return PayoutResult(
            payout_batch_id=batch_id, batch_status="PENDING", sender_batch_id=sender_batch_id
        )

    async def refund_capture(
        self,
        *,
        capture_id: str,
        amount: Decimal,
        currency: str,
        request_id: str,
        note: str,
    ) -> RefundResult:
        if self.fail_next_refund:
            self.fail_next_refund = False
            raise PayPalError("PayPal could not refund capture (simulated failure)")

        for refund in self.refunds:
            if refund["request_id"] == request_id:
                return RefundResult(
                    refund_id=refund["refund_id"],
                    status="COMPLETED",
                    amount=refund["amount"],
                    currency=refund["currency"],
                )

        capture = self.captures.get(capture_id)
        if capture is None:
            raise PayPalError(f"unknown capture {capture_id}")
        if capture["refunded"] + amount > capture["amount"]:
            raise PayPalError("refund would exceed the captured amount")
        capture["refunded"] += amount

        refund_id = self._next_id("REFUND")
        self.refunds.append(
            {
                "refund_id": refund_id,
                "capture_id": capture_id,
                "amount": amount,
                "currency": currency,
                "request_id": request_id,
                "note": note,
            }
        )
        return RefundResult(
            refund_id=refund_id, status="COMPLETED", amount=amount, currency=currency
        )

    async def verify_webhook(
        self, *, headers: WebhookHeaders, event_body: dict[str, Any], webhook_id: str
    ) -> bool:
        return self.webhook_verifies

    # --- assertions the tests read ---------------------------------------

    @property
    def total_paid_out(self) -> Decimal:
        return sum((payout["amount"] for payout in self.payouts), Decimal("0.00"))

    @property
    def total_refunded(self) -> Decimal:
        return sum((refund["amount"] for refund in self.refunds), Decimal("0.00"))


@dataclass
class FakeAIGateway:
    """Implements `AIGateway` with judgments the test chooses up front."""

    criteria: tuple[str, ...] = (
        "The deliverable is a working link to the agreed logo file.",
        "The logo is supplied in vector format (SVG or AI).",
    )
    verdict: Verdict = Verdict.PASS
    confidence: Decimal = Decimal("0.95")
    reasoning: str = "Every criterion is met by the submitted deliverable."
    failed_criteria_ids: tuple[str, ...] = ()
    recommendation: SettlementAction = SettlementAction.REFUND
    recommendation_reasoning: str = "The deliverable does not meet the agreed criteria."
    suggested_seller_amount: Decimal | None = None

    raise_on_draft: bool = False
    return_inconclusive: bool = False

    draft_calls: int = 0
    verify_calls: int = 0
    mediate_calls: int = 0
    last_deliverable: DeliverableContext | None = None

    async def draft_criteria(self, *, deal: DealContext) -> tuple[DraftedCriterion, ...]:
        self.draft_calls += 1
        if self.raise_on_draft:
            raise AIError("the criteria agent is unavailable (simulated failure)")
        return tuple(DraftedCriterion(text=text) for text in self.criteria)

    async def verify_deliverable(
        self,
        *,
        deal: DealContext,
        criteria: tuple[tuple[str, str], ...],
        deliverable: DeliverableContext,
    ) -> VerificationJudgment:
        self.verify_calls += 1
        self.last_deliverable = deliverable

        if self.return_inconclusive:
            return VerificationJudgment.inconclusive("the verifier could not complete")

        # Stay internally consistent: a FAIL verdict with every criterion
        # marked met is a judgment no real verifier would return, and a test
        # built on one proves nothing. Naming specific ids overrides this.
        fail_all = self.verdict is Verdict.FAIL and not self.failed_criteria_ids
        judgments = tuple(
            CriterionJudgment(
                criterion_id=criterion_id,
                text=text,
                passed=not fail_all and criterion_id not in self.failed_criteria_ids,
                note="checked by the fake verifier",
            )
            for criterion_id, text in criteria
        )
        return VerificationJudgment(
            verdict=self.verdict,
            confidence=self.confidence,
            reasoning=self.reasoning,
            per_criterion=judgments,
        )

    async def mediate_dispute(
        self,
        *,
        deal: DealContext,
        criteria: tuple[tuple[str, str], ...],
        deliverable: DeliverableContext | None,
        verification: VerificationJudgment | None,
    ) -> MediationRecommendation:
        self.mediate_calls += 1
        return MediationRecommendation(
            recommendation=self.recommendation,
            reasoning=self.recommendation_reasoning,
            suggested_seller_amount=self.suggested_seller_amount,
        )


@dataclass
class FakeContentFetcher:
    """Implements `ContentFetcher` without touching the network.

    Defaults to returning readable text, so an integration test that submits
    a link exercises the same path a real fetch would — the verifier sees
    retrieved content, not a URL.
    """

    text: str | None = "A vector logo file: <svg>...</svg>"
    image_base64: str | None = None
    media_type: str | None = "text/plain"
    unavailable_reason: str | None = None
    truncated: bool = False

    fetched: list[str] = field(default_factory=list)

    async def fetch(self, url: str) -> FetchedContent:
        self.fetched.append(url)

        if self.unavailable_reason is not None:
            return FetchedContent.unavailable(self.unavailable_reason, url)

        if self.image_base64 is not None:
            return FetchedContent(
                kind="image",
                source_url=url,
                image_base64=self.image_base64,
                media_type=self.media_type or "image/png",
            )

        return FetchedContent(
            kind="text",
            source_url=url,
            text=self.text,
            media_type=self.media_type,
            truncated=self.truncated,
        )
