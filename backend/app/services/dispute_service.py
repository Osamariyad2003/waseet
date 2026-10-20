"""Disputes: the mediator's recommendation and the human's decision (FR-8, FR-9).

The mediator is advisory. It reads the deal, the deliverable and the
verification, and recommends release / refund / split with reasoning. The
reviewer reads that and decides, and only the reviewer's decision moves
money — through the settlement service, as always.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationError
from app.domain.enums import (
    Actor,
    DealState,
    DecidedBy,
    SettlementAction,
    TransitionEvent,
    Verdict,
)
from app.domain.errors import DealNotFound, NotAuthorizedForDeal, TransitionGuardFailed
from app.integrations.ai.interface import (
    AIGateway,
    MediationRecommendation,
    VerificationJudgment,
)
from app.models.deal import Deal
from app.models.verification import VerificationReport
from app.repositories.audit_repo import AuditRepository
from app.repositories.deal_repo import DealRepository
from app.repositories.deliverable_repo import DeliverableRepository
from app.repositories.verification_repo import VerificationRepository
from app.services.agent_toolbox import AgentToolbox
from app.services.settlement_service import SettlementOutcome, SettlementService

logger = structlog.get_logger(__name__)

EVENT_BY_ACTION = {
    SettlementAction.RELEASE: TransitionEvent.HUMAN_DECIDED_RELEASE,
    SettlementAction.REFUND: TransitionEvent.HUMAN_DECIDED_REFUND,
    SettlementAction.SPLIT: TransitionEvent.HUMAN_DECIDED_SPLIT,
}


@dataclass(frozen=True, slots=True)
class DisputeResolution:
    deal: Deal
    outcome: SettlementOutcome
    report: VerificationReport


class DisputeService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        deal_repo: DealRepository,
        deliverable_repo: DeliverableRepository,
        verification_repo: VerificationRepository,
        audit_repo: AuditRepository,
        settlement: SettlementService,
        ai: AIGateway,
    ) -> None:
        self._session = session
        self._deals = deal_repo
        self._deliverables = deliverable_repo
        self._verifications = verification_repo
        self._audit = audit_repo
        self._settlement = settlement
        self._ai = ai

    async def get_recommendation(self, deal_id: uuid.UUID) -> MediationRecommendation:
        """Run the mediator agent for a reviewer. Read-only: produces words,
        not money."""
        deal = await self._deals.get(deal_id)
        if deal is None:
            raise DealNotFound("no such deal")
        if deal.state is not DealState.DISPUTED:
            raise TransitionGuardFailed(
                f"a recommendation is only produced for a DISPUTED deal; this deal "
                f"is {deal.state.value}"
            )

        report = await self._verifications.get_latest_ai(deal.id)

        # The mediator reads through the same read-only toolbox as the
        # verifier: the same three reads, the same narrow fields, and no
        # capability to act on what it reads.
        toolbox = AgentToolbox(
            deal_id=deal.id,
            deal_repo=self._deals,
            deliverable_repo=self._deliverables,
        )
        recommendation = await self._ai.mediate_dispute(
            deal=await toolbox.read_deal(),
            criteria=await toolbox.read_criteria(),
            deliverable=await toolbox.read_deliverable(),
            verification=_judgment_from(report),
        )

        logger.info(
            "dispute.recommendation",
            deal_id=str(deal.id),
            recommendation=recommendation.recommendation.value,
        )
        return recommendation

    async def resolve(
        self,
        *,
        deal_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        is_reviewer: bool,
        action: SettlementAction,
        reasoning: str,
        seller_amount: Decimal | None = None,
    ) -> DisputeResolution:
        """Execute the reviewer's decision (FR-8, FR-9).

        The decision, the money movement, the human verification report and
        the audit entry all commit together.
        """
        if not is_reviewer:
            raise NotAuthorizedForDeal("only a reviewer can resolve a dispute")

        stated = reasoning.strip()
        if not stated:
            # Explainability is not optional: every settlement is backed by
            # stored, human-readable reasoning.
            raise ValidationError("a dispute decision must include the reviewer's reasoning")

        deal = await self._deals.get_for_update(deal_id)
        if deal is None:
            raise DealNotFound("no such deal")
        if deal.state is not DealState.DISPUTED:
            raise TransitionGuardFailed(
                f"only a DISPUTED deal can be resolved; this deal is {deal.state.value}"
            )

        if action is SettlementAction.SPLIT and seller_amount is None:
            raise ValidationError("a split decision must state the amount to pay the seller")
        if action is not SettlementAction.SPLIT and seller_amount is not None:
            raise ValidationError(f"a {action.value} decision cannot carry a seller amount")

        event = EVENT_BY_ACTION[action]

        # The reviewer's decision is itself a verification report, recorded
        # as decided_by=human so the trail distinguishes it from the AI's.
        report = self._verifications.add(
            deal_id=deal.id,
            deliverable_id=None,
            verdict=_verdict_for(action),
            confidence=Decimal("1.000"),
            reasoning=stated,
            per_criterion=[],
            decided_by=DecidedBy.HUMAN,
            recommendation=action.value,
        )
        await self._session.flush()

        outcome = await self._settlement.settle(
            deal=deal,
            action=action,
            event=event,
            actor=Actor.REVIEWER,
            reason=f"the reviewer decided to {action.value}: {stated}",
            seller_amount=seller_amount,
        )
        await self._session.commit()

        logger.info(
            "dispute.resolved",
            deal_id=str(deal.id),
            action=action.value,
            deal_state=outcome.state.value,
            reviewer_id=str(reviewer_id),
        )
        final = await self._deals.get(deal_id)
        return DisputeResolution(deal=final or deal, outcome=outcome, report=report)


def _verdict_for(action: SettlementAction) -> Verdict:
    """How a human decision reads as a verdict on the deliverable."""
    if action is SettlementAction.RELEASE:
        return Verdict.PASS
    if action is SettlementAction.REFUND:
        return Verdict.FAIL
    return Verdict.INCONCLUSIVE  # a split is a partial acceptance


def _judgment_from(report: VerificationReport | None) -> VerificationJudgment | None:
    """Rebuild the gateway's value object from the stored report, so the
    mediator sees what the verifier actually said."""
    if report is None:
        return None
    return VerificationJudgment(
        verdict=report.verdict,
        confidence=report.confidence,
        reasoning=report.reasoning,
        per_criterion=(),
    )
