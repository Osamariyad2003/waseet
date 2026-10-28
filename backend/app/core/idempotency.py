"""Idempotency keys for money movement.

The SRS is explicit: "state transitions and payouts are idempotent; a
replayed webhook never double-pays or double-refunds". That is enforced in
three independent places, and this module owns the first one.

  1. Deterministic keys (here). Every money-moving call carries a key
     derived from the deal id and the action, so PayPal itself refuses the
     duplicate — a payout reuses its sender_batch_id, a refund and an order
     reuse their PayPal-Request-Id.
  2. The state machine. A replayed event is recognised as already-applied
     and becomes a no-op instead of a second transition.
  3. The database. A unique index on webhook_events.event_id means a
     redelivered webhook cannot be processed twice.

Keys are stable across restarts because they are pure functions of the deal
id — nothing is stored to make this work.
"""

from __future__ import annotations

import uuid

PREFIX = "waseet"


def order_request_id(deal_id: uuid.UUID) -> str:
    """Key for creating the funding order."""
    return f"{PREFIX}-order-{deal_id}"


def capture_request_id(deal_id: uuid.UUID) -> str:
    """Key for capturing into the platform account."""
    return f"{PREFIX}-capture-{deal_id}"


def release_batch_id(deal_id: uuid.UUID) -> str:
    """sender_batch_id for the release payout.

    One release per deal, so the deal id alone identifies it. A second
    attempt reuses this id and PayPal rejects the batch.
    """
    return f"{PREFIX}-release-{deal_id}"


def refund_request_id(deal_id: uuid.UUID) -> str:
    """PayPal-Request-Id for the refund."""
    return f"{PREFIX}-refund-{deal_id}"


def split_batch_id(deal_id: uuid.UUID) -> str:
    """sender_batch_id for the seller's share of a split.

    Distinct from the plain release id so a deal that was split cannot
    collide with a deal that was released.
    """
    return f"{PREFIX}-split-{deal_id}"


def split_refund_request_id(deal_id: uuid.UUID) -> str:
    """PayPal-Request-Id for the buyer's remainder in a split."""
    return f"{PREFIX}-split-refund-{deal_id}"


def milestone_release_batch_id(milestone_id: uuid.UUID) -> str:
    """sender_batch_id for one milestone's release payout.

    Keyed on the milestone id, not the deal, so each milestone of a deal gets
    its own stable key and a replay of one milestone's release cannot collide
    with another's.
    """
    return f"{PREFIX}-ms-release-{milestone_id}"


def milestone_refund_request_id(milestone_id: uuid.UUID) -> str:
    """PayPal-Request-Id for one milestone's refund (a partial refund of the
    deal's single capture)."""
    return f"{PREFIX}-ms-refund-{milestone_id}"
