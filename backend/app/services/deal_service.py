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
class MilestoneSpec:
    """One milestone the buyer asks for: a slice of the deal with its own
    deliverable and its own acceptance checklist drafted by the AI."""

    title: str
    description: str
    amount: Decimal


@dataclass(frozen=True, slots=True)
class CreateDealCommand:
    buyer_id: uuid.UUID
    seller_id: uuid.UUID
    title: str
    description: str
    amount: Decimal
    currency: str
    # Empty for a simple deal; two or more for a milestone deal, in which
    # case `amount` is the sum of the milestone amounts.
    milestones: tuple[MilestoneSpec, ...] = ()


@dataclass(frozen=True, slots=True)
class OrderCreated:
    order_id: str
    approve_url: str | None


@dataclass(frozen=True, slots=True)
class PayoutView:
    """One payout batch tied to a deal, with its live PayPal status (or the
    reason it could not be read)."""

    source: str
    milestone_id: uuid.UUID | None
    status: object | None  # PayPalGateway.PayoutStatus
    error: str | None


@dataclass(frozen=True, slots=True)
class ActivityEntry:
    """One step of a deal's PayPal money trail, with its live status — the
    order, the capture held in escrow, each release payout, and any refund."""

    kind: str  # order | capture | payout | refund
    label: str
    reference_id: str
    status: str
    amount: Decimal | None
    currency: str | None
    receiver: str | None
    error: str | None


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
        if command.buyer_id == command.seller_id:
            raise ValidationError("the buyer and the seller must be different users")

        if command.milestones:
            return await self._create_milestone_deal(command)

        self._validate_money(command.amount, command.currency)
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

    async def _create_milestone_deal(self, command: CreateDealCommand) -> Deal:
        """A deal split into milestones: fund the whole once, release each
        milestone on its own. The AI drafts a separate checklist per milestone.

        The deal amount is the sum of the milestone amounts — the client's own
        total is ignored so the two can never disagree. Each milestone's
        checklist and the deal commit together, as with a simple deal.
        """
        if len(command.milestones) < 2:
            raise ValidationError("a milestone deal needs at least two milestones")

        currency = command.currency.upper()
        total = Decimal("0.00")
        for spec in command.milestones:
            if not spec.title.strip():
                raise ValidationError("every milestone needs a title")
            if spec.amount != spec.amount.quantize(Decimal("0.01")):
                raise ValidationError("a milestone amount cannot have more than two decimals")
            if spec.amount < MIN_AMOUNT:
                raise ValidationError(
                    f"each milestone must be at least {MIN_AMOUNT} {currency}"
                )
            total += spec.amount
        # The summed total is the deal amount, and it must clear the same
        # bounds a simple deal does.
        self._validate_money(total, currency)

        deal = Deal(
            buyer_id=command.buyer_id,
            seller_id=command.seller_id,
            title=command.title.strip(),
            description=command.description.strip(),
            amount=total,
            currency=currency,
            state=DealState.DRAFT,
        )
        self._deals.add(deal)
        await self._session.flush()

        total_criteria = 0
        for position, spec in enumerate(command.milestones):
            milestone = self._deals.add_milestone(
                deal_id=deal.id,
                position=position,
                title=spec.title.strip(),
                description=spec.description.strip(),
                amount=spec.amount,
            )
            await self._session.flush()
            drafted = await self._ai.draft_criteria(
                deal=DealContext(
                    description=(
                        f"Milestone '{spec.title.strip()}' of a larger deal "
                        f"({deal.description}): {spec.description.strip()}"
                    ),
                    amount=spec.amount,
                    currency=currency,
                )
            )
            self._deals.add_milestone_criteria(
                deal.id, milestone.id, [criterion.text for criterion in drafted]
            )
            total_criteria += len(drafted)

        self._audit.append(
            deal_id=deal.id,
            from_state=None,
            to_state=DealState.DRAFT,
            actor=Actor.AI,
            event=TransitionEvent.DEAL_CREATED.value,
            reason=(
                f"milestone deal created with {len(command.milestones)} milestones; the "
                f"criteria agent drafted {total_criteria} acceptance criteria across them "
                "for both parties to confirm"
            ),
        )
        await self._session.commit()

        logger.info(
            "deal.created",
            deal_id=str(deal.id),
            deal_state=deal.state.value,
            milestones=len(command.milestones),
            criteria=total_criteria,
        )
        refreshed = await self._deals.get(deal.id)
        if refreshed is None:  # pragma: no cover
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

        # A milestone deal is funded once, for the whole amount; each
        # milestone's own slice becomes FUNDED and can then be delivered and
        # released independently.
        for milestone in deal.milestones:
            if milestone.state is DealState.DRAFT:
                milestone.state = next_state(
                    milestone.state,
                    TransitionEvent.PAYMENT_CAPTURED,
                    replace(
                        deal_transition_context(deal),
                        criteria_count=1,
                        all_criteria_confirmed=True,
                        has_capture=True,
                    ),
                )

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

    async def get_payouts(
        self, *, deal_id: uuid.UUID, user_id: uuid.UUID, is_reviewer: bool = False
    ) -> list[PayoutView]:
        """Live PayPal status for every payout this deal has made — the whole
        deal's release, or each released milestone's slice.

        Each batch is read from PayPal independently; one that cannot be read
        is reported as an error on its own row rather than failing the lot.
        """
        deal = (
            await self.get_deal_for_reviewer(deal_id)
            if is_reviewer
            else await self.get_deal_for_party(deal_id=deal_id, user_id=user_id)
        )
        return await self._payout_views(deal)

    async def get_paypal_activity(
        self, *, deal_id: uuid.UUID, user_id: uuid.UUID, is_reviewer: bool = False
    ) -> list[ActivityEntry]:
        """The deal's full PayPal money trail, each step read live: the order,
        the capture held in escrow, every release payout, and any refund.

        Each reference is read independently; one that cannot be read becomes
        an error on its own row rather than failing the whole trail.
        """
        deal = (
            await self.get_deal_for_reviewer(deal_id)
            if is_reviewer
            else await self.get_deal_for_party(deal_id=deal_id, user_id=user_id)
        )

        entries: list[ActivityEntry] = []

        async def add_reference(kind: str, label: str, ref: str | None, reader) -> None:
            if not ref:
                return
            try:
                status = await reader(ref)
                entries.append(
                    ActivityEntry(
                        kind=kind,
                        label=label,
                        reference_id=status.reference_id,
                        status=status.status,
                        amount=status.amount,
                        currency=status.currency,
                        receiver=None,
                        error=None,
                    )
                )
            except PayPalError as exc:
                entries.append(
                    ActivityEntry(kind, label, ref, "", None, None, None, exc.message)
                )

        await add_reference(
            "order", "order", deal.paypal_order_id, lambda r: self._paypal.get_order_status(order_id=r)
        )
        await add_reference(
            "capture",
            "capture",
            deal.paypal_capture_id,
            lambda r: self._paypal.get_capture_status(capture_id=r),
        )

        # Payouts carry a receiver, so they are mapped from the richer view.
        for view in await self._payout_views(deal):
            if view.status is not None:
                receiver = view.status.items[0].receiver if view.status.items else None
                entries.append(
                    ActivityEntry(
                        kind="payout",
                        label=view.source,
                        reference_id=view.status.payout_batch_id,
                        status=view.status.batch_status,
                        amount=view.status.amount,
                        currency=view.status.currency,
                        receiver=receiver,
                        error=None,
                    )
                )
            else:
                entries.append(
                    ActivityEntry("payout", view.source, "", "", None, None, None, view.error)
                )

        await add_reference(
            "refund",
            "refund",
            deal.refund_id,
            lambda r: self._paypal.get_refund_status(refund_id=r),
        )
        return entries

    async def _payout_views(self, deal: Deal) -> list[PayoutView]:
        """The payout batches on a deal, with live status — shared by the
        payouts endpoint and the fuller activity trail."""
        targets: list[tuple[str, uuid.UUID | None, str]] = []
        # On a milestone deal the milestones own the payouts; the deal-level
        # payout_batch_id is only a side effect of the last release, so it is
        # not listed again here.
        if deal.payout_batch_id and not deal.milestones:
            targets.append(("deal", None, deal.payout_batch_id))
        for milestone in deal.milestones:
            if milestone.payout_batch_id:
                targets.append((milestone.title, milestone.id, milestone.payout_batch_id))

        views: list[PayoutView] = []
        for source, milestone_id, batch_id in targets:
            try:
                status = await self._paypal.get_payout_status(payout_batch_id=batch_id)
                views.append(PayoutView(source, milestone_id, status, None))
            except PayPalError as exc:
                views.append(PayoutView(source, milestone_id, None, exc.message))
        return views

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
