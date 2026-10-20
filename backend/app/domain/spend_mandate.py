"""The spend mandate.

From the Agentic Workflow doc: "Any money action is pinned to this deal's
exact amount and the designated seller; the agent cannot alter amount,
recipient, or action."

That sentence is only true if something enforces it. This module is that
something. A mandate is minted from the deal aggregate — never from a
request body, a model response, or anything a deliverable could influence —
and every outbound payment is checked against it immediately before the
PayPal call.

The mandate is deliberately dumb and deliberately strict: it knows one
deal's captured amount, one recipient, and which actions exist. It cannot
be widened, only refused.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from app.domain.enums import SettlementAction
from app.domain.errors import DomainError


class SpendMandateViolation(DomainError):
    """An attempted payment does not match the deal it claims to settle."""

    code = "spend_mandate_violation"


@dataclass(frozen=True, slots=True)
class SpendMandate:
    """Authority to move exactly this deal's money, to exactly these parties.

    Frozen on purpose: once minted, nothing can widen it.
    """

    deal_id: uuid.UUID
    captured_amount: Decimal
    currency: str
    seller_recipient: str
    buyer_refund_capture_id: str

    def authorize_payout(
        self, *, recipient: str, amount: Decimal, currency: str, action: SettlementAction
    ) -> None:
        """Check a payout to the seller. Raises SpendMandateViolation.

        A payout is only ever to the designated seller, never more than the
        captured amount, and only for an action that pays the seller at all.
        """
        if action not in {SettlementAction.RELEASE, SettlementAction.SPLIT}:
            raise SpendMandateViolation(
                f"a {action.value} does not authorize a payout to the seller"
            )
        if recipient != self.seller_recipient:
            # The one check that stops a redirected payout, whatever
            # suggested the new recipient.
            raise SpendMandateViolation(
                "the payout recipient is not the seller designated on this deal"
            )
        self._check_amount(amount, currency, "payout")

    def authorize_refund(
        self, *, capture_id: str, amount: Decimal, currency: str, action: SettlementAction
    ) -> None:
        """Check a refund to the buyer. Raises SpendMandateViolation."""
        if action not in {SettlementAction.REFUND, SettlementAction.SPLIT}:
            raise SpendMandateViolation(
                f"a {action.value} does not authorize a refund to the buyer"
            )
        if capture_id != self.buyer_refund_capture_id:
            raise SpendMandateViolation(
                "the refund does not target the payment captured for this deal"
            )
        self._check_amount(amount, currency, "refund")

    def _check_amount(self, amount: Decimal, currency: str, what: str) -> None:
        if currency != self.currency:
            raise SpendMandateViolation(
                f"the {what} currency {currency} is not the deal's currency {self.currency}"
            )
        if amount <= 0:
            raise SpendMandateViolation(f"the {what} amount must be positive")
        if amount > self.captured_amount:
            raise SpendMandateViolation(
                f"the {what} of {amount} exceeds the {self.captured_amount} captured for this deal"
            )
