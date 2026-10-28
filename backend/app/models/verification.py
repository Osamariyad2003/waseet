from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UUIDPrimaryKeyMixin
from app.domain.enums import DecidedBy, Verdict
from app.models.sql_enums import JSONType, decided_by_enum, verdict_enum


class VerificationReport(UUIDPrimaryKeyMixin, Base):
    """One row per verification or human decision (FR-5, FR-8).

    The reasoning is a first-class artifact, not a throwaway: every release,
    refund or split is backed by stored, human-readable reasoning and a
    confidence score.
    """

    __tablename__ = "verification_reports"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Null on a simple deal; set when the report is for a milestone.
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("milestones.id", ondelete="CASCADE"), nullable=True, index=True
    )
    deliverable_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deliverables.id", ondelete="SET NULL"), nullable=True
    )
    verdict: Mapped[Verdict] = mapped_column(verdict_enum, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    # [{"criterion_id": str, "text": str, "pass": bool, "note": str}, ...]
    per_criterion: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONType, nullable=False, default=list
    )
    decided_by: Mapped[DecidedBy] = mapped_column(decided_by_enum, nullable=False)
    # Set when a dispute mediator produced a recommendation for a human.
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The pre-flight intake screen's result (status, risk, findings), stored so
    # the deal and reviewer views can show what the security gate caught.
    intake: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    deal = relationship("Deal", back_populates="verification_reports")
    milestone = relationship(
        "Milestone",
        back_populates="verification_reports",
        foreign_keys=[milestone_id],
        viewonly=True,
    )
