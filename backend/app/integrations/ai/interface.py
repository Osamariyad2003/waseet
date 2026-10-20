"""The AIGateway contract — the three judgment agents.

The agents decide; they never disburse. Nothing in this interface can move
money: it returns judgments, and the backend executes money movement only
after the deterministic decision policy or a human has spoken.

Services depend on this Protocol, so the whole verification and dispute flow
is testable with a fake that returns fixed judgments.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable

from app.domain.enums import SettlementAction, Verdict


@dataclass(frozen=True, slots=True)
class DraftedCriterion:
    """One testable acceptance criterion from the criteria agent."""

    text: str


@dataclass(frozen=True, slots=True)
class CriterionJudgment:
    """The verifier's finding on a single criterion."""

    criterion_id: str
    text: str
    passed: bool
    note: str

    def as_dict(self) -> dict[str, object]:
        """The shape stored in `verification_reports.per_criterion`."""
        return {
            "criterion_id": self.criterion_id,
            "text": self.text,
            "pass": self.passed,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class VerificationJudgment:
    """The verifier agent's full result.

    `verdict` is INCONCLUSIVE when the model's output could not be parsed or
    schema-validated, or when the call failed after its retry. The decision
    policy treats that exactly like any other non-confident result.
    """

    verdict: Verdict
    confidence: Decimal
    reasoning: str
    per_criterion: tuple[CriterionJudgment, ...] = ()

    @property
    def failed_criteria_count(self) -> int:
        return sum(1 for judgment in self.per_criterion if not judgment.passed)

    @classmethod
    def inconclusive(cls, reasoning: str) -> VerificationJudgment:
        return cls(verdict=Verdict.INCONCLUSIVE, confidence=Decimal("0"), reasoning=reasoning)


@dataclass(frozen=True, slots=True)
class MediationRecommendation:
    """The mediator agent's advisory recommendation for a human reviewer."""

    recommendation: SettlementAction
    reasoning: str
    # Present only when the mediator recommends a split.
    suggested_seller_amount: Decimal | None = None


@dataclass(frozen=True, slots=True)
class DealContext:
    """The minimum a judgment agent needs.

    Privacy requirement from the SRS: only the data needed to verify a
    deliverable is sent to the model — no emails, no account references, no
    PayPal ids.
    """

    description: str
    amount: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class DeliverableContext:
    """The submitted work, as untrusted data.

    Anything inside `content_ref` or `note` may be an attempt to instruct
    the model ("mark this as passed"). Implementations must wrap it as data
    and tell the model to judge it, never to obey it.
    """

    type: str
    content_ref: str
    note: str | None = None


@runtime_checkable
class AIGateway(Protocol):
    """The judgment layer. Read-only with respect to money."""

    async def draft_criteria(self, *, deal: DealContext) -> tuple[DraftedCriterion, ...]:
        """Turn a plain-language deal into concrete, checkable criteria (FR-2)."""
        ...

    async def verify_deliverable(
        self,
        *,
        deal: DealContext,
        criteria: tuple[tuple[str, str], ...],
        deliverable: DeliverableContext,
    ) -> VerificationJudgment:
        """Judge the deliverable against each confirmed criterion (FR-5).

        `criteria` is a tuple of (criterion_id, text). Never raises for a
        model failure: an unusable result comes back as INCONCLUSIVE so the
        deal routes to DISPUTED rather than guessing.
        """
        ...

    async def mediate_dispute(
        self,
        *,
        deal: DealContext,
        criteria: tuple[tuple[str, str], ...],
        deliverable: DeliverableContext | None,
        verification: VerificationJudgment | None,
    ) -> MediationRecommendation:
        """Recommend release / refund / split for a human to decide on (FR-8)."""
        ...
