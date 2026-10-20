"""Deal lifecycle up to the point of verification.

Covers creation with AI-drafted criteria (FR-1, FR-2), funding through
PayPal (FR-3), deliverable submission (FR-4) and a buyer contest (FR-7).
Every state change goes through the state machine and writes an audit entry
in the same transaction.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from decimal import Decimal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import idempotency
from app.core.errors import ValidationError
from app.domain.enums import Actor, DealState, DeliverableType, Role, TransitionEvent
from app.domain.errors import (
    DealNotFound,
    NotAuthorizedForDeal,
    PayPalError,
    TransitionGuardFailed,
)
from app.domain.state_machine import next_state
from app.integrations.ai.interface import AIGateway, DealContext
from app.integrations.paypal.interface import PayPalGateway
from app.models.deal import Deal
from app.models.deliverable import Deliverable
from app.repositories.audit_repo import AuditRepository
from app.repositories.deal_repo import DealRepository
from app.repositories.deliverable_repo import DeliverableRepository
from app.services.settlement_service import deal_transition_context

logger = structlog.get_logger(__name__)

MIN_AMOUNT = Decimal("1.00")
MAX_AMOUNT = Decimal("10000.00")
SUPPORTED_CURRENCIES = frozenset({"USD", "EUR", "GBP"})


@dataclass(frozen=True, slots=True)
class CreateDealCommand:
    buyer_id: uuid.UUID
    seller_id: uuid.UUID
    title: str
    description: str
    amount: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class OrderCreated:
    order_id: str
    approve_url: str | None


class DealService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        deal_repo: DealRepository,
        deliverable_repo: DeliverableRepository,
        audit_repo: AuditRepository,
        ai: AIGateway,
        paypal: PayPalGateway,
    ) -> None:
        self._session = session
        self._deals = deal_repo
        self._deliverables = deliverable_repo
        self._audit = audit_repo
        self._ai = ai
        self._paypal = paypal

    # --- FR-1 / FR-2: creation and criteria -------------------------------

    async def create_deal(self, command: CreateDealCommand) -> Deal:
        """Create a deal and have the criteria agent draft its checklist.

        The deal and its criteria commit together: a deal must never exist
        without the checklist both parties are about to confirm.
        """
        self._validate_money(command.amount, command.currency)
        if command.buyer_id == command.seller_id:
            raise ValidationError("the buyer and the seller must be different users")

        deal = Deal(
            buyer_id=command.buyer_id,
            seller_id=command.seller_id,
            title=command.title.strip(),
            description=command.description.strip(),
            amount=command.amount,
            currency=command.currency.upper(),
            state=DealState.DRAFT,
        )
        self._deals.add(deal)
        await self._session.flush()

        drafted = await self._ai.draft_criteria(
            deal=DealContext(
                description=deal.description, amount=deal.amount, currency=deal.currency
            )
        )
        self._deals.add_criteria(deal.id, [criterion.text for criterion in drafted])

        self._audit.append(
            deal_id=deal.id,
            from_state=None,
            to_state=DealState.DRAFT,
            actor=Actor.AI,
            event=TransitionEvent.DEAL_CREATED.value,
            reason=(
                f"deal created; the criteria agent drafted {len(drafted)} acceptance "
                "criteria for both parties to confirm"
            ),
        )
        await self._session.commit()

        logger.info(
            "deal.created",
            deal_id=str(deal.id),
            deal_state=deal.state.value,
            criteria=len(drafted),
        )
        refreshed = await self._deals.get(deal.id)
        if refreshed is None:  # pragma: no cover — it was just committed
            raise DealNotFound("the deal could not be read back after creation")
        return refreshed

    async def confirm_criteria(self, *, deal_id: uuid.UUID, user_id: uuid.UUID) -> Deal:
        """Record one party's confirmation of the whole checklist (FR-2)."""
        deal = await self.get_deal_for_party(deal_id=deal_id, user_id=user_id)
        if deal.state is not DealState.DRAFT:
            raise TransitionGuardFailed(
                f"the acceptance criteria can only be confirmed while the deal is in "
                f"DRAFT; it is {deal.state.value}"
            )

        criteria = await self._deals.list_criteria(deal_id)
        if not criteria:
            raise TransitionGuardFailed("the deal has no acceptance criteria to confirm")

        is_buyer = deal.buyer_id == user_id
        for criterion in criteria:
            if is_buyer:
                criterion.confirmed_by_buyer = True
            else:
                criterion.confirmed_by_seller = True

        party = "buyer" if is_buyer else "seller"
        all_confirmed = all(criterion.is_confirmed for criterion in criteria)
        self._audit.append(
            deal_id=deal.id,
            from_state=deal.state,
            to_state=deal.state,
            actor=Actor.BUYER if is_buyer else Actor.SELLER,
            event="criteria_confirmed",
            reason=(
                f"the {party} confirmed all {len(criteria)} acceptance criteria"
                + ("; the deal is ready to fund" if all_confirmed else "")
            ),
        )
        await self._session.commit()

        logger.info(
            "deal.criteria_confirmed",
            deal_id=str(deal.id),
            party=party,
            all_confirmed=all_confirmed,
        )
        return await self.get_deal_for_party(deal_id=deal_id, user_id=user_id)

    # --- FR-3: funding ----------------------------------------------------

    async def create_order(self, *, deal_id: uuid.UUID, user_id: uuid.UUID) -> OrderCreated:
        """Create the PayPal order the buyer approves in the JS SDK.

        Only the buyer can fund, and only once the checklist is confirmed —
        checked here rather than at capture time, so the buyer is not sent
        through checkout for a deal that cannot be funded.
        """
        deal = await self.get_deal_for_party(deal_id=deal_id, user_id=user_id)
        if deal.buyer_id != user_id:
            raise NotAuthorizedForDeal("only the buyer can fund this deal")
        if deal.state is not DealState.DRAFT:
            raise TransitionGuardFailed(
                f"only a DRAFT deal can be funded; this deal is {deal.state.value}"
            )

        context = deal_transition_context(deal)
        if not context.all_criteria_confirmed:
            raise TransitionGuardFailed(
                "both parties must confirm the acceptance criteria before funding"
            )

        result = await self._paypal.create_order(
            amount=deal.amount,
            currency=deal.currency,
            reference_id=str(deal.id),
            description=deal.title or "Waseet escrow deal",
            request_id=idempotency.order_request_id(deal.id),
        )

        deal.paypal_order_id = result.order_id
        self._audit.append(
            deal_id=deal.id,
            from_state=deal.state,
            to_state=deal.state,
            actor=Actor.BUYER,
            event="order_created",
            reason=f"a PayPal order was created for {deal.amount} {deal.currency}",
            paypal_reference=result.order_id,
        )
        await self._session.commit()

        logger.info("deal.order_created", deal_id=str(deal.id), paypal_order_id=result.order_id)
        return OrderCreated(order_id=result.order_id, approve_url=result.approve_url)

    async def capture_order(
        self, *, deal_id: uuid.UUID, user_id: uuid.UUID, order_id: str | None = None
    ) -> Deal:
        """Capture the approved order into the platform account — "escrow".

        The deal row is locked for the transaction, so a capture racing a
        redelivered capture webhook cannot both move the deal to FUNDED.
        """
        deal = await self._load_locked(deal_id)
        if not deal.is_party(user_id):
            raise NotAuthorizedForDeal("you are not a party to this deal")
        if deal.buyer_id != user_id:
            raise NotAuthorizedForDeal("only the buyer can fund this deal")

        if deal.state is DealState.FUNDED:
            # The webhook, or a retried request, got here first.
            logger.info("deal.capture_already_applied", deal_id=str(deal.id))
            return await self._reload(deal_id)

        target = next_state(
            deal.state, TransitionEvent.PAYMENT_CAPTURED, deal_transition_context(deal)
        )

        resolved_order_id = (order_id or deal.paypal_order_id or "").strip()
        if not resolved_order_id:
            raise ValidationError("no PayPal order exists for this deal yet")
        if deal.paypal_order_id and resolved_order_id != deal.paypal_order_id:
            # The client does not get to nominate a different order.
            raise ValidationError("the order id does not belong to this deal")

        try:
            capture = await self._paypal.capture_order(
                order_id=resolved_order_id,
                request_id=idempotency.capture_request_id(deal.id),
            )
        except PayPalError as exc:
            raise PayPalError(f"the payment could not be captured: {exc.message}") from exc

        if not capture.is_completed:
            raise PayPalError(
                f"PayPal did not complete the capture (status {capture.status or 'unknown'})"
            )
        if capture.amount != deal.amount or capture.currency != deal.currency:
            # Refuse to hold an amount that is not the agreed one.
            raise PayPalError(
                "the captured amount does not match the deal: captured "
                f"{capture.amount} {capture.currency}, expected "
                f"{deal.amount} {deal.currency}"
            )

        from_state = deal.state
        deal.paypal_order_id = capture.order_id
        deal.paypal_capture_id = capture.capture_id
        deal.state = target

        self._audit.append(
            deal_id=deal.id,
            from_state=from_state,
            to_state=target,
            actor=Actor.BUYER,
            event=TransitionEvent.PAYMENT_CAPTURED.value,
            reason=(
                f"{capture.amount} {capture.currency} was captured into the platform "
                "account and is held in escrow"
            ),
            paypal_reference=capture.capture_id,
        )
        await self._session.commit()

        logger.info(
            "deal.funded",
            deal_id=str(deal.id),
            deal_state=target.value,
            paypal_capture_id=capture.capture_id,
        )
        return await self._reload(deal_id)

    # --- FR-4: deliverable ------------------------------------------------

    async def submit_deliverable(
        self,
        *,
        deal_id: uuid.UUID,
        user_id: uuid.UUID,
        type_: DeliverableType,
        content_ref: str,
        note: str | None = None,
    ) -> Deliverable:
        """Record the seller's submission and move the deal to DELIVERED.

        The content is stored as given and never interpreted here: it is
        untrusted input, and only the verifier reads it — as data.
        """
        deal = await self._load_locked(deal_id)
        if deal.seller_id != user_id:
            raise NotAuthorizedForDeal("only the seller can submit the deliverable")

        content = content_ref.strip()
        if not content:
            raise ValidationError("the deliverable cannot be empty")

        deliverable = self._deliverables.add(
            deal_id=deal.id, type_=type_, content_ref=content, note=note
        )
        await self._session.flush()

        # The deliverable exists as of the flush above, so the guard must
        # see it even though the relationship was loaded before.
        context = replace(deal_transition_context(deal), has_deliverable=True)
        target = next_state(deal.state, TransitionEvent.DELIVERABLE_SUBMITTED, context)

        from_state = deal.state
        deal.state = target
        self._audit.append(
            deal_id=deal.id,
            from_state=from_state,
            to_state=target,
            actor=Actor.SELLER,
            event=TransitionEvent.DELIVERABLE_SUBMITTED.value,
            reason=f"the seller submitted a deliverable of type {type_.value}",
        )
        await self._session.commit()

        logger.info(
            "deal.delivered",
            deal_id=str(deal.id),
            deal_state=target.value,
            deliverable_type=type_.value,
        )
        return deliverable

    # --- FR-7: buyer contest ----------------------------------------------

    async def contest(self, *, deal_id: uuid.UUID, user_id: uuid.UUID, reason: str) -> Deal:
        """The buyer contests, which routes the deal to DISPUTED.

        A contest is deliberately not a judgment call: it always disputes,
        and a human resolves it.
        """
        deal = await self._load_locked(deal_id)
        if deal.buyer_id != user_id:
            raise NotAuthorizedForDeal("only the buyer can contest this deal")

        if deal.state is DealState.DISPUTED:
            return await self._reload(deal_id)

        target = next_state(
            deal.state, TransitionEvent.BUYER_CONTESTED, deal_transition_context(deal)
        )
        from_state = deal.state
        deal.state = target

        stated = reason.strip() or "no reason was given"
        self._audit.append(
            deal_id=deal.id,
            from_state=from_state,
            to_state=target,
            actor=Actor.BUYER,
            event=TransitionEvent.BUYER_CONTESTED.value,
            reason=f"the buyer contested the delivery: {stated}",
            paypal_reference=deal.paypal_capture_id,
        )
        await self._session.commit()

        logger.info("deal.contested", deal_id=str(deal.id), deal_state=target.value)
        return await self._reload(deal_id)

    # --- reads ------------------------------------------------------------

    async def get_deal_for_party(self, *, deal_id: uuid.UUID, user_id: uuid.UUID) -> Deal:
        """Load a deal the user is entitled to see.

        A deal that exists but belongs to someone else is reported as not
        found, so the endpoint does not confirm which deal ids exist.
        """
        deal = await self._deals.get(deal_id)
        if deal is None:
            raise DealNotFound("no such deal")
        if not deal.is_party(user_id):
            raise DealNotFound("no such deal")
        return deal

    async def get_deal_for_reviewer(self, deal_id: uuid.UUID) -> Deal:
        deal = await self._deals.get(deal_id)
        if deal is None:
            raise DealNotFound("no such deal")
        return deal

    async def list_deals(
        self, *, user_id: uuid.UUID, role: Role, state: DealState | None = None
    ) -> list[Deal]:
        """A party sees their own deals; a reviewer sees the dispute queue."""
        if role is Role.REVIEWER:
            deals = await self._deals.list_by_state(state or DealState.DISPUTED)
        else:
            deals = await self._deals.list_for_user(user_id, state=state)
        return list(deals)

    # --- helpers ----------------------------------------------------------

    async def _load_locked(self, deal_id: uuid.UUID) -> Deal:
        deal = await self._deals.get_for_update(deal_id)
        if deal is None:
            raise DealNotFound("no such deal")
        return deal

    async def _reload(self, deal_id: uuid.UUID) -> Deal:
        deal = await self._deals.get(deal_id)
        if deal is None:  # pragma: no cover
            raise DealNotFound("no such deal")
        return deal

    @staticmethod
    def _validate_money(amount: Decimal, currency: str) -> None:
        if currency.upper() not in SUPPORTED_CURRENCIES:
            raise ValidationError(
                f"{currency} is not supported; use one of {', '.join(sorted(SUPPORTED_CURRENCIES))}"
            )
        if amount < MIN_AMOUNT or amount > MAX_AMOUNT:
            raise ValidationError(
                f"the amount must be between {MIN_AMOUNT} and {MAX_AMOUNT} {currency.upper()}"
            )
        if amount != amount.quantize(Decimal("0.01")):
            raise ValidationError("the amount cannot have more than two decimal places")
