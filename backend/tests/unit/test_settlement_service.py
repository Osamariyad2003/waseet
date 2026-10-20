"""Settlement service, isolated from the database.

The money movement itself: which PayPal calls happen, with what amounts and
what idempotency keys, and what happens when one of them fails.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

import pytest

from app.config import Settings
from app.core import idempotency
from app.domain.enums import Actor, DealState, SettlementAction, TransitionEvent
from app.domain.errors import InvalidTransition, SettlementError
from app.domain.state_machine import TransitionContext
from app.services.settlement_service import SettlementService, settlement_action_for
from tests.fakes import FakePayPalGateway

# --- stand-ins for the ORM objects, so no database is involved -------------


@dataclass
class StubUser:
    paypal_account_ref: str | None = "seller@sandbox.example.com"


@dataclass
class StubCriterion:
    is_confirmed: bool = True


@dataclass
class StubDeal:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    state: DealState = DealState.DISPUTED
    amount: Decimal = Decimal("250.00")
    currency: str = "USD"
    platform_fee: Decimal | None = None
    paypal_capture_id: str | None = "CAPTURE-1"
    payout_batch_id: str | None = None
    refund_id: str | None = None
    seller: StubUser = field(default_factory=StubUser)
    criteria: list = field(default_factory=lambda: [StubCriterion()])
    deliverables: list = field(default_factory=lambda: [object()])
    verification_reports: list = field(default_factory=lambda: [object()])


@dataclass
class RecordingAudit:
    """Captures audit entries without a session."""

    entries: list = field(default_factory=list)

    def append(self, **kwargs):
        self.entries.append(kwargs)
        return kwargs

    @property
    def last(self) -> dict:
        return self.entries[-1]


def make_service(paypal: FakePayPalGateway, audit: RecordingAudit, **overrides):
    config = {
        "database_url": "sqlite+aiosqlite:///:memory:",
        "paypal_seller_receiver_email": "fallback@sandbox.example.com",
        **overrides,
    }
    return SettlementService(settings=Settings(**config), paypal=paypal, audit_repo=audit)


@pytest.fixture
def paypal() -> FakePayPalGateway:
    gateway = FakePayPalGateway()
    # Register the capture the stub deal refers to, so refunds can resolve it.
    gateway.captures["CAPTURE-1"] = {
        "order_id": "ORDER-1",
        "amount": Decimal("250.00"),
        "currency": "USD",
        "refunded": Decimal("0.00"),
    }
    return gateway


@pytest.fixture
def audit() -> RecordingAudit:
    return RecordingAudit()


class TestRelease:
    async def test_release_pays_the_full_amount_to_the_seller(self, paypal, audit):
        service = make_service(paypal, audit)
        deal = StubDeal()

        outcome = await service.settle(
            deal=deal,
            action=SettlementAction.RELEASE,
            event=TransitionEvent.HUMAN_DECIDED_RELEASE,
            actor=Actor.REVIEWER,
            reason="the work is acceptable",
        )

        assert outcome.state is DealState.RELEASED
        assert deal.state is DealState.RELEASED
        assert len(paypal.payouts) == 1
        assert paypal.payouts[0]["amount"] == Decimal("250.00")
        assert paypal.refunds == []

    async def test_release_uses_a_deal_derived_sender_batch_id(self, paypal, audit):
        """The idempotency key PayPal itself dedupes on."""
        service = make_service(paypal, audit)
        deal = StubDeal()

        await service.settle(
            deal=deal,
            action=SettlementAction.RELEASE,
            event=TransitionEvent.HUMAN_DECIDED_RELEASE,
            actor=Actor.REVIEWER,
            reason="ok",
        )

        assert paypal.payouts[0]["sender_batch_id"] == idempotency.release_batch_id(deal.id)

    async def test_the_payout_goes_to_the_deals_own_seller(self, paypal, audit):
        """The spend mandate: the recipient comes from the deal, not the request."""
        service = make_service(paypal, audit)
        deal = StubDeal(seller=StubUser(paypal_account_ref="designer@sandbox.example.com"))

        await service.settle(
            deal=deal,
            action=SettlementAction.RELEASE,
            event=TransitionEvent.HUMAN_DECIDED_RELEASE,
            actor=Actor.REVIEWER,
            reason="ok",
        )

        assert paypal.payouts[0]["receiver_email"] == "designer@sandbox.example.com"

    async def test_the_configured_fee_is_deducted(self, paypal, audit):
        service = make_service(paypal, audit, platform_fee_percent=Decimal("4"))
        deal = StubDeal()

        outcome = await service.settle(
            deal=deal,
            action=SettlementAction.RELEASE,
            event=TransitionEvent.HUMAN_DECIDED_RELEASE,
            actor=Actor.REVIEWER,
            reason="ok",
        )

        assert paypal.payouts[0]["amount"] == Decimal("240.00")
        assert outcome.breakdown.platform_fee == Decimal("10.00")
        assert deal.platform_fee == Decimal("10.00")

    async def test_a_seller_with_no_paypal_account_cannot_be_paid(self, paypal, audit):
        service = make_service(paypal, audit, paypal_seller_receiver_email="")
        deal = StubDeal(seller=StubUser(paypal_account_ref=None))

        with pytest.raises(SettlementError, match="no PayPal account"):
            await service.settle(
                deal=deal,
                action=SettlementAction.RELEASE,
                event=TransitionEvent.HUMAN_DECIDED_RELEASE,
                actor=Actor.REVIEWER,
                reason="ok",
            )
        assert paypal.payouts == []
        assert deal.state is DealState.DISPUTED  # unchanged


class TestRefund:
    async def test_refund_returns_everything_to_the_buyer(self, paypal, audit):
        service = make_service(paypal, audit)
        deal = StubDeal()

        outcome = await service.settle(
            deal=deal,
            action=SettlementAction.REFUND,
            event=TransitionEvent.HUMAN_DECIDED_REFUND,
            actor=Actor.REVIEWER,
            reason="not as agreed",
        )

        assert outcome.state is DealState.REFUNDED
        assert paypal.refunds[0]["amount"] == Decimal("250.00")
        assert paypal.payouts == []

    async def test_refund_uses_a_deal_derived_request_id(self, paypal, audit):
        service = make_service(paypal, audit)
        deal = StubDeal()

        await service.settle(
            deal=deal,
            action=SettlementAction.REFUND,
            event=TransitionEvent.HUMAN_DECIDED_REFUND,
            actor=Actor.REVIEWER,
            reason="x",
        )

        assert paypal.refunds[0]["request_id"] == idempotency.refund_request_id(deal.id)

    async def test_no_fee_is_taken_on_a_refund(self, paypal, audit):
        service = make_service(paypal, audit, platform_fee_percent=Decimal("10"))
        deal = StubDeal()

        outcome = await service.settle(
            deal=deal,
            action=SettlementAction.REFUND,
            event=TransitionEvent.HUMAN_DECIDED_REFUND,
            actor=Actor.REVIEWER,
            reason="x",
        )

        assert outcome.breakdown.platform_fee == Decimal("0.00")
        assert paypal.refunds[0]["amount"] == Decimal("250.00")


class TestSplit:
    async def test_split_pays_the_seller_and_refunds_the_rest(self, paypal, audit):
        service = make_service(paypal, audit)
        deal = StubDeal()

        outcome = await service.settle(
            deal=deal,
            action=SettlementAction.SPLIT,
            event=TransitionEvent.HUMAN_DECIDED_SPLIT,
            actor=Actor.REVIEWER,
            reason="partially delivered",
            seller_amount=Decimal("90.00"),
        )

        assert outcome.state is DealState.SPLIT
        assert paypal.total_paid_out == Decimal("90.00")
        assert paypal.total_refunded == Decimal("160.00")

    async def test_split_uses_distinct_idempotency_keys(self, paypal, audit):
        """So a split cannot collide with a plain release on the same deal."""
        service = make_service(paypal, audit)
        deal = StubDeal()

        await service.settle(
            deal=deal,
            action=SettlementAction.SPLIT,
            event=TransitionEvent.HUMAN_DECIDED_SPLIT,
            actor=Actor.REVIEWER,
            reason="x",
            seller_amount=Decimal("90.00"),
        )

        assert paypal.payouts[0]["sender_batch_id"] == idempotency.split_batch_id(deal.id)
        assert paypal.refunds[0]["request_id"] == idempotency.split_refund_request_id(deal.id)
        assert idempotency.split_batch_id(deal.id) != idempotency.release_batch_id(deal.id)

    async def test_a_split_needs_an_amount(self, paypal, audit):
        service = make_service(paypal, audit)

        with pytest.raises(SettlementError, match="requires the amount"):
            await service.settle(
                deal=StubDeal(),
                action=SettlementAction.SPLIT,
                event=TransitionEvent.HUMAN_DECIDED_SPLIT,
                actor=Actor.REVIEWER,
                reason="x",
            )
        assert paypal.payouts == []

    @pytest.mark.parametrize("amount", [Decimal("0"), Decimal("250.00"), Decimal("900.00")])
    async def test_a_split_outside_the_captured_amount_is_refused(self, paypal, audit, amount):
        service = make_service(paypal, audit)

        with pytest.raises(SettlementError):
            await service.settle(
                deal=StubDeal(),
                action=SettlementAction.SPLIT,
                event=TransitionEvent.HUMAN_DECIDED_SPLIT,
                actor=Actor.REVIEWER,
                reason="x",
                seller_amount=amount,
            )
        assert paypal.payouts == []
        assert paypal.refunds == []

    async def test_a_failed_refund_leaves_the_split_unfinished_for_retry(self, paypal, audit):
        """The caller rolls back, and the same keys make a retry safe."""
        service = make_service(paypal, audit)
        deal = StubDeal()
        paypal.fail_next_refund = True

        with pytest.raises(SettlementError, match="refund could not be issued"):
            await service.settle(
                deal=deal,
                action=SettlementAction.SPLIT,
                event=TransitionEvent.HUMAN_DECIDED_SPLIT,
                actor=Actor.REVIEWER,
                reason="x",
                seller_amount=Decimal("90.00"),
            )

        assert deal.state is DealState.DISPUTED  # not SPLIT
        assert audit.entries == []  # nothing recorded


class TestGuardsAndIdempotency:
    async def test_a_deal_with_no_capture_cannot_be_settled(self, paypal, audit):
        service = make_service(paypal, audit)
        deal = StubDeal(paypal_capture_id=None)

        with pytest.raises(Exception) as exc:
            await service.settle(
                deal=deal,
                action=SettlementAction.RELEASE,
                event=TransitionEvent.HUMAN_DECIDED_RELEASE,
                actor=Actor.REVIEWER,
                reason="x",
            )
        assert "captured payment" in str(exc.value)
        assert paypal.payouts == []

    async def test_settling_a_terminal_deal_is_refused(self, paypal, audit):
        service = make_service(paypal, audit)
        deal = StubDeal(state=DealState.REFUNDED)

        with pytest.raises(InvalidTransition):
            await service.settle(
                deal=deal,
                action=SettlementAction.RELEASE,
                event=TransitionEvent.HUMAN_DECIDED_RELEASE,
                actor=Actor.REVIEWER,
                reason="x",
            )
        assert paypal.payouts == []

    async def test_a_replayed_release_is_a_no_op(self, paypal, audit):
        """The deal is already RELEASED, so there is nothing left to pay."""
        service = make_service(paypal, audit)
        deal = StubDeal(state=DealState.RELEASED, payout_batch_id="PAYOUT-0001")

        outcome = await service.settle(
            deal=deal,
            action=SettlementAction.RELEASE,
            event=TransitionEvent.HUMAN_DECIDED_RELEASE,
            actor=Actor.REVIEWER,
            reason="x",
        )

        assert outcome.already_settled
        assert outcome.state is DealState.RELEASED
        assert outcome.paypal_reference == "PAYOUT-0001"
        assert paypal.payouts == []
        assert audit.entries == []

    async def test_a_failed_payout_records_nothing(self, paypal, audit):
        service = make_service(paypal, audit)
        deal = StubDeal()
        paypal.fail_next_payout = True

        with pytest.raises(SettlementError, match="payout could not be sent"):
            await service.settle(
                deal=deal,
                action=SettlementAction.RELEASE,
                event=TransitionEvent.HUMAN_DECIDED_RELEASE,
                actor=Actor.REVIEWER,
                reason="x",
            )

        assert deal.state is DealState.DISPUTED
        assert audit.entries == []

    async def test_an_explicit_context_can_satisfy_a_guard(self, paypal, audit):
        """How the verification service tells the guard about a report it has
        flushed but not yet reloaded."""
        service = make_service(paypal, audit)
        deal = StubDeal(state=DealState.VERIFYING, verification_reports=[])

        outcome = await service.settle(
            deal=deal,
            action=SettlementAction.RELEASE,
            event=TransitionEvent.VERIFICATION_PASSED_CONFIDENTLY,
            actor=Actor.AI,
            reason="confident pass",
            context=TransitionContext(
                criteria_count=1,
                all_criteria_confirmed=True,
                has_capture=True,
                has_deliverable=True,
                has_verification_report=True,
            ),
        )
        assert outcome.state is DealState.RELEASED

    async def test_a_hundred_percent_fee_skips_the_payout_but_still_settles(self, paypal, audit):
        service = make_service(paypal, audit, platform_fee_percent=Decimal("100"))
        deal = StubDeal()

        outcome = await service.settle(
            deal=deal,
            action=SettlementAction.RELEASE,
            event=TransitionEvent.HUMAN_DECIDED_RELEASE,
            actor=Actor.REVIEWER,
            reason="x",
        )

        assert outcome.state is DealState.RELEASED
        assert paypal.payouts == []  # there is nothing to send
        assert outcome.breakdown.platform_fee == Decimal("250.00")


class TestAuditTrail:
    async def test_every_settlement_records_actor_reason_and_reference(self, paypal, audit):
        service = make_service(paypal, audit)
        deal = StubDeal()

        await service.settle(
            deal=deal,
            action=SettlementAction.RELEASE,
            event=TransitionEvent.HUMAN_DECIDED_RELEASE,
            actor=Actor.REVIEWER,
            reason="the reviewer accepted the work",
        )

        entry = audit.last
        assert entry["from_state"] is DealState.DISPUTED
        assert entry["to_state"] is DealState.RELEASED
        assert entry["actor"] is Actor.REVIEWER
        assert entry["reason"] == "the reviewer accepted the work"
        assert entry["paypal_reference"] is not None


class TestActionMapping:
    @pytest.mark.parametrize(
        ("event", "action"),
        [
            (TransitionEvent.HUMAN_DECIDED_RELEASE, SettlementAction.RELEASE),
            (TransitionEvent.HUMAN_DECIDED_REFUND, SettlementAction.REFUND),
            (TransitionEvent.HUMAN_DECIDED_SPLIT, SettlementAction.SPLIT),
            (TransitionEvent.VERIFICATION_PASSED_CONFIDENTLY, SettlementAction.RELEASE),
        ],
    )
    def test_events_map_to_their_money_action(self, event, action):
        assert settlement_action_for(event) is action

    @pytest.mark.parametrize(
        "event",
        [
            TransitionEvent.VERIFICATION_NOT_CONFIDENT,
            TransitionEvent.BUYER_CONTESTED,
            TransitionEvent.DELIVERABLE_SUBMITTED,
        ],
    )
    def test_a_non_settling_event_has_no_money_action(self, event):
        """Nothing that routes to DISPUTED can be mistaken for a payout."""
        with pytest.raises(SettlementError):
            settlement_action_for(event)
