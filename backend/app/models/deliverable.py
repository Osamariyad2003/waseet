from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UUIDPrimaryKeyMixin
from app.domain.enums import DeliverableType
from app.models.sql_enums import deliverable_type_enum


class Deliverable(UUIDPrimaryKeyMixin, Base):
    """What the seller submits (FR-4).

    `content_ref` is a URL, a repo link, a stored-file path, or the text
    itself — whichever the type implies. Its content is untrusted input: it
    is data for the verifier to judge, never instructions to follow.
    """

    __tablename__ = "deliverables"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Null on a simple deal; set when the deliverable is for a milestone.
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("milestones.id", ondelete="CASCADE"), nullable=True, index=True
    )
    type: Mapped[DeliverableType] = mapped_column(deliverable_type_enum, nullable=False)
    content_ref: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    deal = relationship("Deal", back_populates="deliverables")
    milestone = relationship(
        "Milestone", back_populates="deliverables", foreign_keys=[milestone_id], viewonly=True
    )
