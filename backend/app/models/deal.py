from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.domain.enums import DealState
from app.models.sql_enums import deal_state_enum


class Deal(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The central aggregate. `state` only ever changes via the state machine."""

    __tablename__ = "deals"
    __table_args__ = (
        Index("ix_deals_state", "state"),
        Index("ix_deals_buyer_id_seller_id", "buyer_id", "seller_id"),
    )

    buyer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    seller_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Money is numeric with an explicit currency — never a float.
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    platform_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    state: Mapped[DealState] = mapped_column(
        deal_state_enum, nullable=False, default=DealState.DRAFT
    )

    # PayPal references. Set as the lifecycle progresses; each one is also
    # written into the audit trail at the moment it is obtained.
    paypal_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    paypal_capture_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    payout_batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    refund_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    buyer = relationship("User", foreign_keys=[buyer_id], lazy="joined")
    seller = relationship("User", foreign_keys=[seller_id], lazy="joined")
    criteria = relationship(
        "AcceptanceCriterion",
        back_populates="deal",
        cascade="all, delete-orphan",
        order_by="AcceptanceCriterion.position",
    )
    deliverables = relationship(
        "Deliverable",
        back_populates="deal",
        cascade="all, delete-orphan",
        order_by="Deliverable.submitted_at",
    )
    verification_reports = relationship(
        "VerificationReport",
        back_populates="deal",
        cascade="all, delete-orphan",
        order_by="VerificationReport.decided_at",
    )

    def is_party(self, user_id: uuid.UUID) -> bool:
        return user_id in (self.buyer_id, self.seller_id)


class AcceptanceCriterion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One testable criterion, drafted by the criteria agent and confirmed by
    both parties before funding (FR-2)."""

    __tablename__ = "acceptance_criteria"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(nullable=False, default=0)
    confirmed_by_buyer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmed_by_seller: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    deal = relationship("Deal", back_populates="criteria")

    @property
    def is_confirmed(self) -> bool:
        return self.confirmed_by_buyer and self.confirmed_by_seller
