"""Domain enumerations.

Pure Python. This module must not import the framework, the DB, or any
network code — the domain layer depends on nothing.
"""

from __future__ import annotations

from enum import StrEnum


class DealState(StrEnum):
    """The escrow lifecycle states from the SRS.

    RELEASED, REFUNDED and SPLIT are terminal; every other state has at
    least one exit.
    """

    DRAFT = "DRAFT"
    FUNDED = "FUNDED"
    DELIVERED = "DELIVERED"
    VERIFYING = "VERIFYING"
    RELEASED = "RELEASED"
    REFUNDED = "REFUNDED"
    DISPUTED = "DISPUTED"
    SPLIT = "SPLIT"


class DeliverableType(StrEnum):
    URL = "url"
    FILE = "file"
    IMAGE = "image"
    REPO = "repo"
    TEXT = "text"


class Verdict(StrEnum):
    """Verifier outcome. INCONCLUSIVE covers malformed or unusable output."""

    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


class DecidedBy(StrEnum):
    AI = "ai"
    HUMAN = "human"


class Role(StrEnum):
    BUYER = "buyer"
    SELLER = "seller"
    REVIEWER = "reviewer"


class TransitionEvent(StrEnum):
    """The named triggers that drive the lifecycle.

    The state machine is keyed on (state, event), so every state change in
    the system has to name the thing that caused it — which is also what
    lands in the audit log.
    """

    DEAL_CREATED = "deal_created"
    PAYMENT_CAPTURED = "payment_captured"
    DELIVERABLE_SUBMITTED = "deliverable_submitted"
    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_PASSED_CONFIDENTLY = "verification_passed_confidently"
    VERIFICATION_NOT_CONFIDENT = "verification_not_confident"
    BUYER_CONTESTED = "buyer_contested"
    HUMAN_DECIDED_RELEASE = "human_decided_release"
    HUMAN_DECIDED_REFUND = "human_decided_refund"
    HUMAN_DECIDED_SPLIT = "human_decided_split"


class SettlementAction(StrEnum):
    """What the system does with the money. Decided by policy or a human,
    never by an agent."""

    RELEASE = "release"
    REFUND = "refund"
    SPLIT = "split"


class PolicyOutcome(StrEnum):
    """The decision policy's only two answers."""

    AUTO_RELEASE = "auto_release"
    DISPUTE = "dispute"


class Actor(StrEnum):
    """Who caused an audit entry."""

    BUYER = "buyer"
    SELLER = "seller"
    REVIEWER = "reviewer"
    SYSTEM = "system"
    AI = "ai"
    PAYPAL_WEBHOOK = "paypal_webhook"
