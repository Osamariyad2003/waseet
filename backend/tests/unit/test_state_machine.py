"""The state machine is the spine: if these tests are wrong, money moves wrong."""

from __future__ import annotations

import pytest

from app.domain.enums import DealState, TransitionEvent
from app.domain.errors import InvalidTransition, TransitionGuardFailed
from app.domain.state_machine import (
    TERMINAL_STATES,
    TransitionContext,
    allowed_events,
    can_transition,
    is_already_applied,
    is_terminal,
    next_state,
    target_state,
)

# A context where every precondition holds, so a test can isolate one guard.
SATISFIED = TransitionContext(
    criteria_count=3,
    all_criteria_confirmed=True,
    has_capture=True,
    has_deliverable=True,
    has_verification_report=True,
)


class TestHappyPath:
    def test_full_auto_release_path(self):
        state = DealState.DRAFT
        for event, expected in [
            (TransitionEvent.PAYMENT_CAPTURED, DealState.FUNDED),
            (TransitionEvent.DELIVERABLE_SUBMITTED, DealState.DELIVERED),
            (TransitionEvent.VERIFICATION_STARTED, DealState.VERIFYING),
            (TransitionEvent.VERIFICATION_PASSED_CONFIDENTLY, DealState.RELEASED),
        ]:
            state = next_state(state, event, SATISFIED)
            assert state is expected

    def test_dispute_then_human_decision_paths(self):
        for event, expected in [
            (TransitionEvent.HUMAN_DECIDED_RELEASE, DealState.RELEASED),
            (TransitionEvent.HUMAN_DECIDED_REFUND, DealState.REFUNDED),
            (TransitionEvent.HUMAN_DECIDED_SPLIT, DealState.SPLIT),
        ]:
            assert next_state(DealState.DISPUTED, event, SATISFIED) is expected

    def test_verifying_not_confident_goes_to_disputed(self):
        assert (
            next_state(DealState.VERIFYING, TransitionEvent.VERIFICATION_NOT_CONFIDENT, SATISFIED)
            is DealState.DISPUTED
        )

    @pytest.mark.parametrize("state", [DealState.FUNDED, DealState.DELIVERED])
    def test_buyer_contest_from_funded_or_delivered(self, state):
        assert next_state(state, TransitionEvent.BUYER_CONTESTED, SATISFIED) is DealState.DISPUTED


class TestTerminalStates:
    def test_the_three_terminal_states_are_exactly_as_specced(self):
        assert TERMINAL_STATES == {DealState.RELEASED, DealState.REFUNDED, DealState.SPLIT}

    @pytest.mark.parametrize("state", sorted(TERMINAL_STATES))
    def test_terminal_states_have_no_exits(self, state):
        assert allowed_events(state) == frozenset()
        assert is_terminal(state)

    @pytest.mark.parametrize("state", sorted(TERMINAL_STATES))
    @pytest.mark.parametrize("event", list(TransitionEvent))
    def test_no_event_escapes_a_terminal_state(self, state, event):
        with pytest.raises(InvalidTransition):
            next_state(state, event, SATISFIED)

    def test_every_non_terminal_state_has_at_least_one_exit(self):
        for state in DealState:
            if state in TERMINAL_STATES:
                continue
            assert allowed_events(state), f"{state} is a dead end but is not terminal"


class TestGuards:
    def test_funding_requires_confirmed_criteria(self):
        unconfirmed = TransitionContext(criteria_count=2, all_criteria_confirmed=False)
        with pytest.raises(TransitionGuardFailed, match="not confirmed"):
            next_state(DealState.DRAFT, TransitionEvent.PAYMENT_CAPTURED, unconfirmed)

    def test_funding_requires_criteria_to_exist(self):
        with pytest.raises(TransitionGuardFailed, match="no acceptance criteria"):
            next_state(
                DealState.DRAFT,
                TransitionEvent.PAYMENT_CAPTURED,
                TransitionContext(criteria_count=0, all_criteria_confirmed=True),
            )

    def test_release_requires_money_actually_held(self):
        no_capture = TransitionContext(
            has_capture=False, has_deliverable=True, has_verification_report=True
        )
        with pytest.raises(TransitionGuardFailed, match="no captured payment"):
            next_state(
                DealState.VERIFYING, TransitionEvent.VERIFICATION_PASSED_CONFIDENTLY, no_capture
            )

    def test_release_requires_a_stored_verification_report(self):
        """No release without recorded reasoning — the SRS forbids a silent release."""
        no_report = TransitionContext(
            has_capture=True, has_deliverable=True, has_verification_report=False
        )
        with pytest.raises(TransitionGuardFailed, match="no verification report"):
            next_state(
                DealState.VERIFYING, TransitionEvent.VERIFICATION_PASSED_CONFIDENTLY, no_report
            )

    def test_dispute_out_of_verifying_also_requires_a_report(self):
        no_report = TransitionContext(has_capture=True, has_verification_report=False)
        with pytest.raises(TransitionGuardFailed):
            next_state(DealState.VERIFYING, TransitionEvent.VERIFICATION_NOT_CONFIDENT, no_report)

    def test_delivery_requires_a_submitted_deliverable(self):
        with pytest.raises(TransitionGuardFailed, match="no deliverable"):
            next_state(
                DealState.FUNDED,
                TransitionEvent.DELIVERABLE_SUBMITTED,
                TransitionContext(has_capture=True, has_deliverable=False),
            )

    def test_human_decisions_require_held_funds(self):
        empty = TransitionContext(has_capture=False)
        for event in (
            TransitionEvent.HUMAN_DECIDED_RELEASE,
            TransitionEvent.HUMAN_DECIDED_REFUND,
            TransitionEvent.HUMAN_DECIDED_SPLIT,
        ):
            with pytest.raises(TransitionGuardFailed):
                next_state(DealState.DISPUTED, event, empty)

    def test_missing_context_is_treated_as_nothing_satisfied(self):
        with pytest.raises(TransitionGuardFailed):
            next_state(DealState.DRAFT, TransitionEvent.PAYMENT_CAPTURED)

    def test_target_state_ignores_guards(self):
        """Useful for introspection; callers that move money use next_state."""
        assert target_state(DealState.DRAFT, TransitionEvent.PAYMENT_CAPTURED) is DealState.FUNDED


class TestInvalidTransitions:
    @pytest.mark.parametrize(
        ("state", "event"),
        [
            (DealState.DRAFT, TransitionEvent.DELIVERABLE_SUBMITTED),
            (DealState.DRAFT, TransitionEvent.BUYER_CONTESTED),
            (DealState.DRAFT, TransitionEvent.HUMAN_DECIDED_RELEASE),
            (DealState.FUNDED, TransitionEvent.PAYMENT_CAPTURED),
            (DealState.FUNDED, TransitionEvent.VERIFICATION_PASSED_CONFIDENTLY),
            (DealState.DELIVERED, TransitionEvent.VERIFICATION_PASSED_CONFIDENTLY),
            (DealState.VERIFYING, TransitionEvent.BUYER_CONTESTED),
            (DealState.VERIFYING, TransitionEvent.HUMAN_DECIDED_REFUND),
            (DealState.DISPUTED, TransitionEvent.VERIFICATION_PASSED_CONFIDENTLY),
            (DealState.DISPUTED, TransitionEvent.DELIVERABLE_SUBMITTED),
        ],
    )
    def test_undefined_pairs_are_rejected(self, state, event):
        with pytest.raises(InvalidTransition):
            next_state(state, event, SATISFIED)
        assert not can_transition(state, event, SATISFIED)

    def test_a_deal_can_never_leave_verifying_without_the_policy(self):
        """Only the two policy-driven events exit VERIFYING."""
        assert allowed_events(DealState.VERIFYING) == {
            TransitionEvent.VERIFICATION_PASSED_CONFIDENTLY,
            TransitionEvent.VERIFICATION_NOT_CONFIDENT,
        }

    def test_release_is_never_reachable_directly_from_delivered(self):
        """Verification cannot be skipped: DELIVERED has no path to RELEASED."""
        assert DealState.RELEASED not in {
            target_state(DealState.DELIVERED, event)
            for event in allowed_events(DealState.DELIVERED)
        }


class TestIdempotency:
    def test_replayed_capture_is_recognised_as_already_applied(self):
        """A duplicate capture webhook arrives with the deal already FUNDED."""
        assert is_already_applied(DealState.FUNDED, TransitionEvent.PAYMENT_CAPTURED)

    def test_replayed_payout_event_is_recognised_as_already_applied(self):
        assert is_already_applied(
            DealState.RELEASED, TransitionEvent.VERIFICATION_PASSED_CONFIDENTLY
        )
        assert is_already_applied(DealState.RELEASED, TransitionEvent.HUMAN_DECIDED_RELEASE)

    def test_an_unrelated_event_is_not_already_applied(self):
        assert not is_already_applied(DealState.FUNDED, TransitionEvent.HUMAN_DECIDED_REFUND)
        assert not is_already_applied(DealState.DRAFT, TransitionEvent.PAYMENT_CAPTURED)
