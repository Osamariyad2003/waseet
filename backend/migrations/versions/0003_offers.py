"""Marketplace offers: a `offers` table for seller service listings.

Additive and standalone — nothing else references it, and a buyer starts an
ordinary deal from an offer rather than the offer owning any state.

Revision ID: 0003_offers
Revises: 0002_milestones
Create Date: 2026-10-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_offers"
down_revision: str | None = "0002_milestones"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "offers",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("seller_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["seller_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_offers_seller_id", "offers", ["seller_id"])
    op.create_index("ix_offers_active", "offers", ["active"])


def downgrade() -> None:
    op.drop_index("ix_offers_active", table_name="offers")
    op.drop_index("ix_offers_seller_id", table_name="offers")
    op.drop_table("offers")
