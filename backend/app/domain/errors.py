"""Domain-level errors.

These are raised by the domain and by services. `app/core/errors.py` maps
them onto HTTP responses — the mapping lives there so the domain stays free
of transport concerns.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base for every expected, typed failure in the business layer."""

    code = "domain_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidTransition(DomainError):
    """The event is not defined for the deal's current state."""

    code = "invalid_transition"


class TransitionGuardFailed(DomainError):
    """The transition exists but its precondition is not satisfied."""

    code = "transition_guard_failed"


class DealNotFound(DomainError):
    code = "deal_not_found"


class NotAuthorizedForDeal(DomainError):
    """The caller is not a party to this deal, or lacks the required role."""

    code = "not_authorized_for_deal"


class CriteriaNotConfirmed(DomainError):
    code = "criteria_not_confirmed"


class SettlementError(DomainError):
    """A money movement could not be completed."""

    code = "settlement_error"


class PayPalError(DomainError):
    """A PayPal call failed or returned something unusable."""

    code = "paypal_error"


class AIError(DomainError):
    """An AI call failed, timed out, or returned unparseable output."""

    code = "ai_error"


class WebhookVerificationFailed(DomainError):
    code = "webhook_verification_failed"
