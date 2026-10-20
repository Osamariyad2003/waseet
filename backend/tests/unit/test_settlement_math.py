"""Settlement arithmetic. A breakdown that does not balance must not exist."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.entities import (
    Money,
    SettlementBreakdown,
    compute_refund,
    compute_release,
    compute_split,
    quantize_money,
)
from app.domain.enums import SettlementAction


class TestRelease:
    def test_release_with_no_fee_pays_the_whole_amount(self):
        breakdown = compute_release(Decimal("250.00"), "USD")
        assert breakdown.action is SettlementAction.RELEASE
        assert breakdown.to_seller == Decimal("250.00")
        assert breakdown.to_buyer == Decimal("0.00")
        assert breakdown.platform_fee == Decimal("0.00")

    def test_release_takes_the_configured_fee(self):
        breakdown = compute_release(Decimal("100.00"), "USD", Decimal("2.5"))
        assert breakdown.platform_fee == Decimal("2.50")
        assert breakdown.to_seller == Decimal("97.50")

    def test_fee_rounds_to_cents_and_still_balances(self):
        breakdown = compute_release(Decimal("33.33"), "USD", Decimal("3"))
        assert breakdown.platform_fee == Decimal("1.00")  # 0.9999 -> 1.00
        assert breakdown.to_seller == Decimal("32.33")
        assert breakdown.to_seller + breakdown.platform_fee == Decimal("33.33")

    def test_a_hundred_percent_fee_leaves_the_seller_nothing_but_balances(self):
        breakdown = compute_release(Decimal("10.00"), "USD", Decimal("100"))
        assert breakdown.to_seller == Decimal("0.00")
        assert breakdown.platform_fee == Decimal("10.00")

    @pytest.mark.parametrize("fee", [Decimal("-1"), Decimal("101")])
    def test_an_out_of_range_fee_is_rejected(self, fee):
        with pytest.raises(ValueError, match="fee percent"):
            compute_release(Decimal("10.00"), "USD", fee)


class TestRefund:
    def test_refund_returns_everything_to_the_buyer(self):
        breakdown = compute_refund(Decimal("75.40"), "USD")
        assert breakdown.action is SettlementAction.REFUND
        assert breakdown.to_buyer == Decimal("75.40")
        assert breakdown.to_seller == Decimal("0.00")

    def test_no_fee_is_taken_on_a_refund(self):
        """The platform does not profit from a deal that failed."""
        assert compute_refund(Decimal("75.40"), "USD").platform_fee == Decimal("0.00")


class TestSplit:
    def test_split_pays_the_seller_and_refunds_the_rest(self):
        breakdown = compute_split(Decimal("200.00"), "USD", seller_amount=Decimal("120.00"))
        assert breakdown.action is SettlementAction.SPLIT
        assert breakdown.to_seller == Decimal("120.00")
        assert breakdown.to_buyer == Decimal("80.00")

    def test_the_fee_comes_out_of_the_sellers_share_only(self):
        breakdown = compute_split(
            Decimal("200.00"), "USD", seller_amount=Decimal("100.00"), fee_percent=Decimal("10")
        )
        assert breakdown.platform_fee == Decimal("10.00")
        assert breakdown.to_seller == Decimal("90.00")
        assert breakdown.to_buyer == Decimal("100.00")  # buyer is unaffected by the fee

    def test_a_split_that_pays_the_seller_nothing_is_a_refund_not_a_split(self):
        with pytest.raises(ValueError, match="use a refund instead"):
            compute_split(Decimal("200.00"), "USD", seller_amount=Decimal("0"))

    def test_a_split_that_leaves_the_buyer_nothing_is_a_release_not_a_split(self):
        with pytest.raises(ValueError, match="use a release instead"):
            compute_split(Decimal("200.00"), "USD", seller_amount=Decimal("200.00"))

    def test_a_split_over_the_captured_amount_is_rejected(self):
        with pytest.raises(ValueError):
            compute_split(Decimal("200.00"), "USD", seller_amount=Decimal("500.00"))

    def test_a_negative_seller_share_is_rejected(self):
        with pytest.raises(ValueError):
            compute_split(Decimal("200.00"), "USD", seller_amount=Decimal("-5.00"))


class TestInvariants:
    @pytest.mark.parametrize(
        "captured", [Decimal("0.01"), Decimal("1.00"), Decimal("99.99"), Decimal("12345.67")]
    )
    @pytest.mark.parametrize("fee", [Decimal("0"), Decimal("1"), Decimal("2.9"), Decimal("33.3")])
    def test_every_release_balances_to_the_cent(self, captured, fee):
        breakdown = compute_release(captured, "USD", fee)
        assert breakdown.to_seller + breakdown.to_buyer + breakdown.platform_fee == captured

    def test_a_breakdown_that_does_not_balance_cannot_be_constructed(self):
        with pytest.raises(ValueError, match="does not balance"):
            SettlementBreakdown(
                action=SettlementAction.RELEASE,
                captured=Decimal("100.00"),
                to_seller=Decimal("99.00"),  # a cent short — money would vanish
                to_buyer=Decimal("0.00"),
                platform_fee=Decimal("0.00"),
                currency="USD",
            )

    def test_a_breakdown_cannot_invent_money(self):
        with pytest.raises(ValueError, match="does not balance"):
            SettlementBreakdown(
                action=SettlementAction.RELEASE,
                captured=Decimal("100.00"),
                to_seller=Decimal("150.00"),
                to_buyer=Decimal("0.00"),
                platform_fee=Decimal("0.00"),
                currency="USD",
            )

    def test_negative_components_are_rejected(self):
        with pytest.raises(ValueError):
            SettlementBreakdown(
                action=SettlementAction.SPLIT,
                captured=Decimal("100.00"),
                to_seller=Decimal("110.00"),
                to_buyer=Decimal("-10.00"),
                platform_fee=Decimal("0.00"),
                currency="USD",
            )


class TestMoney:
    def test_paypal_value_is_always_two_decimals(self):
        assert Money(Decimal("5"), "USD").paypal_value == "5.00"
        assert Money(Decimal("5.5"), "USD").paypal_value == "5.50"
        assert Money(Decimal("5.004"), "USD").paypal_value == "5.00"

    def test_negative_money_is_rejected(self):
        with pytest.raises(ValueError, match="negative"):
            Money(Decimal("-1"), "USD")

    def test_currency_must_be_an_iso_code(self):
        with pytest.raises(ValueError, match="3-letter"):
            Money(Decimal("1"), "DOLLARS")

    def test_quantize_rounds_half_up(self):
        assert quantize_money(Decimal("1.005")) == Decimal("1.01")
        assert quantize_money(Decimal("1.004")) == Decimal("1.00")
