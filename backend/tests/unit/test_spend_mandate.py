"""The spend mandate: amount and recipient pinned to the deal.

"The agent cannot alter amount, recipient, or action" is only true if
something refuses when it tries. These tests are that something's proof.
"""

from __future__ import annotations

import dataclasses
import uuid
from decimal import Decimal

import pytest

from app.domain.enums import SettlementAction
from app.domain.spend_mandate import SpendMandate, SpendMandateViolation

SELLER = "seller@sandbox.example.com"
CAPTURE = "CAPTURE-1"


def mandate(**overrides) -> SpendMandate:
    config = {
        "deal_id": uuid.uuid4(),
        "captured_amount": Decimal("250.00"),
        "currency": "USD",
        "seller_recipient": SELLER,
        "buyer_refund_capture_id": CAPTURE,
        **overrides,
    }
    return SpendMandate(**config)


class TestAuthorizedPayments:
    def test_a_release_to_the_seller_for_the_full_amount_is_authorized(self):
        mandate().authorize_payout(
            recipient=SELLER,
            amount=Decimal("250.00"),
            currency="USD",
            action=SettlementAction.RELEASE,
        )

    def test_a_release_net_of_a_fee_is_authorized(self):
        mandate().authorize_payout(
            recipient=SELLER,
            amount=Decimal("243.75"),
            currency="USD",
            action=SettlementAction.RELEASE,
        )

    def test_a_split_authorizes_both_a_payout_and_a_refund(self):
        given = mandate()
        given.authorize_payout(
            recipient=SELLER,
            amount=Decimal("100.00"),
            currency="USD",
            action=SettlementAction.SPLIT,
        )
        given.authorize_refund(
            capture_id=CAPTURE,
            amount=Decimal("150.00"),
            currency="USD",
            action=SettlementAction.SPLIT,
        )

    def test_a_full_refund_to_the_buyer_is_authorized(self):
        mandate().authorize_refund(
            capture_id=CAPTURE,
            amount=Decimal("250.00"),
            currency="USD",
            action=SettlementAction.REFUND,
        )


class TestRecipientIsPinned:
    @pytest.mark.parametrize(
        "recipient",
        [
            "attacker@example.com",
            "Seller@sandbox.example.com",  # case differs
            " seller@sandbox.example.com",  # padded
            "",
            "seller@sandbox.example.com.evil.com",
        ],
    )
    def test_a_payout_to_anyone_but_the_designated_seller_is_refused(self, recipient):
        """The single check that stops a redirected payout."""
        with pytest.raises(SpendMandateViolation, match="not the seller designated"):
            mandate().authorize_payout(
                recipient=recipient,
                amount=Decimal("10.00"),
                currency="USD",
                action=SettlementAction.RELEASE,
            )

    def test_a_refund_against_another_capture_is_refused(self):
        with pytest.raises(SpendMandateViolation, match="captured for this deal"):
            mandate().authorize_refund(
                capture_id="CAPTURE-SOMEONE-ELSE",
                amount=Decimal("10.00"),
                currency="USD",
                action=SettlementAction.REFUND,
            )


class TestAmountIsPinned:
    @pytest.mark.parametrize("amount", [Decimal("250.01"), Decimal("1000"), Decimal("999999")])
    def test_a_payout_over_the_captured_amount_is_refused(self, amount):
        with pytest.raises(SpendMandateViolation, match="exceeds"):
            mandate().authorize_payout(
                recipient=SELLER,
                amount=amount,
                currency="USD",
                action=SettlementAction.RELEASE,
            )

    def test_a_refund_over_the_captured_amount_is_refused(self):
        with pytest.raises(SpendMandateViolation, match="exceeds"):
            mandate().authorize_refund(
                capture_id=CAPTURE,
                amount=Decimal("500.00"),
                currency="USD",
                action=SettlementAction.REFUND,
            )

    @pytest.mark.parametrize("amount", [Decimal("0"), Decimal("-1"), Decimal("-250.00")])
    def test_a_non_positive_amount_is_refused(self, amount):
        with pytest.raises(SpendMandateViolation, match="must be positive"):
            mandate().authorize_payout(
                recipient=SELLER,
                amount=amount,
                currency="USD",
                action=SettlementAction.RELEASE,
            )

    def test_a_different_currency_is_refused(self):
        """No implicit FX; the deal's currency is the only one authorized."""
        with pytest.raises(SpendMandateViolation, match="currency"):
            mandate().authorize_payout(
                recipient=SELLER,
                amount=Decimal("10.00"),
                currency="EUR",
                action=SettlementAction.RELEASE,
            )


class TestActionIsPinned:
    def test_a_refund_action_cannot_authorize_a_payout(self):
        with pytest.raises(SpendMandateViolation, match="does not authorize a payout"):
            mandate().authorize_payout(
                recipient=SELLER,
                amount=Decimal("10.00"),
                currency="USD",
                action=SettlementAction.REFUND,
            )

    def test_a_release_action_cannot_authorize_a_refund(self):
        with pytest.raises(SpendMandateViolation, match="does not authorize a refund"):
            mandate().authorize_refund(
                capture_id=CAPTURE,
                amount=Decimal("10.00"),
                currency="USD",
                action=SettlementAction.RELEASE,
            )


class TestMandateIsImmutable:
    def test_a_mandate_cannot_be_widened_after_minting(self):
        """Frozen on purpose: no code path can raise its own limit."""
        given = mandate()
        for field, value in (
            ("captured_amount", Decimal("999999")),
            ("seller_recipient", "attacker@example.com"),
            ("buyer_refund_capture_id", "CAPTURE-OTHER"),
            ("currency", "EUR"),
        ):
            with pytest.raises(dataclasses.FrozenInstanceError):
                setattr(given, field, value)

    def test_the_limits_survive_a_refused_attempt(self):
        given = mandate()
        with pytest.raises(SpendMandateViolation):
            given.authorize_payout(
                recipient="attacker@example.com",
                amount=Decimal("999999"),
                currency="USD",
                action=SettlementAction.RELEASE,
            )
        # Still exactly as minted, and the legitimate payout still works.
        given.authorize_payout(
            recipient=SELLER,
            amount=Decimal("250.00"),
            currency="USD",
            action=SettlementAction.RELEASE,
        )
