from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.sql_enums import JSONType


class WebhookEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Dedup key for idempotent webhook handling.

    The unique index on `event_id` is the enforcement point: PayPal retries
    the same event id, the insert conflicts, and the handler returns without
    paying twice.
    """

    __tablename__ = "webhook_events"

    event_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Why a received event was ignored (unknown type, no matching deal, state
    # already past it) — keeps "nothing happened" explainable in the demo.
    outcome: Mapped[str | None] = mapped_column(String(255), nullable=True)
