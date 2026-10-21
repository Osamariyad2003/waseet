"""PayPal webhook receiver (FR-12).

Three things have to be true before an event is acted on:

  1. the signature verifies against PAYPAL_WEBHOOK_ID — an unverified event
     is rejected, and a verification that cannot be completed counts as a
     failure, never a pass;
  2. the event id has not been seen before — enforced by a unique index, so
     a redelivery is a no-op rather than a second state change;
  3. the event actually corresponds to a deal and to a transition the deal
     has not already made.

Webhooks confirm state; they do not decide it. A capture event can move a
deal to FUNDED, but no webhook ever releases, refunds or splits — those
happen only behind the decision policy or a human.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from fastapi import APIRouter, Request, status

from app.core.errors import ValidationError, error_body
from app.dependencies import (
    AuditRepoDep,
    DealRepoDep,
    PayPalDep,
    SessionDep,
    SettingsDep,
    WebhookRepoDep,
)
from app.domain.enums import Actor, DealState, TransitionEvent
from app.domain.errors import WebhookVerificationFailed
from app.domain.state_machine import is_already_applied, next_state
from app.integrations.paypal.interface import WebhookHeaders
from app.services.settlement_service import deal_transition_context

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["webhooks"])

MAX_BODY_BYTES = 256 * 1024

# Events Waseet acts on. Anything else is recorded and ignored — PayPal
# sends plenty that are not ours to interpret.
CAPTURE_COMPLETED = "PAYMENT.CAPTURE.COMPLETED"
CAPTURE_DENIED = "PAYMENT.CAPTURE.DENIED"
PAYOUT_SUCCEEDED = "PAYMENT.PAYOUTSBATCH.SUCCESS"
PAYOUT_DENIED = "PAYMENT.PAYOUTSBATCH.DENIED"
REFUND_COMPLETED = "PAYMENT.CAPTURE.REFUNDED"

HANDLED_EVENTS = frozenset(
    {CAPTURE_COMPLETED, CAPTURE_DENIED, PAYOUT_SUCCEEDED, PAYOUT_DENIED, REFUND_COMPLETED}
)


@router.post("/webhooks/paypal", status_code=status.HTTP_200_OK)
async def receive_paypal_webhook(
    request: Request,
    settings: SettingsDep,
    session: SessionDep,
    paypal: PayPalDep,
    webhook_repo: WebhookRepoDep,
    deal_repo: DealRepoDep,
    audit_repo: AuditRepoDep,
) -> dict[str, Any]:
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise ValidationError("the webhook payload is too large")

    try:
        event = json.loads(raw)
    except ValueError as exc:
        raise ValidationError("the webhook payload is not valid JSON") from exc
    if not isinstance(event, dict):
        raise ValidationError("the webhook payload must be a JSON object")

    event_id = str(event.get("id") or "").strip()
    event_type = str(event.get("event_type") or "").strip()
    if not event_id or not event_type:
        raise ValidationError("the webhook payload has no event id or type")

    # 1. Signature. Verified before anything is persisted or acted on.
    headers = WebhookHeaders.from_mapping(request.headers)
    if headers is None:
        logger.warning("webhook.missing_signature_headers", event_type=event_type)
        raise WebhookVerificationFailed("the webhook signature headers are missing")

    verified = await paypal.verify_webhook(
        headers=headers, event_body=event, webhook_id=settings.paypal_webhook_id
    )
    if not verified:
        logger.warning("webhook.verification_failed", event_type=event_type)
        raise WebhookVerificationFailed("the webhook signature could not be verified")

    return await _process_verified_event(
        event=event,
        event_id=event_id,
        event_type=event_type,
        session=session,
        webhook_repo=webhook_repo,
        deal_repo=deal_repo,
        audit_repo=audit_repo,
    )


async def _process_verified_event(
    *,
    event: dict[str, Any],
    event_id: str,
    event_type: str,
    session: SessionDep,
    webhook_repo: WebhookRepoDep,
    deal_repo: DealRepoDep,
    audit_repo: AuditRepoDep,
) -> dict[str, Any]:
    """Claim the event id, then apply it. Shared with the dev simulator."""
    # 2. Idempotency. The claim is the insert; a redelivery loses the race
    # against the unique index and stops here.
    claimed = await webhook_repo.claim(event_id=event_id, event_type=event_type, payload=event)
    if claimed is None:
        logger.info("webhook.duplicate_ignored", event_id=event_id, event_type=event_type)
        await session.commit()
        return {"status": "ignored", "reason": "this event has already been processed"}

    if event_type not in HANDLED_EVENTS:
        webhook_repo.mark_processed(claimed, f"event type {event_type} is not handled")
        await session.commit()
        logger.info("webhook.unhandled_type", event_id=event_id, event_type=event_type)
        return {"status": "ignored", "reason": "this event type is not handled"}

    # 3. Find the deal this event belongs to.
    deal = await _find_deal(event=event, event_type=event_type, deal_repo=deal_repo)
    if deal is None:
        webhook_repo.mark_processed(claimed, "no matching deal")
        await session.commit()
        logger.info("webhook.no_matching_deal", event_id=event_id, event_type=event_type)
        return {"status": "ignored", "reason": "no deal matches this event"}

    resource = event.get("resource")
    outcome = await _apply_event(
        event_type=event_type,
        deal_id=deal.id,
        deal_repo=deal_repo,
        audit_repo=audit_repo,
        resource=resource if isinstance(resource, dict) else None,
    )
    webhook_repo.mark_processed(claimed, outcome)
    await session.commit()

    logger.info("webhook.processed", event_id=event_id, event_type=event_type, outcome=outcome)
    return {"status": "processed", "outcome": outcome}


async def _find_deal(*, event: dict[str, Any], event_type: str, deal_repo: DealRepoDep):
    """Match the event to a deal by the references PayPal echoes back.

    `custom_id` is set to the deal id when the order is created, which is
    the reliable link; the capture id is the fallback.
    """
    resource = event.get("resource") or {}
    if not isinstance(resource, dict):
        return None

    custom_id = str(resource.get("custom_id") or "").strip()
    if custom_id:
        from uuid import UUID

        try:
            return await deal_repo.get(UUID(custom_id))
        except ValueError:
            pass

    capture_id = str(resource.get("id") or "").strip()
    if capture_id and event_type in {CAPTURE_COMPLETED, CAPTURE_DENIED, REFUND_COMPLETED}:
        deal = await deal_repo.get_by_capture_id(capture_id)
        if deal is not None:
            return deal

    supplementary = resource.get("supplementary_data") or {}
    related = (supplementary.get("related_ids") or {}) if isinstance(supplementary, dict) else {}
    order_id = str(related.get("order_id") or "").strip()
    if order_id:
        return await deal_repo.get_by_order_id(order_id)
    return None


async def _apply_event(
    *,
    event_type: str,
    deal_id,
    deal_repo: DealRepoDep,
    audit_repo: AuditRepoDep,
    resource: dict[str, Any] | None = None,
) -> str:
    """Apply a confirmation event to the deal, under a row lock."""
    deal = await deal_repo.get_for_update(deal_id)
    if deal is None:  # pragma: no cover
        return "no matching deal"

    if event_type == CAPTURE_COMPLETED:
        # Record the capture id from the event if we do not already have it.
        # Without this, a deal funded by the webhook alone — PayPal captured,
        # but our own capture call never ran or failed — would sit in FUNDED
        # with no capture reference, and both release and refund would later
        # refuse it as having no captured payment to settle.
        captured_id = str((resource or {}).get("id") or "").strip()
        if captured_id and not deal.paypal_capture_id:
            deal.paypal_capture_id = captured_id

        if is_already_applied(deal.state, TransitionEvent.PAYMENT_CAPTURED):
            return f"capture already applied; the deal is {deal.state.value}"
        if deal.state is not DealState.DRAFT:
            return f"no transition from {deal.state.value} for a capture"
        target = next_state(
            deal.state, TransitionEvent.PAYMENT_CAPTURED, deal_transition_context(deal)
        )
        from_state = deal.state
        deal.state = target
        audit_repo.append(
            deal_id=deal.id,
            from_state=from_state,
            to_state=target,
            actor=Actor.PAYPAL_WEBHOOK,
            event=TransitionEvent.PAYMENT_CAPTURED.value,
            reason="PayPal confirmed the capture; the funds are held in escrow",
            paypal_reference=deal.paypal_capture_id,
        )
        return f"the deal moved to {target.value}"

    # The remaining events confirm money that already moved, or report that
    # it did not. Neither changes state — a payout is recorded when it is
    # initiated, and a denial is surfaced for a human rather than silently
    # reversing a terminal state.
    reasons = {
        CAPTURE_DENIED: "PayPal denied the capture; the deal was not funded",
        PAYOUT_SUCCEEDED: "PayPal confirmed the payout batch reached the seller",
        PAYOUT_DENIED: "PayPal denied the payout batch; a reviewer needs to look at this",
        REFUND_COMPLETED: "PayPal confirmed the refund reached the buyer",
    }
    audit_repo.append(
        deal_id=deal.id,
        from_state=deal.state,
        to_state=deal.state,
        actor=Actor.PAYPAL_WEBHOOK,
        event=event_type,
        reason=reasons[event_type],
        paypal_reference=deal.payout_batch_id or deal.paypal_capture_id,
    )
    return "recorded in the audit trail"


@router.post("/webhooks/paypal/simulate", status_code=status.HTTP_200_OK)
async def simulate_paypal_webhook(
    request: Request,
    settings: SettingsDep,
    session: SessionDep,
    webhook_repo: WebhookRepoDep,
    deal_repo: DealRepoDep,
    audit_repo: AuditRepoDep,
) -> Any:
    """Dev-only: apply a webhook body without a signature.

    The demo should not depend on a public tunnel being up. Disabled unless
    ENABLE_WEBHOOK_SIMULATOR is true, and refused outright in production —
    the signature check is the only thing this skips, so it must never be
    reachable on a deployed instance.
    """
    if settings.is_production or not settings.enable_webhook_simulator:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=error_body("not_found", "not found"),
        )

    event = await request.json()
    if not isinstance(event, dict):
        raise ValidationError("the webhook payload must be a JSON object")

    event_id = str(event.get("id") or "").strip()
    event_type = str(event.get("event_type") or "").strip()
    if not event_id or not event_type:
        raise ValidationError("the webhook payload has no event id or type")

    logger.warning("webhook.simulated", event_id=event_id, event_type=event_type)
    return await _process_verified_event(
        event=event,
        event_id=event_id,
        event_type=event_type,
        session=session,
        webhook_repo=webhook_repo,
        deal_repo=deal_repo,
        audit_repo=audit_repo,
    )
