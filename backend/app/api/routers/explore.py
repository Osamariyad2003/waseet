"""Explore router — public platform overview, escrow lifecycle, and safety guarantees."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter

from app.api.schemas.deals import (
    ExplorePlatformInfo,
    ExploreResponse,
    LifecycleStep,
    SafetyPillar,
)
from app.dependencies import DealRepoDep, SettingsDep
from app.domain.enums import DealState, DeliverableType

router = APIRouter(prefix="/explore", tags=["explore"])


@router.get("", response_model=ExploreResponse)
async def get_explore_info(
    deal_repo: DealRepoDep,
    settings: SettingsDep,
) -> ExploreResponse:
    """Public informational endpoint explaining Waseet's architecture, safety rules, and stats."""
    totals = await deal_repo.state_totals()
    total_deals = sum(c for c, _ in totals.values())
    total_volume = sum((a for _, a in totals.values()), Decimal("0"))
    released_volume = sum(
        (totals.get(s, (0, Decimal("0")))[1] for s in (DealState.RELEASED, DealState.SPLIT)),
        Decimal("0"),
    )

    steps = [
        LifecycleStep(
            step=1,
            key="create",
            title="Create & Agree",
            description=(
                "A buyer describes the work. The AI drafts an acceptance checklist, and both "
                "parties confirm it before any money moves."
            ),
        ),
        LifecycleStep(
            step=2,
            key="fund",
            title="Fund the Escrow",
            description=(
                "The buyer pays through PayPal. The money is captured into the platform account "
                "and held — it is not sent to the seller."
            ),
        ),
        LifecycleStep(
            step=3,
            key="deliver",
            title="Deliver & Verify",
            description=(
                "The seller submits the work. The AI fetches it and checks it against the "
                "confirmed checklist."
            ),
        ),
        LifecycleStep(
            step=4,
            key="settle",
            title="Release or Dispute",
            description=(
                "A confident pass auto-releases to the seller. Anything else goes to a human "
                "reviewer with the money still held."
            ),
        ),
    ]

    safety_pillars = [
        SafetyPillar(
            key="decide",
            title="Decide, Don't Disburse",
            description=(
                "The agents read the deal and judge the work. They can never move money — "
                "a deterministic policy does that."
            ),
        ),
        SafetyPillar(
            key="gate",
            title="Confidence Gate",
            description=(
                "Auto-release only on a clear pass at or above the confidence threshold, "
                "with no failed criterion and no buyer contest."
            ),
        ),
        SafetyPillar(
            key="failsafe",
            title="Fail Safe, Not Open",
            description=(
                "A fail, low confidence, an unreadable response or a contest all route to a "
                "dispute, with the funds held."
            ),
        ),
        SafetyPillar(
            key="bounded",
            title="Bounded Payouts",
            description=(
                "Every payout is capped at the deal amount and pinned to the named seller, "
                "whatever the deliverable claims."
            ),
        ),
    ]

    platform_info = ExplorePlatformInfo(
        confidence_threshold=settings.auto_release_confidence_threshold,
        platform_fee_percent=settings.platform_fee_percent,
        sandbox_mode=True,
        ai_provider=settings.ai_provider,
        supported_deliverable_types=[
            DeliverableType.URL,
            DeliverableType.FILE,
            DeliverableType.IMAGE,
            DeliverableType.REPO,
            DeliverableType.TEXT,
        ],
    )

    stats = {
        "total_deals": total_deals,
        "total_volume_secured": str(total_volume),
        "total_volume_released": str(released_volume),
        "active_escrows": sum(
            totals.get(s, (0, Decimal("0")))[0]
            for s in (
                DealState.FUNDED,
                DealState.DELIVERED,
                DealState.VERIFYING,
                DealState.DISPUTED,
            )
        ),
    }

    return ExploreResponse(
        title="How Waseet Works",
        subtitle=(
            "The AI verifies the work. A fixed policy — not the AI — decides whether that "
            "judgment is allowed to move money."
        ),
        steps=steps,
        safety_pillars=safety_pillars,
        platform_info=platform_info,
        stats=stats,
    )
