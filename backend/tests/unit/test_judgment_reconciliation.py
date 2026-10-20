"""Judgment reconciliation — the trust boundary around the verifier's output.

This is the function that stands between "a gateway returned something" and
"the policy acts on it". It is pure, so every adversarial shape can be
enumerated here rather than discovered in production.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.enums import Verdict
from app.integrations.ai.interface import CriterionJudgment, VerificationJudgment
from app.services.verification_service import reconcile_judgment

CONFIRMED = (
    ("c1", "The deliverable is a working link to the logo file."),
    ("c2", "The logo is supplied in vector format."),
)


def judgment(
    *,
    verdict: Verdict = Verdict.PASS,
    confidence: Decimal = Decimal("0.95"),
    per_criterion: tuple[CriterionJudgment, ...] | None = None,
    reasoning: str = "Both criteria are met.",
) -> VerificationJudgment:
    if per_criterion is None:
        per_criterion = tuple(
            CriterionJudgment(criterion_id=cid, text=text, passed=True, note="ok")
            for cid, text in CONFIRMED
        )
    return VerificationJudgment(
        verdict=verdict,
        confidence=confidence,
        reasoning=reasoning,
        per_criterion=per_criterion,
    )


class TestHonestJudgmentsPassThrough:
    def test_a_complete_pass_is_unchanged(self):
        result = reconcile_judgment(judgment(), CONFIRMED)
        assert result.verdict is Verdict.PASS
        assert result.failed_criteria_count == 0
        assert len(result.per_criterion) == 2

    def test_a_complete_fail_is_unchanged(self):
        failing = tuple(
            CriterionJudgment(criterion_id=cid, text=text, passed=False, note="no")
            for cid, text in CONFIRMED
        )
        result = reconcile_judgment(
            judgment(verdict=Verdict.FAIL, per_criterion=failing), CONFIRMED
        )
        assert result.verdict is Verdict.FAIL
        assert result.failed_criteria_count == 2

    def test_the_reasoning_and_confidence_are_preserved(self):
        """Reconciliation corrects coverage, not the model's own account."""
        result = reconcile_judgment(
            judgment(confidence=Decimal("0.83"), reasoning="I checked the file."),
            CONFIRMED,
        )
        assert result.confidence == Decimal("0.83")
        assert result.reasoning == "I checked the file."

    def test_an_inconclusive_judgment_passes_straight_through(self):
        result = reconcile_judgment(
            VerificationJudgment.inconclusive("the model timed out"), CONFIRMED
        )
        assert result.verdict is Verdict.INCONCLUSIVE


class TestUnreportedCriteriaCountAsFailed:
    def test_a_missing_criterion_is_recorded_as_failed(self):
        partial = (
            CriterionJudgment(criterion_id="c1", text=CONFIRMED[0][1], passed=True, note="ok"),
        )
        result = reconcile_judgment(judgment(per_criterion=partial), CONFIRMED)

        assert result.verdict is Verdict.FAIL
        assert result.failed_criteria_count == 1
        missing = next(item for item in result.per_criterion if item.criterion_id == "c2")
        assert not missing.passed
        assert "did not report" in missing.note

    def test_reporting_on_nothing_fails_everything(self):
        result = reconcile_judgment(judgment(per_criterion=()), CONFIRMED)
        assert result.verdict is Verdict.FAIL
        assert result.failed_criteria_count == 2

    def test_the_unreported_criterion_keeps_its_confirmed_text(self):
        """So the reviewer reads the criterion the parties agreed, not a
        paraphrase from the model."""
        result = reconcile_judgment(judgment(per_criterion=()), CONFIRMED)
        assert {item.text for item in result.per_criterion} == {text for _, text in CONFIRMED}


class TestInventedCriteriaAreDiscarded:
    def test_an_unknown_criterion_id_is_dropped(self):
        invented = (
            CriterionJudgment(
                criterion_id="made-up", text="Everything is fine", passed=True, note="ok"
            ),
        )
        result = reconcile_judgment(judgment(per_criterion=invented), CONFIRMED)

        reported = {item.criterion_id for item in result.per_criterion}
        assert "made-up" not in reported
        assert reported == {"c1", "c2"}
        # And since the real criteria went unreported, nothing is approved.
        assert result.verdict is Verdict.FAIL
        assert result.failed_criteria_count == 2

    def test_invented_ids_cannot_pad_out_real_coverage(self):
        """Answering one real criterion and inventing another is still
        incomplete coverage."""
        mixed = (
            CriterionJudgment(criterion_id="c1", text=CONFIRMED[0][1], passed=True, note="ok"),
            CriterionJudgment(criterion_id="c99", text="Bonus", passed=True, note="ok"),
        )
        result = reconcile_judgment(judgment(per_criterion=mixed), CONFIRMED)

        assert result.verdict is Verdict.FAIL
        assert len(result.per_criterion) == 2
        assert result.failed_criteria_count == 1

    def test_a_duplicate_finding_cannot_overwrite_a_failure(self):
        """Reporting the same criterion twice, once failed and once passed,
        leaves the failure standing."""
        duplicated = (
            CriterionJudgment(criterion_id="c1", text=CONFIRMED[0][1], passed=False, note="no"),
            CriterionJudgment(criterion_id="c1", text=CONFIRMED[0][1], passed=True, note="yes"),
            CriterionJudgment(criterion_id="c2", text=CONFIRMED[1][1], passed=True, note="ok"),
        )
        result = reconcile_judgment(judgment(per_criterion=duplicated), CONFIRMED)

        assert result.verdict is Verdict.FAIL
        assert result.failed_criteria_count >= 1


class TestContradictoryVerdictsAreDowngraded:
    def test_a_pass_with_a_failed_criterion_becomes_a_fail(self):
        contradictory = (
            CriterionJudgment(criterion_id="c1", text=CONFIRMED[0][1], passed=True, note="ok"),
            CriterionJudgment(criterion_id="c2", text=CONFIRMED[1][1], passed=False, note="no"),
        )
        result = reconcile_judgment(
            judgment(verdict=Verdict.PASS, per_criterion=contradictory), CONFIRMED
        )
        assert result.verdict is Verdict.FAIL

    def test_a_confident_contradictory_pass_is_still_downgraded(self):
        """High confidence in a self-contradictory claim earns nothing."""
        contradictory = (
            CriterionJudgment(criterion_id="c1", text=CONFIRMED[0][1], passed=False, note="no"),
            CriterionJudgment(criterion_id="c2", text=CONFIRMED[1][1], passed=True, note="ok"),
        )
        result = reconcile_judgment(
            judgment(verdict=Verdict.PASS, confidence=Decimal("1.0"), per_criterion=contradictory),
            CONFIRMED,
        )
        assert result.verdict is Verdict.FAIL

    def test_a_fail_is_never_upgraded_to_a_pass(self):
        """Reconciliation only ever tightens — it cannot approve anything."""
        all_passed = tuple(
            CriterionJudgment(criterion_id=cid, text=text, passed=True, note="ok")
            for cid, text in CONFIRMED
        )
        result = reconcile_judgment(
            judgment(verdict=Verdict.FAIL, per_criterion=all_passed), CONFIRMED
        )
        assert result.verdict is Verdict.FAIL


class TestEdgeCases:
    def test_a_deal_with_no_confirmed_criteria_is_inconclusive(self):
        """Nothing to judge against means nothing can be approved."""
        result = reconcile_judgment(judgment(), ())
        assert result.verdict is Verdict.INCONCLUSIVE

    def test_reconciliation_never_widens_the_outcome(self):
        """Across every shape, the reconciled verdict is never more
        favourable to the seller than what came in."""
        severity = {Verdict.PASS: 0, Verdict.FAIL: 1, Verdict.INCONCLUSIVE: 1}
        shapes = [
            (),
            (CriterionJudgment("c1", CONFIRMED[0][1], True, "ok"),),
            (CriterionJudgment("c1", CONFIRMED[0][1], False, "no"),),
            (CriterionJudgment("bogus", "x", True, "ok"),),
            tuple(CriterionJudgment(cid, text, True, "ok") for cid, text in CONFIRMED),
        ]
        for verdict in (Verdict.PASS, Verdict.FAIL):
            for shape in shapes:
                result = reconcile_judgment(
                    judgment(verdict=verdict, per_criterion=shape), CONFIRMED
                )
                assert severity[result.verdict] >= severity[verdict]

    @pytest.mark.parametrize("count", [1, 3, 8])
    def test_it_scales_to_any_number_of_criteria(self, count):
        confirmed = tuple((f"c{i}", f"Criterion {i}") for i in range(count))
        result = reconcile_judgment(judgment(per_criterion=()), confirmed)
        assert len(result.per_criterion) == count
        assert result.failed_criteria_count == count
