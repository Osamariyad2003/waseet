"""The escrow state machine — the single place a deal's state change is decided.

No service mutates `deal.state` directly; every change goes through
`next_state()`, which refuses an undefined transition and refuses a defined
transition whose guard is not satisfied.

Transition table (SRS "Escrow lifecycle"):

    DRAFT      --payment_captured-------------> FUNDED
    FUNDED     --deliverable_submitted--------> DELIVERED
    DELIVERED  --verification_started---------> VERIFYING
    VERIFYING  --verification_passed_confidently--> RELEASED   (terminal)
    VERIFYING  --verification_not_confident----> DISPUTED
    FUNDED     --buyer_contested--------------> DISPUTED
    DELIVERED  --buyer_contested--------------> DISPUTED
    DISPUTED   --human_decided_release--------> RELEASED   (terminal)
    DISPUTED   --human_decided_refund---------> REFUNDED   (terminal)
    DISPUTED   --human_decided_split----------> SPLIT      (terminal)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import MappingProxyType

from app.domain.enums import DealState, TransitionEvent
from app.domain.errors import InvalidTransition, TransitionGuardFailed

TERMINAL_STATES: frozenset[DealState] = frozenset(
    {DealState.RELEASED, DealState.REFUNDED, DealState.SPLIT}
)

INITIAL_STATE: DealState = DealState.DRAFT


@dataclass(frozen=True, slots=True)
class TransitionContext:
    """The facts a guard may inspect.

    Services assemble this from the deal aggregate. Defaults are permissive
    only where the fact is irrelevant to the transition being attempted —
    each guard names what it requires.
    """

    criteria_count: int = 0
    all_criteria_confirmed: bool = False
    has_capture: bool = False
    has_deliverable: bool = False
    has_verification_report: bool = False


@dataclass(frozen=True, slots=True)
class _Transition:
    target: DealState
    guard: Callable[[TransitionContext], str | None] | None = None
    """Returns None when satisfied, or a human-readable reason when not."""


# --- Guards ----------------------------------------------------------------
# Each guard is a pure predicate over TransitionContext and returns the
# reason it blocked, so the error message explains itself.


def _guard_fundable(ctx: TransitionContext) -> str | None:
    """FR-2: both parties confirm the acceptance checklist before funding."""
    if ctx.criteria_count == 0:
        return "the deal has no acceptance criteria"
    if not ctx.all_criteria_confirmed:
        return "the acceptance criteria are not confirmed by both parties"
    return None


def _guard_has_capture(ctx: TransitionContext) -> str | None:
    """Nothing downstream of funding is valid without money actually held."""
    if not ctx.has_capture:
        return "no captured payment is held in escrow for this deal"
    return None


def _guard_deliverable_submitted(ctx: TransitionContext) -> str | None:
    if not ctx.has_capture:
        return "no captured payment is held in escrow for this deal"
    if not ctx.has_deliverable:
        return "no deliverable has been submitted"
    return None


def _guard_settle_after_verification(ctx: TransitionContext) -> str | None:
    """A release or dispute out of VERIFYING must be backed by a stored report."""
    if not ctx.has_capture:
        return "no captured payment is held in escrow for this deal"
    if not ctx.has_verification_report:
        return "no verification report has been stored for this deal"
    return None


# --- Transition table ------------------------------------------------------

_TRANSITIONS: dict[DealState, dict[TransitionEvent, _Transition]] = {
    DealState.DRAFT: {
        TransitionEvent.PAYMENT_CAPTURED: _Transition(DealState.FUNDED, _guard_fundable),
    },
    DealState.FUNDED: {
        TransitionEvent.DELIVERABLE_SUBMITTED: _Transition(
            DealState.DELIVERED, _guard_deliverable_submitted
        ),
        TransitionEvent.BUYER_CONTESTED: _Transition(DealState.DISPUTED, _guard_has_capture),
    },
    DealState.DELIVERED: {
        TransitionEvent.VERIFICATION_STARTED: _Transition(
            DealState.VERIFYING, _guard_deliverable_submitted
        ),
        TransitionEvent.BUYER_CONTESTED: _Transition(DealState.DISPUTED, _guard_has_capture),
    },
    DealState.VERIFYING: {
        TransitionEvent.VERIFICATION_PASSED_CONFIDENTLY: _Transition(
            DealState.RELEASED, _guard_settle_after_verification
        ),
        TransitionEvent.VERIFICATION_NOT_CONFIDENT: _Transition(
            DealState.DISPUTED, _guard_settle_after_verification
        ),
    },
    DealState.DISPUTED: {
        TransitionEvent.HUMAN_DECIDED_RELEASE: _Transition(DealState.RELEASED, _guard_has_capture),
        TransitionEvent.HUMAN_DECIDED_REFUND: _Transition(DealState.REFUNDED, _guard_has_capture),
        TransitionEvent.HUMAN_DECIDED_SPLIT: _Transition(DealState.SPLIT, _guard_has_capture),
    },
    # Terminal states deliberately have no exits.
    DealState.RELEASED: {},
    DealState.REFUNDED: {},
    DealState.SPLIT: {},
}

TRANSITIONS = MappingProxyType(_TRANSITIONS)


# --- Public API ------------------------------------------------------------


def is_terminal(state: DealState) -> bool:
    return state in TERMINAL_STATES


def allowed_events(state: DealState) -> frozenset[TransitionEvent]:
    """The events defined for `state`, ignoring guards."""
    return frozenset(_TRANSITIONS[state].keys())


def target_state(state: DealState, event: TransitionEvent) -> DealState:
    """The state `event` leads to, without evaluating guards.

    Raises InvalidTransition if the pair is not in the table.
    """
    transition = _TRANSITIONS[state].get(event)
    if transition is None:
        raise InvalidTransition(f"{event.value} is not allowed from state {state.value}")
    return transition.target


def can_transition(
    state: DealState, event: TransitionEvent, ctx: TransitionContext | None = None
) -> bool:
    """True when the transition is defined and its guard is satisfied."""
    try:
        next_state(state, event, ctx)
    except (InvalidTransition, TransitionGuardFailed):
        return False
    return True


def next_state(
    state: DealState, event: TransitionEvent, ctx: TransitionContext | None = None
) -> DealState:
    """Resolve the state `event` moves the deal to.

    Raises:
        InvalidTransition: the event is not defined for this state (this
            also covers every event out of a terminal state).
        TransitionGuardFailed: the transition exists but its precondition
            is not met.
    """
    transition = _TRANSITIONS[state].get(event)
    if transition is None:
        if is_terminal(state):
            raise InvalidTransition(
                f"deal is in terminal state {state.value}; {event.value} cannot be applied"
            )
        raise InvalidTransition(f"{event.value} is not allowed from state {state.value}")

    if transition.guard is not None:
        reason = transition.guard(ctx or TransitionContext())
        if reason is not None:
            raise TransitionGuardFailed(f"cannot apply {event.value} from {state.value}: {reason}")

    return transition.target


def is_already_applied(state: DealState, event: TransitionEvent) -> bool:
    """True when `state` is already the state `event` leads to.

    A replayed capture webhook arrives with the deal in FUNDED, where
    PAYMENT_CAPTURED is no longer a defined transition. Callers check this
    first and treat the event as a no-op instead of an error — the
    idempotency requirement in the SRS ("a replayed webhook never
    double-pays").
    """
    return any(
        transition.target == state
        for by_event in _TRANSITIONS.values()
        for evt, transition in by_event.items()
        if evt == event
    )
