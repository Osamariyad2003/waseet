"""Per-milestone delivery and verification.

A milestone deal is funded once, for the whole amount; each milestone is then
delivered, verified and released on its own. This service runs that loop for a
single milestone, reusing the exact pieces a whole-deal verification uses — the
read-only agent toolbox, the judgment reconciliation at the trust boundary, the
deterministic decision policy, and the settlement service with its spend
mandate. The only differences are scope (one milestone's checklist, deliverable
and slice) and that the money cap is the deal's *remaining* balance.

The agent still only decides; the settlement service still is the only place a
payout happens; the mandate still caps cumulative releases at the capture.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from decimal import Decimal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.errors import ValidationError
from app.domain.decision_policy import PolicyDecision, VerificationOutcome, decide
from app.domain.enums import (
    Actor,
    DealState,
    DecidedBy,
    DeliverableType,
    PolicyOutcome,
    SettlementAction,
    TransitionEvent,
)
from app.domain.errors import DealNotFound, NotAuthorizedForDeal, TransitionGuardFailed
from app.domain.state_machine import next_state
from app.integrations.ai.interface import AIGateway
from app.integrations.content.interface import ContentFetcher
from app.models.deliverable import Deliverable
from app.models.milestone import Milestone
from app.repositories.audit_repo import AuditRepository
from app.repositories.deal_repo import DealRepository
from app.repositories.deliverable_repo import DeliverableRepository
from app.repositories.verification_repo import VerificationRepository
from app.services.agent_toolbox import AgentToolbox
from app.services.dispute_service import EVENT_BY_ACTION, _verdict_for
from app.services.settlement_service import (
    SettlementOutcome,
    SettlementService,
    deal_transition_context,
)
from app.services.verification_service import reconcile_judgment

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class MilestoneVerificationResult:
    milestone: Milestone
    released: bool
    decision: PolicyDecision


@dataclass(frozen=True, slots=True)
class MilestoneDisputeResolution:
    milestone: Milestone
    outcome: SettlementOutcome


class MilestoneService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        deal_repo: DealRepository,
        deliverable_repo: DeliverableRepository,
        verification_repo: VerificationRepository,
        audit_repo: AuditRepository,
        settlement: SettlementService,
        ai: AIGateway,
        fetcher: ContentFetcher | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._deals = deal_repo
        self._deliverables = deliverable_repo
        self._verifications = verification_repo
        self._audit = audit_repo
        self._settlement = settlement
        self._ai = ai
        self._fetcher = fetcher

    # --- delivery ---------------------------------------------------------

    async def submit_deliverable(
        self,
        *,
        deal_id: uuid.UUID,
        milestone_id: uuid.UUID,
        user_id: uuid.UUID,
        type_: DeliverableType,
        content_ref: str,
        note: str | None = None,
    ) -> Deliverable:
        deal = await self._deals.get_for_update(deal_id)
        if deal is None:
            raise DealNotFound("no such deal")
        if deal.seller_id != user_id:
            raise NotAuthorizedForDeal("only the seller can submit the deliverable")

        milestone = await self._load_milestone(deal_id, milestone_id)
        if milestone.state is not DealState.FUNDED:
            raise TransitionGuardFailed(
                f"a milestone deliverable is submitted while the milestone is FUNDED; "
                f"this milestone is {milestone.state.value}"
            )

        content = content_ref.strip()
        if not content:
            raise ValidationError("the deliverable cannot be empty")

        deliverable = self._deliverables.add(
            deal_id=deal.id,
            milestone_id=milestone.id,
            type_=type_,
            content_ref=content,
            note=note,
        )
        await self._session.flush()

        context = replace(
            deal_transition_context(deal),
            has_capture=True,
            has_deliverable=True,
        )
        milestone.state = next_state(
            milestone.state, TransitionEvent.DELIVERABLE_SUBMITTED, context
        )
        self._audit.append(
            deal_id=deal.id,
            from_state=deal.state,
            to_state=deal.state,
            actor=Actor.SELLER,
            event=TransitionEvent.DELIVERABLE_SUBMITTED.value,
            reason=(
                f"the seller submitted a deliverable of type {type_.value} for milestone "
                f"'{milestone.title}'"
            ),
        )
        await self._session.commit()
        logger.info(
            "milestone.delivered",
            deal_id=str(deal.id),
            milestone_id=str(milestone.id),
            milestone_state=milestone.state.value,
        )
        return deliverable

    # --- verification -----------------------------------------------------

    async def verify(
        self, *, deal_id: uuid.UUID, milestone_id: uuid.UUID, user_id: uuid.UUID
    ) -> MilestoneVerificationResult:
        deal = await self._deals.get_for_update(deal_id)
        if deal is None:
            raise DealNotFound("no such deal")
        if not deal.is_party(user_id):
            raise NotAuthorizedForDeal("you are not a party to this deal")

        milestone = await self._load_milestone(deal_id, milestone_id)
        if milestone.state is not DealState.DELIVERED:
            if milestone.state in {DealState.RELEASED, DealState.DISPUTED, DealState.VERIFYING}:
                existing = await self._verifications.get_latest_for_milestone(milestone.id)
                if existing is not None:
                    return MilestoneVerificationResult(
                        milestone=milestone,
                        released=milestone.state is DealState.RELEASED,
                        decision=decide(
                            VerificationOutcome(
                                verdict=existing.verdict, confidence=existing.confidence
                            ),
                            self._settings.auto_release_confidence_threshold,
                        ),
                    )
            raise TransitionGuardFailed(
                f"verification runs on a DELIVERED milestone; this one is {milestone.state.value}"
            )

        deliverable = await self._deliverables.get_latest_for_milestone(milestone.id)
        if deliverable is None:
            raise TransitionGuardFailed("there is no deliverable to verify for this milestone")

        # 1. VERIFYING, committed before the model call so the UI can show it.
        milestone.state = next_state(
            milestone.state,
            TransitionEvent.VERIFICATION_STARTED,
            replace(deal_transition_context(deal), has_capture=True, has_deliverable=True),
        )
        self._audit.append(
            deal_id=deal.id,
            from_state=deal.state,
            to_state=deal.state,
            actor=Actor.SYSTEM,
            event=TransitionEvent.VERIFICATION_STARTED.value,
            reason=f"the verifier agent is judging milestone '{milestone.title}'",
        )
        await self._session.commit()

        # 2-3. Run the agent through the milestone-scoped read-only toolbox.
        toolbox = AgentToolbox(
            deal_id=deal.id,
            deal_repo=self._deals,
            deliverable_repo=self._deliverables,
            fetcher=self._fetcher,
            milestone_id=milestone.id,
        )
        confirmed = await toolbox.read_criteria()
        agent_deliverable = await toolbox.read_deliverable()
        if agent_deliverable is None:  # pragma: no cover — guarded above
            raise TransitionGuardFailed("there is no deliverable to verify for this milestone")

        raw_judgment = await self._ai.verify_deliverable(
            deal=await toolbox.read_deal(),
            criteria=confirmed,
            deliverable=agent_deliverable,
        )
        judgment = reconcile_judgment(raw_judgment, confirmed)

        # Everything from here commits as one transaction.
        deal = await self._deals.get_for_update(deal_id)
        milestone = await self._load_milestone(deal_id, milestone_id)

        self._verifications.add(
            deal_id=deal.id,
            milestone_id=milestone.id,
            deliverable_id=deliverable.id,
            verdict=judgment.verdict,
            confidence=judgment.confidence,
            reasoning=judgment.reasoning,
            per_criterion=[item.as_dict() for item in judgment.per_criterion],
            decided_by=DecidedBy.AI,
        )
        await self._session.flush()

        decision = decide(
            VerificationOutcome(
                verdict=judgment.verdict,
                confidence=judgment.confidence,
                failed_criteria_count=judgment.failed_criteria_count,
            ),
            self._settings.auto_release_confidence_threshold,
        )
        logger.info(
            "milestone.policy_decided",
            deal_id=str(deal.id),
            milestone_id=str(milestone.id),
            outcome=decision.outcome.value,
            verdict=judgment.verdict.value,
        )

        released = False
        if decision.outcome is PolicyOutcome.AUTO_RELEASE:
            await self._settlement.settle_milestone(
                deal=deal,
                milestone=milestone,
                event=decision.event,
                actor=Actor.AI,
                reason=(
                    f"milestone '{milestone.title}' released: {decision.reason}"
                ),
                context=replace(
                    deal_transition_context(deal),
                    has_capture=True,
                    has_verification_report=True,
                ),
            )
            released = True
        else:
            milestone.state = next_state(
                milestone.state,
                decision.event,
                replace(
                    deal_transition_context(deal),
                    has_capture=True,
                    has_verification_report=True,
                ),
            )
            failed = [item.text for item in judgment.per_criterion if not item.passed]
            detail = f"; unmet: {'; '.join(failed)}" if failed else ""
            self._audit.append(
                deal_id=deal.id,
                from_state=deal.state,
                to_state=deal.state,
                actor=Actor.SYSTEM,
                event=decision.event.value,
                reason=(
                    f"milestone '{milestone.title}' disputed, its slice stays held, because "
                    f"{decision.reason}{detail}"
                ),
                paypal_reference=deal.paypal_capture_id,
            )

        await self._session.commit()
        refreshed = await self._load_milestone(deal_id, milestone_id)
        logger.info(
            "milestone.verification_complete",
            deal_id=str(deal.id),
            milestone_id=str(milestone_id),
            milestone_state=refreshed.state.value,
            released=released,
        )
        return MilestoneVerificationResult(
            milestone=refreshed, released=released, decision=decision
        )

    # --- dispute resolution (reviewer) ------------------------------------

    async def resolve_dispute(
        self,
        *,
        deal_id: uuid.UUID,
        milestone_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        is_reviewer: bool,
        action: SettlementAction,
        reasoning: str,
        seller_amount: Decimal | None = None,
    ) -> MilestoneDisputeResolution:
        """A reviewer resolves one disputed milestone — release, refund or
        split its slice. The decision, the money, the human report and the
        audit entry commit together, exactly as a whole-deal dispute does."""
        if not is_reviewer:
            raise NotAuthorizedForDeal("only a reviewer can resolve a dispute")
        stated = reasoning.strip()
        if not stated:
            raise ValidationError("a dispute decision must include the reviewer's reasoning")
        if action is SettlementAction.SPLIT and seller_amount is None:
            raise ValidationError("a split decision must state the amount to pay the seller")
        if action is not SettlementAction.SPLIT and seller_amount is not None:
            raise ValidationError(f"a {action.value} decision cannot carry a seller amount")

        deal = await self._deals.get_for_update(deal_id)
        if deal is None:
            raise DealNotFound("no such deal")
        milestone = await self._load_milestone(deal_id, milestone_id)
        if milestone.state is not DealState.DISPUTED:
            raise TransitionGuardFailed(
                f"only a DISPUTED milestone can be resolved; this one is {milestone.state.value}"
            )

        # The reviewer's decision is itself a report, recorded as human.
        self._verifications.add(
            deal_id=deal.id,
            milestone_id=milestone.id,
            deliverable_id=None,
            verdict=_verdict_for(action),
            confidence=Decimal("1.000"),
            reasoning=stated,
            per_criterion=[],
            decided_by=DecidedBy.HUMAN,
            recommendation=action.value,
        )
        await self._session.flush()

        outcome = await self._settlement.settle_milestone_dispute(
            deal=deal,
            milestone=milestone,
            action=action,
            event=EVENT_BY_ACTION[action],
            actor=Actor.REVIEWER,
            reason=(
                f"the reviewer decided to {action.value} milestone '{milestone.title}': {stated}"
            ),
            seller_amount=seller_amount,
            context=replace(
                deal_transition_context(deal),
                has_capture=True,
                has_verification_report=True,
            ),
        )
        await self._session.commit()
        refreshed = await self._load_milestone(deal_id, milestone_id)
        logger.info(
            "milestone.dispute_resolved",
            deal_id=str(deal.id),
            milestone_id=str(milestone_id),
            action=action.value,
            reviewer_id=str(reviewer_id),
        )
        return MilestoneDisputeResolution(milestone=refreshed, outcome=outcome)

    # --- helpers ----------------------------------------------------------

    async def _load_milestone(self, deal_id: uuid.UUID, milestone_id: uuid.UUID) -> Milestone:
        milestone = await self._deals.get_milestone_for_update(milestone_id)
        if milestone is None or milestone.deal_id != deal_id:
            raise DealNotFound("no such milestone for this deal")
        return milestone
