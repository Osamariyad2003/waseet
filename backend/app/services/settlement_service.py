"""Settlement — the only place in the system that moves money out of escrow.

Release, refund and split all funnel through here, whether the decision came
from the policy or from a human reviewer. One service, so the money logic is
never duplicated.

Each settlement does the same five things, in one transaction:

  1. ask the state machine for the next state (which refuses an illegal or
     unguarded transition);
  2. compute the exact breakdown (which refuses to lose or invent money);
  3. move the money through the PayPal gateway with a deterministic
     idempotency key;
  4. record the PayPal reference on the deal and apply the new state;
  5. append the audit entry.

If step 3 fails, nothing is committed: the deal keeps its old state and the
caller sees a typed error. A deal is never left claiming RELEASED when no
payout happened.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import structlog

from app.config import Settings
from app.core import idempotency
from app.domain.entities import (
    SettlementBreakdown,
    compute_refund,
    compute_release,
    compute_split,
)
from app.domain.enums import Actor, DealState, SettlementAction, TransitionEvent
from app.domain.errors import PayPalError, SettlementError
from app.domain.spend_mandate import SpendMandate
from app.domain.state_machine import TransitionContext, is_already_applied, next_state
from app.integrations.paypal.interface import PayPalGateway
from app.models.deal import Deal
from app.repositories.audit_repo import AuditRepository

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SettlementOutcome:
    """What a settlement did. `already_settled` marks a replay no-op."""

    state: DealState
    breakdown: SettlementBreakdown | None
    paypal_reference: str | None
    already_settled: bool = False


class SettlementService:
    def __init__(
        self,
        *,
        settings: Settings,
        paypal: PayPalGateway,
        audit_repo: AuditRepository,
    ) -> None:
        self._settings = settings
        self._paypal = paypal
        self._audit = audit_repo

    async def settle(
        self,
        *,
        deal: Deal,
        action: SettlementAction,
        event: TransitionEvent,
        actor: Actor,
        reason: str,
        seller_amount: Decimal | None = None,
        context: TransitionContext | None = None,
    ) -> SettlementOutcome:
        """Execute a settlement. Does not commit — the caller owns the
        transaction so the state change, money movement and audit entry
        land together.

        `context` lets the caller state facts the deal's loaded
        relationships do not yet show — a verification report flushed in
        this same transaction, for instance. Omitted, it is derived from
        the deal.
        """
        # A replay of a settlement that already happened is a no-op, not a
        # second payout. This is the state-machine half of idempotency.
        if is_already_applied(deal.state, event):
            logger.info(
                "settlement.already_applied",
                deal_id=str(deal.id),
                deal_state=deal.state.value,
                # Not `event`: that is structlog's own name for the message.
                transition=event.value,
            )
            return SettlementOutcome(
                state=deal.state,
                breakdown=None,
                paypal_reference=self._reference_for(deal, action),
                already_settled=True,
            )

        target = next_state(deal.state, event, context or self._context_for(deal))
        breakdown = self._breakdown_for(deal, action, seller_amount)

        reference = await self._move_money(deal, breakdown)

        from_state = deal.state
        deal.state = target
        deal.platform_fee = breakdown.platform_fee

        self._audit.append(
            deal_id=deal.id,
            from_state=from_state,
            to_state=target,
            actor=actor,
            event=event.value,
            reason=reason,
            paypal_reference=reference,
        )
        logger.info(
            "settlement.executed",
            deal_id=str(deal.id),
            action=action.value,
            from_state=from_state.value,
            deal_state=target.value,
            to_seller=str(breakdown.to_seller),
            to_buyer=str(breakdown.to_buyer),
            platform_fee=str(breakdown.platform_fee),
            paypal_reference=reference,
        )
        return SettlementOutcome(state=target, breakdown=breakdown, paypal_reference=reference)

    # --- money movement ---------------------------------------------------

    def _mint_mandate(self, deal: Deal) -> SpendMandate:
        """Mint the authority for this settlement from the deal aggregate.

        Everything in it comes from persisted deal state: the captured
        amount, the deal's currency, the designated seller, the capture to
        refund against. Nothing here is read from a request body or a model
        response, which is what makes the mandate meaningful.
        """
        if deal.paypal_capture_id is None:
            raise SettlementError("the deal has no captured payment to settle")
        return SpendMandate(
            deal_id=deal.id,
            captured_amount=deal.amount,
            currency=deal.currency,
            seller_recipient=self._receiver_email(deal),
            buyer_refund_capture_id=deal.paypal_capture_id,
        )

    async def _move_money(self, deal: Deal, breakdown: SettlementBreakdown) -> str | None:
        """Perform the PayPal calls for this breakdown.

        Every outbound payment is checked against the mandate immediately
        before the call, so the amount is always the deal's own and the
        recipient is always the deal's own seller. Nothing upstream — not an
        agent, not a deliverable, not a request body — can redirect either.
        """
        mandate = self._mint_mandate(deal)

        if breakdown.action is SettlementAction.RELEASE:
            return await self._payout(
                deal,
                mandate,
                amount=breakdown.to_seller,
                currency=breakdown.currency,
                action=breakdown.action,
                batch_id=idempotency.release_batch_id(deal.id),
                note=f"Waseet escrow release for deal {deal.id}",
            )

        if breakdown.action is SettlementAction.REFUND:
            return await self._refund(
                deal,
                mandate,
                amount=breakdown.to_buyer,
                currency=breakdown.currency,
                action=breakdown.action,
                request_id=idempotency.refund_request_id(deal.id),
                note="Waseet escrow refund",
            )

        # SPLIT: pay the seller's share, then refund the remainder. The
        # payout runs first because it is the harder call to reverse; if the
        # refund then fails, the transaction rolls back and the audit trail
        # shows no settlement, so the reviewer can retry with the same
        # idempotency keys and PayPal will not duplicate the payout.
        payout_reference = await self._payout(
            deal,
            mandate,
            amount=breakdown.to_seller,
            currency=breakdown.currency,
            action=breakdown.action,
            batch_id=idempotency.split_batch_id(deal.id),
            note=f"Waseet escrow split release for deal {deal.id}",
        )
        await self._refund(
            deal,
            mandate,
            amount=breakdown.to_buyer,
            currency=breakdown.currency,
            action=breakdown.action,
            request_id=idempotency.split_refund_request_id(deal.id),
            note="Waseet escrow split refund",
        )
        return payout_reference

    async def _payout(
        self,
        deal: Deal,
        mandate: SpendMandate,
        *,
        amount: Decimal,
        currency: str,
        action: SettlementAction,
        batch_id: str,
        note: str,
    ) -> str:
        receiver = mandate.seller_recipient
        if amount <= 0:
            # A 100% fee leaves nothing to send; there is no payout to make.
            logger.info("settlement.payout_skipped", deal_id=str(deal.id), reason="zero amount")
            return batch_id

        # The last gate before money leaves the platform.
        mandate.authorize_payout(
            recipient=receiver, amount=amount, currency=currency, action=action
        )
        try:
            result = await self._paypal.create_payout(
                receiver_email=receiver,
                amount=amount,
                currency=currency,
                sender_batch_id=batch_id,
                note=note,
            )
        except PayPalError as exc:
            raise SettlementError(f"the payout could not be sent: {exc.message}") from exc

        deal.payout_batch_id = result.payout_batch_id
        return result.payout_batch_id

    async def _refund(
        self,
        deal: Deal,
        mandate: SpendMandate,
        *,
        amount: Decimal,
        currency: str,
        action: SettlementAction,
        request_id: str,
        note: str,
    ) -> str:
        if amount <= 0:
            return request_id

        capture_id = mandate.buyer_refund_capture_id
        mandate.authorize_refund(
            capture_id=capture_id, amount=amount, currency=currency, action=action
        )
        try:
            result = await self._paypal.refund_capture(
                capture_id=capture_id,
                amount=amount,
                currency=currency,
                request_id=request_id,
                note=note,
            )
        except PayPalError as exc:
            raise SettlementError(f"the refund could not be issued: {exc.message}") from exc

        deal.refund_id = result.refund_id
        return result.refund_id

    def _receiver_email(self, deal: Deal) -> str:
        """The designated seller for this deal, and no one else."""
        receiver = (deal.seller.paypal_account_ref or "").strip() if deal.seller else ""
        if not receiver:
            receiver = self._settings.paypal_seller_receiver_email.strip()
        if not receiver:
            raise SettlementError(
                "the seller has no PayPal account on file, so funds cannot be released"
            )
        return receiver

    # --- helpers ----------------------------------------------------------

    def _breakdown_for(
        self, deal: Deal, action: SettlementAction, seller_amount: Decimal | None
    ) -> SettlementBreakdown:
        fee = self._settings.platform_fee_percent
        try:
            if action is SettlementAction.RELEASE:
                return compute_release(deal.amount, deal.currency, fee)
            if action is SettlementAction.REFUND:
                return compute_refund(deal.amount, deal.currency)
            if seller_amount is None:
                raise SettlementError("a split requires the amount to pay the seller")
            return compute_split(deal.amount, deal.currency, seller_amount, fee)
        except ValueError as exc:
            # The arithmetic refused: an out-of-range split, or a breakdown
            # that would not balance.
            raise SettlementError(str(exc)) from exc

    @staticmethod
    def _context_for(deal: Deal) -> TransitionContext:
        criteria = deal.criteria or []
        return TransitionContext(
            criteria_count=len(criteria),
            all_criteria_confirmed=bool(criteria)
            and all(criterion.is_confirmed for criterion in criteria),
            has_capture=deal.paypal_capture_id is not None,
            has_deliverable=bool(deal.deliverables),
            has_verification_report=bool(deal.verification_reports),
        )

    @staticmethod
    def _reference_for(deal: Deal, action: SettlementAction) -> str | None:
        if action is SettlementAction.REFUND:
            return deal.refund_id
        return deal.payout_batch_id


def deal_transition_context(deal: Deal) -> TransitionContext:
    """Shared with the other services, so every guard sees the same facts."""
    return SettlementService._context_for(deal)


def settlement_action_for(event: TransitionEvent) -> SettlementAction:
    """The money action a human decision implies."""
    mapping = {
        TransitionEvent.HUMAN_DECIDED_RELEASE: SettlementAction.RELEASE,
        TransitionEvent.HUMAN_DECIDED_REFUND: SettlementAction.REFUND,
        TransitionEvent.HUMAN_DECIDED_SPLIT: SettlementAction.SPLIT,
        TransitionEvent.VERIFICATION_PASSED_CONFIDENTLY: SettlementAction.RELEASE,
    }
    action = mapping.get(event)
    if action is None:
        raise SettlementError(f"{event.value} does not correspond to a settlement")
    return action
