"""A development stub for the AI gateway.

Lets the whole product be clicked through — criteria, verification,
auto-release, dispute, mediation — without an API key or a model call. It is
for seeing the system work, not for judging anything.

It is deliberately not clever. A model that is pretending to reason would be
worse than one that obviously is not: every judgment here comes from a
documented keyword rule, and every piece of reasoning it writes says plainly
that no model was called. If a demo is ever recorded against this stub, the
recording will say so on screen rather than implying an AI made a decision it
never made.

**The rule:** a criterion fails when the deliverable carries a fail marker —
a raster image extension, or a word like "draft" or "placeholder". Everything
else passes. That maps onto the demo's own story: an `.svg` link passes and
auto-releases, a `.png` link fails the vector criterion and goes to a human.

Enabled with `USE_STUB_AI=true`, and refused outright when
`ENVIRONMENT=production`.
"""

from __future__ import annotations

import re
from decimal import Decimal

import structlog

from app.domain.enums import SettlementAction, Verdict
from app.integrations.ai.interface import (
    CriterionJudgment,
    DealContext,
    DeliverableContext,
    DraftedCriterion,
    MediationRecommendation,
    VerificationJudgment,
)

logger = structlog.get_logger(__name__)

STUB_NOTICE = "Development stub — no AI model was called."

#: A deliverable containing any of these fails. Raster formats first, because
#: "vector, not raster" is the distinction the demo turns on.
FAIL_MARKERS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    "raster",
    "draft",
    "todo",
    "placeholder",
    "coming soon",
    "work in progress",
)

#: Attributes worth turning into their own criterion when the deal mentions
#: them, so the drafted checklist reflects what was actually asked for.
ATTRIBUTE_CRITERIA: tuple[tuple[tuple[str, ...], str], ...] = (
    (("vector", "svg"), "The deliverable is supplied in vector format (SVG or AI)."),
    (("transparent",), "The background is transparent."),
    (("logo",), "The delivered file is the agreed logo."),
    (("responsive",), "The delivered work is responsive at mobile and desktop widths."),
    (("repo", "repository", "github"), "The repository link opens and contains the work."),
    (("document", "documentation", "readme"), "The written documentation is included."),
    (("translation", "arabic", "english"), "The translated text covers the agreed content."),
)

CONFIDENCE_PASS = Decimal("0.920")
CONFIDENCE_FAIL = Decimal("0.880")


class StubAIGateway:
    """Implements `AIGateway` with fixed rules instead of a model."""

    def __init__(self) -> None:
        logger.warning(
            "ai.stub_enabled",
            detail="USE_STUB_AI is on; no model will be called and no judgment is real",
        )

    # --- criteria agent ---------------------------------------------------

    async def draft_criteria(self, *, deal: DealContext) -> tuple[DraftedCriterion, ...]:
        """Build a checklist from attributes the description actually mentions."""
        description = deal.description.lower()

        texts: list[str] = [
            f"The deliverable matches what was agreed: {_first_sentence(deal.description)}"
        ]
        for keywords, criterion in ATTRIBUTE_CRITERIA:
            if any(keyword in description for keyword in keywords):
                texts.append(criterion)

        if len(texts) == 1:
            # Nothing recognisable: fall back to something checkable.
            texts.append("The deliverable is complete and ready for the buyer to use.")

        logger.info("ai.stub_criteria", count=len(texts[:4]))
        return tuple(DraftedCriterion(text=text) for text in texts[:4])

    # --- verifier agent ---------------------------------------------------

    async def verify_deliverable(
        self,
        *,
        deal: DealContext,
        criteria: tuple[tuple[str, str], ...],
        deliverable: DeliverableContext,
    ) -> VerificationJudgment:
        if not criteria:
            return VerificationJudgment.inconclusive(
                f"{STUB_NOTICE} There are no confirmed criteria to judge against."
            )

        inspected = deliverable.inspected
        if inspected is not None and not inspected.is_available:
            # The same honest answer the real verifier gives: it has not seen
            # the work, so it cannot pass anything.
            return VerificationJudgment(
                verdict=Verdict.FAIL,
                confidence=Decimal("0.200"),
                reasoning=(
                    f"{STUB_NOTICE} The deliverable could not be retrieved "
                    f"({inspected.reason}), so nothing could be checked."
                ),
                per_criterion=tuple(
                    CriterionJudgment(
                        criterion_id=criterion_id,
                        text=text,
                        passed=False,
                        note="the deliverable could not be opened",
                    )
                    for criterion_id, text in criteria
                ),
            )

        haystack = _haystack(deliverable)
        marker = next((m for m in FAIL_MARKERS if m in haystack), None)

        judgments = tuple(
            CriterionJudgment(
                criterion_id=criterion_id,
                text=text,
                passed=marker is None,
                note=(
                    "no fail marker found in the submission"
                    if marker is None
                    else f"the submission contains {marker!r}"
                ),
            )
            for criterion_id, text in criteria
        )

        if marker is None:
            reasoning = (
                f"{STUB_NOTICE} The submission contains none of the markers this "
                "stub treats as failures, so every criterion is recorded as met."
            )
            verdict, confidence = Verdict.PASS, CONFIDENCE_PASS
        else:
            reasoning = (
                f"{STUB_NOTICE} The submission contains {marker!r}, which this stub "
                "treats as not meeting the agreed criteria."
            )
            verdict, confidence = Verdict.FAIL, CONFIDENCE_FAIL

        logger.info("ai.stub_verification", verdict=verdict.value, marker=marker)
        return VerificationJudgment(
            verdict=verdict,
            confidence=confidence,
            reasoning=reasoning,
            per_criterion=judgments,
        )

    # --- mediator agent ---------------------------------------------------

    async def mediate_dispute(
        self,
        *,
        deal: DealContext,
        criteria: tuple[tuple[str, str], ...],
        deliverable: DeliverableContext | None,
        verification: VerificationJudgment | None,
    ) -> MediationRecommendation:
        if deliverable is None:
            return MediationRecommendation(
                recommendation=SettlementAction.REFUND,
                reasoning=(
                    f"{STUB_NOTICE} Nothing was delivered, so the buyer should be refunded."
                ),
            )

        failed = verification.failed_criteria_count if verification else 0
        if failed == 0 and verification and verification.verdict is Verdict.PASS:
            return MediationRecommendation(
                recommendation=SettlementAction.RELEASE,
                reasoning=(
                    f"{STUB_NOTICE} The verification found nothing unmet, so the "
                    "seller should be paid."
                ),
            )

        return MediationRecommendation(
            recommendation=SettlementAction.REFUND,
            reasoning=(
                f"{STUB_NOTICE} The verification recorded {failed} unmet "
                "criterion/criteria, so the buyer should be refunded. A reviewer "
                "should weigh this against the deliverable itself."
            ),
        )


def _haystack(deliverable: DeliverableContext) -> str:
    """Everything the stub looks at, lowercased."""
    parts = [deliverable.content_ref, deliverable.note or ""]
    inspected = deliverable.inspected
    if inspected is not None and inspected.kind == "text":
        parts.append(inspected.text or "")
    if inspected is not None and inspected.media_type:
        # So a PNG fetched from an extension-less URL still reads as raster.
        parts.append(inspected.media_type.replace("image/", "."))
    return " ".join(parts).lower()


def _first_sentence(text: str) -> str:
    sentence = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]
    return sentence if len(sentence) <= 160 else f"{sentence[:157]}..."
