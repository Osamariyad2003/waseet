"""Anthropic-backed implementation of `AIGateway`.

Structured output is obtained by forcing a tool call, so a response either
validates against the schema or is treated as unusable. Per the Agentic
Workflow doc: one retry on a transient error, and anything still unresolved
becomes INCONCLUSIVE — which the decision policy routes to DISPUTED rather
than guessing.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import structlog
from anthropic import APIError, APIStatusError, AsyncAnthropic

from app.config import Settings
from app.domain.enums import SettlementAction, Verdict
from app.domain.errors import AIError
from app.integrations.ai import prompts
from app.integrations.ai.interface import (
    CriterionJudgment,
    DealContext,
    DeliverableContext,
    DraftedCriterion,
    MediationRecommendation,
    VerificationJudgment,
)

logger = structlog.get_logger(__name__)

MAX_TOKENS = 2048
MAX_ATTEMPTS = 2  # the initial call plus one retry
# A deliverable is "small enough for a model to inspect directly" per the SRS
# assumptions; this cap keeps a pathological submission from blowing the
# context window or the latency budget.
MAX_DELIVERABLE_CHARS = 20_000


class AnthropicAIGateway:
    """Implements `AIGateway`. Decides; never disburses."""

    def __init__(self, settings: Settings, client: AsyncAnthropic | None = None) -> None:
        self._settings = settings
        self._model = settings.ai_model
        self._client = client or AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value(),
            timeout=settings.ai_timeout_seconds,
            max_retries=0,  # retries are handled here, so they stay auditable
        )

    # --- criteria agent ---------------------------------------------------

    async def draft_criteria(self, *, deal: DealContext) -> tuple[DraftedCriterion, ...]:
        """FR-2. Raises AIError on failure: nothing has been funded yet, so
        surfacing the error to the user is the right move."""
        result = await self._call_tool(
            system=prompts.CRITERIA_SYSTEM,
            user=prompts.criteria_user_message(
                deal.description, self._money(deal.amount), deal.currency
            ),
            tool=prompts.CRITERIA_TOOL,
            what="draft acceptance criteria",
        )

        criteria = tuple(
            DraftedCriterion(text=text)
            for item in result.get("criteria", [])
            if (text := str(item.get("text", "")).strip())
        )
        if not criteria:
            raise AIError("the criteria agent returned no usable criteria")

        logger.info("ai.criteria_drafted", count=len(criteria))
        return criteria

    # --- verifier agent ---------------------------------------------------

    async def verify_deliverable(
        self,
        *,
        deal: DealContext,
        criteria: tuple[tuple[str, str], ...],
        deliverable: DeliverableContext,
    ) -> VerificationJudgment:
        """FR-5. Never raises: an unusable result is INCONCLUSIVE, which the
        decision policy sends to DISPUTED."""
        if not criteria:
            return VerificationJudgment.inconclusive(
                "the deal has no confirmed acceptance criteria to judge against"
            )

        content = (deliverable.content_ref or "")[:MAX_DELIVERABLE_CHARS]
        try:
            result = await self._call_tool(
                system=prompts.VERIFIER_SYSTEM,
                user=prompts.verifier_user_message(
                    deal.description,
                    self._money(deal.amount),
                    deal.currency,
                    criteria,
                    deliverable.type,
                    content,
                    deliverable.note,
                ),
                tool=prompts.VERIFIER_TOOL,
                what="verify the deliverable",
            )
        except AIError as exc:
            logger.warning("ai.verification_unavailable", error=str(exc))
            return VerificationJudgment.inconclusive(
                f"the verifier could not complete: {exc.message}. "
                "The deal is routed to a human reviewer."
            )

        return self._parse_verification(result, criteria)

    @staticmethod
    def _parse_verification(
        result: dict[str, Any], criteria: tuple[tuple[str, str], ...]
    ) -> VerificationJudgment:
        """Schema-validate the verifier's output; malformed → inconclusive."""
        texts = dict(criteria)

        raw_judgments = result.get("per_criterion")
        if not isinstance(raw_judgments, list) or not raw_judgments:
            return VerificationJudgment.inconclusive(
                "the verifier returned no per-criterion findings"
            )

        judgments: list[CriterionJudgment] = []
        for item in raw_judgments:
            if not isinstance(item, dict):
                continue
            criterion_id = str(item.get("criterion_id", ""))
            if criterion_id not in texts:
                # An id the model invented is not a judgment on a confirmed
                # criterion — drop it rather than crediting it.
                continue
            judgments.append(
                CriterionJudgment(
                    criterion_id=criterion_id,
                    text=texts[criterion_id],
                    passed=bool(item.get("pass")),
                    note=str(item.get("note", "")).strip(),
                )
            )

        judged_ids = {judgment.criterion_id for judgment in judgments}
        missing = [
            CriterionJudgment(
                criterion_id=criterion_id,
                text=text,
                passed=False,
                note="the verifier did not report on this criterion",
            )
            for criterion_id, text in criteria
            if criterion_id not in judged_ids
        ]
        if missing:
            # An incomplete verification cannot be a pass. The unreported
            # criteria are recorded as failed, which the policy disputes.
            logger.warning("ai.verification_incomplete", missing=len(missing))
        judgments.extend(missing)

        confidence = _parse_confidence(result.get("confidence"))
        if confidence is None:
            return VerificationJudgment.inconclusive(
                "the verifier returned an unusable confidence score"
            )

        reasoning = str(result.get("reasoning", "")).strip()
        if not reasoning:
            return VerificationJudgment.inconclusive("the verifier returned no reasoning")

        raw_verdict = str(result.get("verdict", "")).lower()
        if raw_verdict not in {"pass", "fail"}:
            return VerificationJudgment.inconclusive(
                f"the verifier returned an unrecognised verdict {raw_verdict!r}"
            )

        verdict = Verdict.PASS if raw_verdict == "pass" else Verdict.FAIL
        # A verdict that contradicts its own findings is not trusted. The
        # policy also guards this; rejecting it here keeps the stored report
        # internally consistent.
        if verdict is Verdict.PASS and any(not judgment.passed for judgment in judgments):
            verdict = Verdict.FAIL

        judgment = VerificationJudgment(
            verdict=verdict,
            confidence=confidence,
            reasoning=reasoning,
            per_criterion=tuple(judgments),
        )
        logger.info(
            "ai.verification_complete",
            verdict=verdict.value,
            confidence=str(confidence),
            failed=judgment.failed_criteria_count,
        )
        return judgment

    # --- mediator agent ---------------------------------------------------

    async def mediate_dispute(
        self,
        *,
        deal: DealContext,
        criteria: tuple[tuple[str, str], ...],
        deliverable: DeliverableContext | None,
        verification: VerificationJudgment | None,
    ) -> MediationRecommendation:
        """FR-8. Advisory only — a human makes the final call.

        On failure it recommends REFUND with that stated plainly: the
        reviewer still decides, and the conservative default never pays out
        on a broken model call.
        """
        summary = _summarise_verification(verification)
        try:
            result = await self._call_tool(
                system=prompts.MEDIATOR_SYSTEM,
                user=prompts.mediator_user_message(
                    deal.description,
                    self._money(deal.amount),
                    deal.currency,
                    criteria,
                    deliverable.type if deliverable else None,
                    (deliverable.content_ref or "")[:MAX_DELIVERABLE_CHARS]
                    if deliverable
                    else None,
                    summary,
                ),
                tool=prompts.MEDIATOR_TOOL,
                what="mediate the dispute",
            )
        except AIError as exc:
            logger.warning("ai.mediation_unavailable", error=str(exc))
            return MediationRecommendation(
                recommendation=SettlementAction.REFUND,
                reasoning=(
                    f"No AI recommendation is available ({exc.message}). "
                    "Defaulting to the conservative option of refunding the buyer — "
                    "the reviewer should decide on the evidence in the deal."
                ),
            )

        raw = str(result.get("recommendation", "")).lower()
        try:
            recommendation = SettlementAction(raw)
        except ValueError:
            return MediationRecommendation(
                recommendation=SettlementAction.REFUND,
                reasoning=(
                    f"The mediator returned an unrecognised recommendation {raw!r}. "
                    "Defaulting to the conservative option of refunding the buyer — "
                    "the reviewer should decide on the evidence in the deal."
                ),
            )

        reasoning = str(result.get("reasoning", "")).strip() or "No reasoning was provided."
        seller_amount = None
        if recommendation is SettlementAction.SPLIT:
            seller_amount = _parse_amount(result.get("suggested_seller_amount"), deal.amount)
            if seller_amount is None:
                # A split without a usable amount is not actionable; fall back
                # to refund and say so, rather than inventing a number.
                return MediationRecommendation(
                    recommendation=SettlementAction.REFUND,
                    reasoning=(
                        "The mediator recommended a split but gave no usable amount, so "
                        "no split can be proposed. Defaulting to refund for the reviewer "
                        f"to weigh. Original reasoning: {reasoning}"
                    ),
                )

        logger.info("ai.mediation_complete", recommendation=recommendation.value)
        return MediationRecommendation(
            recommendation=recommendation,
            reasoning=reasoning,
            suggested_seller_amount=seller_amount,
        )

    # --- plumbing ---------------------------------------------------------

    async def _call_tool(
        self, *, system: str, user: str, tool: dict[str, Any], what: str
    ) -> dict[str, Any]:
        """Force a tool call and return its validated input.

        One retry on a transient error. Raises AIError when the result is
        still unusable — callers decide whether that surfaces or becomes
        INCONCLUSIVE.
        """
        if not self._settings.ai_configured:
            raise AIError("the AI provider is not configured; set ANTHROPIC_API_KEY")

        last_error: str | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await self._client.messages.create(
                    model=self._model,
                    max_tokens=MAX_TOKENS,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                    tools=[tool],
                    tool_choice={"type": "tool", "name": tool["name"]},
                )
            except APIStatusError as exc:
                last_error = f"the model returned HTTP {exc.status_code}"
                if not _is_transient_status(exc.status_code):
                    break
            except APIError as exc:
                last_error = f"the model call failed ({type(exc).__name__})"
            except Exception as exc:  # noqa: BLE001 — nothing vendor-specific escapes
                last_error = f"the model call failed unexpectedly ({type(exc).__name__})"
            else:
                payload = _extract_tool_input(response, tool["name"])
                if payload is not None:
                    return payload
                last_error = "the model did not return the expected structured output"

            logger.warning("ai.call_retry", what=what, attempt=attempt, error=last_error)

        raise AIError(f"could not {what}: {last_error}")

    @staticmethod
    def _money(amount: Decimal) -> str:
        return f"{amount:.2f}"


def _is_transient_status(status_code: int) -> bool:
    return status_code == 408 or status_code == 429 or status_code >= 500


def _extract_tool_input(response: Any, tool_name: str) -> dict[str, Any] | None:
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
            payload = getattr(block, "input", None)
            if isinstance(payload, dict):
                return payload
    return None


def _parse_confidence(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        confidence = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not (Decimal("0") <= confidence <= Decimal("1")):
        return None
    return confidence.quantize(Decimal("0.001"))


def _parse_amount(value: Any, deal_amount: Decimal) -> Decimal | None:
    """A suggested split amount, only if it is strictly inside the deal."""
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not (Decimal("0") < amount < deal_amount):
        return None
    return amount


def _summarise_verification(verification: VerificationJudgment | None) -> str:
    if verification is None:
        return (
            "No AI verification was run for this deal (for example, the buyer "
            "contested before delivery was verified)."
        )
    lines = [
        f"Verdict: {verification.verdict.value}",
        f"Confidence: {verification.confidence}",
        f"Reasoning: {verification.reasoning}",
    ]
    if verification.per_criterion:
        lines.append("Per criterion:")
        lines.extend(
            f"  - [{'pass' if judgment.passed else 'fail'}] {judgment.text} — {judgment.note}"
            for judgment in verification.per_criterion
        )
    return "\n".join(lines)
