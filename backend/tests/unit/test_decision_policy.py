"""The decision policy is the gate between AI judgment and money.

Every test here is really one question: can the agent get money moved when
it shouldn't? The answer has to stay no.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.decision_policy import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    PolicyDecision,
    VerificationOutcome,
    decide,
)
from app.domain.enums import PolicyOutcome, TransitionEvent, Verdict


def outcome(**kwargs) -> VerificationOutcome:
    defaults = {
        "verdict": Verdict.PASS,
        "confidence": Decimal("0.95"),
        "failed_criteria_count": 0,
        "buyer_contested": False,
    }
    return VerificationOutcome(**{**defaults, **kwargs})


class TestAutoRelease:
    def test_confident_pass_auto_releases(self):
        decision = decide(outcome())
        assert decision.outcome is PolicyOutcome.AUTO_RELEASE
        assert decision.auto_releases
        assert decision.event is TransitionEvent.VERIFICATION_PASSED_CONFIDENTLY

    def test_confidence_exactly_at_the_threshold_releases(self):
        """The gate is >=, so 0.8 at a 0.8 threshold is a release."""
        decision = decide(outcome(confidence=Decimal("0.8")), threshold=Decimal("0.8"))
        assert decision.auto_releases

    def test_the_default_threshold_is_the_documented_one(self):
        assert DEFAULT_CONFIDENCE_THRESHOLD == Decimal("0.8")

    def test_the_reason_records_the_confidence_and_threshold(self):
        decision = decide(outcome(confidence=Decimal("0.91")), threshold=Decimal("0.8"))
        assert "0.91" in decision.reason
        assert "0.8" in decision.reason


class TestFailsSafeNotOpen:
    def test_a_fail_disputes(self):
        decision = decide(outcome(verdict=Verdict.FAIL, failed_criteria_count=2))
        assert decision.outcome is PolicyOutcome.DISPUTE
        assert decision.event is TransitionEvent.VERIFICATION_NOT_CONFIDENT

    def test_a_confident_fail_still_disputes(self):
        """High confidence in a FAIL must never be read as permission to pay."""
        decision = decide(outcome(verdict=Verdict.FAIL, confidence=Decimal("1.0")))
        assert not decision.auto_releases

    def test_low_confidence_pass_disputes(self):
        decision = decide(outcome(confidence=Decimal("0.79")), threshold=Decimal("0.8"))
        assert not decision.auto_releases
        assert "below the auto-release threshold" in decision.reason

    def test_inconclusive_disputes(self):
        """Malformed or unparseable model output arrives here as INCONCLUSIVE."""
        decision = decide(outcome(verdict=Verdict.INCONCLUSIVE, confidence=Decimal("0.99")))
        assert not decision.auto_releases
        assert "inconclusive" in decision.reason

    def test_buyer_contest_disputes_regardless_of_a_perfect_verdict(self):
        decision = decide(outcome(confidence=Decimal("1.0"), buyer_contested=True))
        assert not decision.auto_releases
        assert "contested" in decision.reason

    def test_contest_takes_priority_over_everything_else(self):
        decision = decide(outcome(verdict=Verdict.FAIL, buyer_contested=True))
        assert "contested" in decision.reason

    def test_pass_contradicted_by_failed_criteria_disputes(self):
        """Injection backstop: an overall 'pass' cannot override a failed criterion."""
        decision = decide(outcome(confidence=Decimal("0.99"), failed_criteria_count=1))
        assert not decision.auto_releases
        assert "marked failed" in decision.reason

    def test_zero_confidence_disputes(self):
        assert not decide(outcome(confidence=Decimal("0"))).auto_releases

    @pytest.mark.parametrize(
        "confidence", [Decimal("0"), Decimal("0.5"), Decimal("0.799"), Decimal("0.7999")]
    )
    def test_nothing_under_the_threshold_releases(self, confidence):
        assert not decide(outcome(confidence=confidence), threshold=Decimal("0.8")).auto_releases


class TestExhaustiveness:
    @pytest.mark.parametrize("verdict", list(Verdict))
    @pytest.mark.parametrize("confidence", [Decimal("0.0"), Decimal("0.8"), Decimal("1.0")])
    @pytest.mark.parametrize("failed", [0, 1])
    @pytest.mark.parametrize("contested", [False, True])
    def test_only_one_combination_releases(self, verdict, confidence, failed, contested):
        """Across the whole input space, exactly one shape of input pays out:
        a PASS, at or above threshold, no failed criteria, no contest."""
        decision = decide(
            outcome(
                verdict=verdict,
                confidence=confidence,
                failed_criteria_count=failed,
                buyer_contested=contested,
            ),
            threshold=Decimal("0.8"),
        )
        should_release = (
            verdict is Verdict.PASS
            and confidence >= Decimal("0.8")
            and failed == 0
            and not contested
        )
        assert decision.auto_releases is should_release

    def test_a_decision_always_carries_a_reason(self):
        """Explainability: nothing reaches the audit log without a reason."""
        for verdict in Verdict:
            decision = decide(outcome(verdict=verdict))
            assert isinstance(decision, PolicyDecision)
            assert decision.reason.strip()

    def test_the_policy_is_pure(self):
        """Same input, same answer — this is why the gate is code, not a model."""
        given = outcome(confidence=Decimal("0.85"))
        assert decide(given) == decide(given)

    def test_a_dispute_never_produces_a_release_event(self):
        for verdict in (Verdict.FAIL, Verdict.INCONCLUSIVE):
            decision = decide(outcome(verdict=verdict))
            assert decision.event is TransitionEvent.VERIFICATION_NOT_CONFIDENT
