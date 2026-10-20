"""The decision policy — the gate between the agent's judgment and money.

Deliberately *not* an LLM. The verifier agent can be as smart as it likes
about judging the work; whether that judgment is allowed to move money
follows fixed, auditable rules that a unit test can pin down.

The rule, from the SRS and the Agentic Workflow doc:

    PASS and confidence >= threshold  ->  AUTO_RELEASE
    everything else                   ->  DISPUTE

"Everything else" is load-bearing. A fail, a low-confidence pass, an
inconclusive or malformed model response, a verdict that contradicts its own
per-criterion results, or a buyer contest all land in DISPUTE. The agent can
never auto-release under uncertainty — it fails safe, not open.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.enums import DealState, PolicyOutcome, TransitionEvent, Verdict

DEFAULT_CONFIDENCE_THRESHOLD = Decimal("0.8")


@dataclass(frozen=True, slots=True)
class VerificationOutcome:
    """The verifier agent's result, already schema-validated.

    `verdict` is INCONCLUSIVE when the model output was malformed, timed
    out, or could not be parsed — the policy treats that exactly like any
    other non-confident result.
    """

    verdict: Verdict
    confidence: Decimal
    failed_criteria_count: int = 0
    buyer_contested: bool = False


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    outcome: PolicyOutcome
    event: TransitionEvent
    reason: str

    @property
    def auto_releases(self) -> bool:
        return self.outcome is PolicyOutcome.AUTO_RELEASE


def decide(
    outcome: VerificationOutcome,
    threshold: Decimal = DEFAULT_CONFIDENCE_THRESHOLD,
) -> PolicyDecision:
    """Map a verification outcome onto auto-release or dispute.

    Pure: same input, same decision, every time. The returned `event` is
    what the caller hands to the state machine, and `reason` is what lands
    in the audit log.
    """
    if outcome.buyer_contested:
        return _dispute("the buyer contested the delivery")

    if outcome.verdict is Verdict.FAIL:
        return _dispute(
            f"the verifier failed the deliverable "
            f"({outcome.failed_criteria_count} criterion/criteria not met)"
        )

    if outcome.verdict is Verdict.INCONCLUSIVE:
        return _dispute("the verifier returned an inconclusive or unusable result")

    # A PASS whose per-criterion results contradict it is not trustworthy.
    # Rejecting it here is the injection-resistance backstop: a deliverable
    # that talks the model into an overall "pass" still cannot move money
    # while any confirmed criterion is marked failed.
    if outcome.failed_criteria_count > 0:
        return _dispute(
            "the verifier returned an overall pass while "
            f"{outcome.failed_criteria_count} criterion/criteria are marked failed"
        )

    if outcome.confidence < threshold:
        return _dispute(
            f"confidence {outcome.confidence} is below the auto-release threshold of {threshold}"
        )

    return PolicyDecision(
        outcome=PolicyOutcome.AUTO_RELEASE,
        event=TransitionEvent.VERIFICATION_PASSED_CONFIDENTLY,
        reason=(
            f"the verifier passed every criterion with confidence "
            f"{outcome.confidence} (>= {threshold})"
        ),
    )


def _dispute(reason: str) -> PolicyDecision:
    return PolicyDecision(
        outcome=PolicyOutcome.DISPUTE,
        event=TransitionEvent.VERIFICATION_NOT_CONFIDENT,
        reason=reason,
    )


def contest_event(state: DealState) -> TransitionEvent:
    """The event a buyer contest raises. Separate from `decide()` because a
    contest can arrive before verification ever runs (FUNDED or DELIVERED).
    """
    del state  # the state machine validates where a contest is allowed
    return TransitionEvent.BUYER_CONTESTED
