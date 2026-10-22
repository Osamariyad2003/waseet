"""Provider-agnostic LLM gateway.

The three judgment agents — criteria drafter, verifier, mediator — and all
their output parsing and guardrails live here, so they are identical no
matter which model backs them. A provider subclass implements exactly one
method: `_single_call`, which makes one structured-output request and
returns the parsed JSON (or raises a typed transient/permanent error).

Everything safety-relevant is in this file and shared: the structured
output is validated, an invented criterion id is dropped, an unreported
criterion counts as failed, a self-contradictory pass is downgraded, and a
failed or malformed call becomes INCONCLUSIVE — which the decision policy
routes to a human rather than guessing. One retry on a transient error.
"""

from __future__ import annotations

import abc
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog

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


class TransientModelError(Exception):
    """A failure worth one retry (timeout, 429, 5xx, missing output)."""


class PermanentModelError(Exception):
    """A failure not worth retrying (bad request, auth, unrecognised)."""


class BaseLLMGateway(abc.ABC):
    """Implements `AIGateway` over any structured-output LLM. Decides; never
    disburses."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = settings.ai_model

    # --- provider hooks ---------------------------------------------------

    @property
    @abc.abstractmethod
    def _provider_name(self) -> str:
        """For error messages, e.g. "ANTHROPIC_API_KEY"."""

    @abc.abstractmethod
    def _is_configured(self) -> bool:
        """Whether the provider has credentials to make a call."""

    @abc.abstractmethod
    async def _single_call(
        self,
        *,
        system: str,
        user: str,
        tool: dict[str, Any],
        image: tuple[str, str] | None,
    ) -> dict[str, Any]:
        """One structured-output request. Return the parsed JSON object, or
        raise TransientModelError / PermanentModelError."""

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
            if isinstance(item, dict) and (text := str(item.get("text", "")).strip())
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
        inspected = deliverable.inspected
        has_image = inspected is not None and inspected.kind == "image"
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
                    fetched_text=(
                        (inspected.text or "")[:MAX_DELIVERABLE_CHARS]
                        if inspected is not None and inspected.kind == "text"
                        else None
                    ),
                    fetched_truncated=bool(inspected and inspected.truncated),
                    unavailable_reason=(
                        inspected.reason
                        if inspected is not None and inspected.kind == "unavailable"
                        else None
                    ),
                    has_image=has_image,
                ),
                tool=prompts.VERIFIER_TOOL,
                what="verify the deliverable",
                image=(
                    (inspected.media_type or "", inspected.image_base64 or "")
                    if has_image and inspected is not None
                    else None
                ),
            )
        except AIError as exc:
            logger.warning("ai.verification_unavailable", error=str(exc))
            return VerificationJudgment.inconclusive(
                f"the verifier could not complete: {exc.message}. "
                "The deal is routed to a human reviewer."
            )
        return parse_verification(result, criteria)

    # --- mediator agent ---------------------------------------------------

    async def mediate_dispute(
        self,
        *,
        deal: DealContext,
        criteria: tuple[tuple[str, str], ...],
        deliverable: DeliverableContext | None,
        verification: VerificationJudgment | None,
    ) -> MediationRecommendation:
        """FR-8. Advisory only. On failure it recommends REFUND, stated
        plainly: the conservative default never pays out on a broken call."""
        summary = summarise_verification(verification)
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
            return _refund_fallback(f"No AI recommendation is available ({exc.message}).")

        raw = str(result.get("recommendation", "")).lower()
        try:
            recommendation = SettlementAction(raw)
        except ValueError:
            return _refund_fallback(
                f"The mediator returned an unrecognised recommendation {raw!r}."
            )

        reasoning = str(result.get("reasoning", "")).strip() or "No reasoning was provided."
        seller_amount = None
        if recommendation is SettlementAction.SPLIT:
            seller_amount = parse_amount(result.get("suggested_seller_amount"), deal.amount)
            if seller_amount is None:
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

    # --- shared plumbing --------------------------------------------------

    async def _call_tool(
        self,
        *,
        system: str,
        user: str,
        tool: dict[str, Any],
        what: str,
        image: tuple[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make the structured call with one retry on a transient error.

        Raises AIError when the result is still unusable — callers decide
        whether that surfaces or becomes INCONCLUSIVE.
        """
        if not self._is_configured():
            raise AIError(f"the AI provider is not configured; set {self._provider_name}")

        last_error: str | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return await self._single_call(system=system, user=user, tool=tool, image=image)
            except PermanentModelError as exc:
                last_error = str(exc)
                break
            except TransientModelError as exc:
                last_error = str(exc)
            except Exception as exc:  # noqa: BLE001 — nothing vendor-specific escapes
                last_error = f"the model call failed unexpectedly ({type(exc).__name__})"
            logger.warning("ai.call_retry", what=what, attempt=attempt, error=last_error)

        raise AIError(f"could not {what}: {last_error}")

    @staticmethod
    def _money(amount: Decimal) -> str:
        return f"{amount:.2f}"


# --- provider-agnostic parsing ---------------------------------------------


def parse_verification(
    result: dict[str, Any], criteria: tuple[tuple[str, str], ...]
) -> VerificationJudgment:
    """Schema-validate a verifier's output; malformed → inconclusive."""
    texts = dict(criteria)

    raw_judgments = result.get("per_criterion")
    if not isinstance(raw_judgments, list) or not raw_judgments:
        return VerificationJudgment.inconclusive("the verifier returned no per-criterion findings")

    judgments: list[CriterionJudgment] = []
    for item in raw_judgments:
        if not isinstance(item, dict):
            continue
        criterion_id = str(item.get("criterion_id", ""))
        if criterion_id not in texts:
            # An invented id is not a judgment on a confirmed criterion.
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
        logger.warning("ai.verification_incomplete", missing=len(missing))
    judgments.extend(missing)

    confidence = parse_confidence(result.get("confidence"))
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
    # A pass that contradicts its own findings is not trusted.
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


def parse_confidence(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        confidence = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not (Decimal("0") <= confidence <= Decimal("1")):
        return None
    return confidence.quantize(Decimal("0.001"))


def parse_amount(value: Any, deal_amount: Decimal) -> Decimal | None:
    """A suggested split amount, only if strictly inside the deal."""
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not (Decimal("0") < amount < deal_amount):
        return None
    return amount


def summarise_verification(verification: VerificationJudgment | None) -> str:
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


def _refund_fallback(reason: str) -> MediationRecommendation:
    return MediationRecommendation(
        recommendation=SettlementAction.REFUND,
        reasoning=(
            f"{reason} Defaulting to the conservative option of refunding the buyer — "
            "the reviewer should decide on the evidence in the deal."
        ),
    )
