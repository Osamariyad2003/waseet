"""Verification and the agentic decision loop (FR-5, FR-6, FR-7).

The loop, exactly as the Agentic Workflow doc specifies it:

  1. move the deal to VERIFYING, so the UI shows progress rather than a
     frozen screen;
  2. run the verifier agent;
  3. schema-validate its output — malformed is treated as inconclusive;
  4. store the report with its reasoning and confidence, whatever the
     outcome;
  5. hand verdict + confidence to the deterministic decision policy;
  6. confident pass -> release through the settlement service;
     anything else -> DISPUTED.

Step 6 is the only place a verification can cause a payout, and it reaches
money only through the settlement service, which re-asks the state machine
and applies the spend mandate. The agent itself never moves money.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.decision_policy import PolicyDecision, VerificationOutcome, decide
from app.domain.enums import (
    Actor,
    DealState,
    DecidedBy,
    PolicyOutcome,
    SettlementAction,
    TransitionEvent,
    Verdict,
)
from app.domain.errors import DealNotFound, NotAuthorizedForDeal, TransitionGuardFailed
from app.domain.preflight import screen
from app.domain.state_machine import next_state
from app.integrations.ai.interface import (
    AIGateway,
    CriterionJudgment,
    VerificationJudgment,
)
from app.integrations.content.interface import ContentFetcher
from app.models.deal import Deal
from app.models.verification import VerificationReport
from app.repositories.audit_repo import AuditRepository
from app.repositories.deal_repo import DealRepository
from app.repositories.deliverable_repo import DeliverableRepository
from app.repositories.verification_repo import VerificationRepository
from app.services.agent_toolbox import AgentToolbox
from app.services.settlement_service import SettlementService, deal_transition_context

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class VerificationResult:
    deal: Deal
    report: VerificationReport
    decision: PolicyDecision
    released: bool


def reconcile_judgment(
    judgment: VerificationJudgment, confirmed: tuple[tuple[str, str], ...]
) -> VerificationJudgment:
    """Reconcile a verifier's judgment against the confirmed checklist.

    The gateway's own parsing does something similar, but a gateway is an
    interchangeable, externally-influenced component — the guarantee has to
    hold at the boundary where the judgment is trusted, not inside the thing
    being trusted. So this runs on every judgment, from any implementation:

      * a finding about a criterion id the parties never confirmed is
        discarded — a model cannot manufacture coverage by answering about
        something that does not exist;
      * a confirmed criterion nobody reported on is recorded as failed,
        because absence of evidence is not evidence of a pass;
      * an overall PASS that contradicts its own findings is downgraded to
        FAIL, so the stored report cannot say "approved" while listing an
        unmet criterion.

    Pure, so the whole table of adversarial shapes is unit-testable.
    """
    if not confirmed:
        return VerificationJudgment.inconclusive(
            "the deal has no confirmed acceptance criteria to judge against"
        )
    if judgment.verdict is Verdict.INCONCLUSIVE:
        return judgment

    texts = dict(confirmed)
    known = [item for item in judgment.per_criterion if item.criterion_id in texts]

    reported = {item.criterion_id for item in known}
    unreported = tuple(
        CriterionJudgment(
            criterion_id=criterion_id,
            text=text,
            passed=False,
            note="the verifier did not report on this criterion",
        )
        for criterion_id, text in confirmed
        if criterion_id not in reported
    )

    per_criterion = tuple(known) + unreported
    verdict = judgment.verdict
    if verdict is Verdict.PASS and any(not item.passed for item in per_criterion):
        verdict = Verdict.FAIL

    return VerificationJudgment(
        verdict=verdict,
        confidence=judgment.confidence,
        reasoning=judgment.reasoning,
        per_criterion=per_criterion,
    )


class VerificationService:
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

    async def verify(self, *, deal_id: uuid.UUID, user_id: uuid.UUID) -> VerificationResult:
        deal = await self._deals.get_for_update(deal_id)
        if deal is None:
            raise DealNotFound("no such deal")
        if not deal.is_party(user_id):
            raise NotAuthorizedForDeal("you are not a party to this deal")

        if deal.state is not DealState.DELIVERED:
            # Re-running a step the deal is already past is a no-op, not an
            # error: the workflow resumes from the deal's state.
            if deal.state in {DealState.RELEASED, DealState.DISPUTED, DealState.VERIFYING}:
                existing = await self._verifications.get_latest(deal.id)
                if existing is not None:
                    logger.info(
                        "verification.already_run",
                        deal_id=str(deal.id),
                        deal_state=deal.state.value,
                    )
                    return VerificationResult(
                        deal=deal,
                        report=existing,
                        decision=decide(
                            VerificationOutcome(
                                verdict=existing.verdict, confidence=existing.confidence
                            ),
                            self._settings.auto_release_confidence_threshold,
                        ),
                        released=deal.state is DealState.RELEASED,
                    )
            raise TransitionGuardFailed(
                f"verification runs on a DELIVERED deal; this deal is {deal.state.value}"
            )

        deliverable = await self._deliverables.get_latest(deal.id)
        if deliverable is None:
            raise TransitionGuardFailed("there is no deliverable to verify")

        criteria = await self._deals.list_criteria(deal.id)

        # 0. Pre-flight intake: a read-only, deterministic screen for injection,
        # off-platform circumvention and corrupt payloads, before the submission
        # reaches the verifier. A REJECT routes to a human (via an inconclusive
        # judgment) and the model is never called on a hostile payload.
        intake = screen(
            deal_id=str(deal.id),
            agreement_summary=deal.description,
            deliverable_type=deliverable.type.value,
            content_ref=deliverable.content_ref,
            note=deliverable.note,
        )
        logger.info(
            "verification.intake_screened",
            deal_id=str(deal.id),
            intake_status=intake.status.value,
            risk_score=intake.risk_score,
            injection_detected=intake.injection_detected,
            off_platform_leakage=intake.off_platform_leakage,
        )

        # 1. VERIFYING, committed before the model call so the UI can show it.
        verifying_state = next_state(
            deal.state, TransitionEvent.VERIFICATION_STARTED, deal_transition_context(deal)
        )
        from_state = deal.state
        deal.state = verifying_state
        self._audit.append(
            deal_id=deal.id,
            from_state=from_state,
            to_state=verifying_state,
            actor=Actor.SYSTEM,
            event=TransitionEvent.VERIFICATION_STARTED.value,
            reason=(
                f"pre-flight intake {intake.status.value} (risk {intake.risk_score:.2f}); "
                f"the verifier agent is judging the deliverable against "
                f"{len(criteria)} confirmed criteria"
                if intake.proceed_to_verifier
                else intake.summary()
            ),
        )
        await self._session.commit()
        logger.info("verification.started", deal_id=str(deal.id), criteria=len(criteria))

        if not intake.proceed_to_verifier:
            # The intake rejected a hostile or corrupt payload. Do not spend a
            # model call on it; hand it to a human as an inconclusive judgment,
            # which the deterministic policy disputes. The findings are the
            # reasoning, so the reviewer sees exactly what was caught.
            judgment = VerificationJudgment.inconclusive(intake.summary())
        else:
            # 2-3. Run the agent. Its whole view of the deal comes through the
            # read-only toolbox: three reads, each returning only the fields the
            # judgment needs. It never raises — an unusable result arrives as
            # INCONCLUSIVE, which the policy disputes.
            toolbox = AgentToolbox(
                deal_id=deal.id,
                deal_repo=self._deals,
                deliverable_repo=self._deliverables,
                fetcher=self._fetcher,
            )
            agent_deliverable = await toolbox.read_deliverable()
            if agent_deliverable is None:  # pragma: no cover — guarded above
                raise TransitionGuardFailed("there is no deliverable to verify")

            confirmed = await toolbox.read_criteria()
            raw_judgment = await self._ai.verify_deliverable(
                deal=await toolbox.read_deal(),
                criteria=confirmed,
                deliverable=agent_deliverable,
            )

            # Reconcile the judgment against the confirmed checklist before it
            # is allowed anywhere near the policy. This is the trust boundary:
            # whatever the gateway returns, only findings about criteria both
            # parties confirmed count, and a criterion nobody reported on is
            # not an approved one.
            judgment = reconcile_judgment(raw_judgment, confirmed)

        # Everything from here commits as one transaction: the report, the
        # policy's state change, the money movement and the audit entries.
        deal = await self._deals.get_for_update(deal_id)
        if deal is None:  # pragma: no cover
            raise DealNotFound("no such deal")

        # 4. Store the reasoning whatever the outcome.
        report = self._verifications.add(
            deal_id=deal.id,
            deliverable_id=deliverable.id,
            verdict=judgment.verdict,
            confidence=judgment.confidence,
            reasoning=judgment.reasoning,
            per_criterion=[judgment_item.as_dict() for judgment_item in judgment.per_criterion],
            decided_by=DecidedBy.AI,
            intake=intake.to_dict(),
        )
        await self._session.flush()

        # 5. The deterministic gate.
        decision = decide(
            VerificationOutcome(
                verdict=judgment.verdict,
                confidence=judgment.confidence,
                failed_criteria_count=judgment.failed_criteria_count,
            ),
            self._settings.auto_release_confidence_threshold,
        )
        logger.info(
            "verification.policy_decided",
            deal_id=str(deal.id),
            outcome=decision.outcome.value,
            verdict=judgment.verdict.value,
            confidence=str(judgment.confidence),
        )

        # 6. Settle or dispute.
        released = False
        if decision.outcome is PolicyOutcome.AUTO_RELEASE:
            await self._settlement.settle(
                deal=deal,
                action=SettlementAction.RELEASE,
                event=decision.event,
                actor=Actor.AI,
                reason=decision.reason,
                # The report was flushed moments ago in this same
                # transaction, so the guard has to be told it exists.
                context=replace(deal_transition_context(deal), has_verification_report=True),
            )
            released = True
        else:
            self._move_to_disputed(deal, judgment, decision)

        await self._session.commit()

        final = await self._deals.get(deal_id)
        logger.info(
            "verification.complete",
            deal_id=str(deal_id),
            deal_state=final.state.value if final else None,
            released=released,
        )
        return VerificationResult(
            deal=final or deal, report=report, decision=decision, released=released
        )

    def _move_to_disputed(
        self, deal: Deal, judgment: VerificationJudgment, decision: PolicyDecision
    ) -> None:
        """Fail safe, not open: hold the funds and open a dispute."""
        context = replace(deal_transition_context(deal), has_verification_report=True)
        target = next_state(deal.state, decision.event, context)
        from_state = deal.state
        deal.state = target

        failed = [item.text for item in judgment.per_criterion if not item.passed]
        detail = f"; unmet criteria: {'; '.join(failed)}" if failed else ""
        self._audit.append(
            deal_id=deal.id,
            from_state=from_state,
            to_state=target,
            actor=Actor.SYSTEM,
            event=decision.event.value,
            reason=(f"funds are held and a dispute is opened because {decision.reason}{detail}"),
            paypal_reference=deal.paypal_capture_id,
        )

    async def get_latest_report(
        self, *, deal_id: uuid.UUID, user_id: uuid.UUID
    ) -> VerificationReport | None:
        deal = await self._deals.get(deal_id)
        if deal is None or not deal.is_party(user_id):
            raise DealNotFound("no such deal")
        return await self._verifications.get_latest(deal_id)
