from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.domain.enums import Actor, DealState
from app.models.sql_enums import actor_enum, deal_state_enum


class AuditLogEntry(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Append-only (FR-10). One row per transition or decision.

    Nothing in the codebase updates or deletes these rows; the repository
    exposes append and read only. Each entry carries the PayPal reference id
    for the money movement it accompanies, so the trail ties the decision to
    the transaction.
    """

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_deal_id_created_at", "deal_id", "created_at"),)

    deal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deals.id", ondelete="CASCADE"), nullable=False
    )
    from_state: Mapped[DealState | None] = mapped_column(deal_state_enum, nullable=True)
    to_state: Mapped[DealState] = mapped_column(deal_state_enum, nullable=False)
    actor: Mapped[Actor] = mapped_column(actor_enum, nullable=False)
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    paypal_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)
