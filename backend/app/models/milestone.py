from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.domain.enums import DealState
from app.models.sql_enums import deal_state_enum


class Milestone(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One slice of a deal that is delivered, verified and released on its own.

    A milestone deal is funded once, for the full amount; each milestone then
    runs its own mini-lifecycle over *the same* state machine the deal uses —
    it starts at DRAFT, moves to FUNDED when the deal's capture lands, and
    then DELIVERED → VERIFYING → RELEASED/DISPUTED exactly like a whole deal,
    but settling only its own `amount`. The deal stays FUNDED until every
    milestone is terminal.

    Its acceptance criteria, deliverables and verification reports are the
    same tables a simple deal uses, linked by a nullable `milestone_id`: null
    means "belongs to the deal as a whole" (a simple deal), set means "belongs
    to this milestone". So an ordinary deal is untouched by this table.
    """

    __tablename__ = "milestones"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(nullable=False, default=0)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    state: Mapped[DealState] = mapped_column(
        deal_state_enum, nullable=False, default=DealState.DRAFT
    )

    # PayPal references for this milestone's own settlement.
    payout_batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    refund_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    platform_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    deal = relationship("Deal", back_populates="milestones")
    criteria = relationship(
        "AcceptanceCriterion",
        back_populates="milestone",
        order_by="AcceptanceCriterion.position",
        viewonly=True,
        lazy="selectin",
        primaryjoin="AcceptanceCriterion.milestone_id == Milestone.id",
    )
    deliverables = relationship(
        "Deliverable",
        back_populates="milestone",
        order_by="Deliverable.submitted_at",
        viewonly=True,
        lazy="selectin",
        primaryjoin="Deliverable.milestone_id == Milestone.id",
    )
    verification_reports = relationship(
        "VerificationReport",
        back_populates="milestone",
        order_by="VerificationReport.decided_at",
        viewonly=True,
        lazy="selectin",
        primaryjoin="VerificationReport.milestone_id == Milestone.id",
    )
