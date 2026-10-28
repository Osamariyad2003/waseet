from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class Offer(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A service a seller advertises in the marketplace.

    An offer is only a listing — it holds no money and changes no state. A
    buyer browses offers and starts an ordinary escrow deal from one, which is
    where the real lifecycle (and all its guardrails) begins. So the
    marketplace is a convenience layer over deal creation, nothing more.
    """

    __tablename__ = "offers"
    __table_args__ = (Index("ix_offers_active", "active"),)

    seller_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="other")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    # A delisted offer is kept (deals may reference its history) but hidden.
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    seller = relationship("User", foreign_keys=[seller_id], lazy="selectin")
