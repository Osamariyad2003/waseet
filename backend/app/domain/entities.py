"""Domain value objects and the pure settlement arithmetic.

Framework-free: no SQLAlchemy, no FastAPI, no network. The persistent
aggregates live in `app/models` as ORM rows; what lives here is the logic
that has to be correct to the cent and therefore has to be unit-testable
without a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.domain.enums import SettlementAction

CENTS = Decimal("0.01")


def quantize_money(value: Decimal) -> Decimal:
    """Round to two decimal places, the precision PayPal accepts."""
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError("money amount cannot be negative")
        if len(self.currency) != 3:
            raise ValueError("currency must be a 3-letter ISO code")

    @property
    def paypal_value(self) -> str:
        """The string form PayPal's APIs expect, e.g. "49.99"."""
        return f"{quantize_money(self.amount):.2f}"


@dataclass(frozen=True, slots=True)
class SettlementBreakdown:
    """How one captured payment is divided. Always exact.

    `to_seller + to_buyer + platform_fee == captured` holds by
    construction, so a settlement can never silently lose or invent money.
    """

    action: SettlementAction
    captured: Decimal
    to_seller: Decimal
    to_buyer: Decimal
    platform_fee: Decimal
    currency: str

    def __post_init__(self) -> None:
        total = self.to_seller + self.to_buyer + self.platform_fee
        if total != self.captured:
            raise ValueError(
                f"settlement does not balance: {self.to_seller} + {self.to_buyer} + "
                f"{self.platform_fee} != {self.captured}"
            )
        for field_name in ("captured", "to_seller", "to_buyer", "platform_fee"):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} cannot be negative")

    @property
    def seller_money(self) -> Money:
        return Money(self.to_seller, self.currency)

    @property
    def buyer_money(self) -> Money:
        return Money(self.to_buyer, self.currency)


def compute_release(
    captured: Decimal, currency: str, fee_percent: Decimal = Decimal("0")
) -> SettlementBreakdown:
    """Full release to the seller, minus the configurable platform fee (FR-13)."""
    captured = quantize_money(captured)
    fee = _fee_for(captured, fee_percent)
    return SettlementBreakdown(
        action=SettlementAction.RELEASE,
        captured=captured,
        to_seller=captured - fee,
        to_buyer=Decimal("0.00"),
        platform_fee=fee,
        currency=currency,
    )


def compute_refund(captured: Decimal, currency: str) -> SettlementBreakdown:
    """Full refund to the buyer. No fee is taken on a refund — the platform
    does not profit from a deal that failed."""
    captured = quantize_money(captured)
    return SettlementBreakdown(
        action=SettlementAction.REFUND,
        captured=captured,
        to_seller=Decimal("0.00"),
        to_buyer=captured,
        platform_fee=Decimal("0.00"),
        currency=currency,
    )


def compute_split(
    captured: Decimal,
    currency: str,
    seller_amount: Decimal,
    fee_percent: Decimal = Decimal("0"),
) -> SettlementBreakdown:
    """Split: `seller_amount` (gross) is paid out, the remainder is refunded.

    The fee is taken out of the seller's share only, so the buyer always
    gets back exactly `captured - seller_amount`.
    """
    captured = quantize_money(captured)
    seller_amount = quantize_money(seller_amount)

    if seller_amount <= 0:
        raise ValueError("a split must pay the seller something; use a refund instead")
    if seller_amount >= captured:
        raise ValueError("a split must leave something for the buyer; use a release instead")

    fee = _fee_for(seller_amount, fee_percent)
    return SettlementBreakdown(
        action=SettlementAction.SPLIT,
        captured=captured,
        to_seller=seller_amount - fee,
        to_buyer=captured - seller_amount,
        platform_fee=fee,
        currency=currency,
    )


def _fee_for(base: Decimal, fee_percent: Decimal) -> Decimal:
    if fee_percent < 0 or fee_percent > 100:
        raise ValueError("fee percent must be between 0 and 100")
    return quantize_money(base * fee_percent / Decimal("100"))
