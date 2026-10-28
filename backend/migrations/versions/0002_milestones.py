"""Milestone-based deals: a `milestones` table and a nullable `milestone_id`
on criteria, deliverables and verification reports.

Additive and backward compatible: an existing deal has no milestones, and its
criteria/deliverables/reports keep `milestone_id` NULL, which means "belongs
to the deal as a whole". Nothing about a simple deal changes.

Revision ID: 0002_milestones
Revises: 0001_initial
Create Date: 2026-10-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_milestones"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "milestones",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        # The milestone's own lifecycle runs over the shared deal_state enum.
        sa.Column(
            "state",
            postgresql.ENUM(name="deal_state", create_type=False),
            nullable=False,
        ),
        sa.Column("payout_batch_id", sa.String(length=64), nullable=True),
        sa.Column("refund_id", sa.String(length=64), nullable=True),
        sa.Column("platform_fee", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_milestones_deal_id", "milestones", ["deal_id"])

    for table in ("acceptance_criteria", "deliverables", "verification_reports"):
        op.add_column(table, sa.Column("milestone_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_milestone_id",
            table,
            "milestones",
            ["milestone_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index(f"ix_{table}_milestone_id", table, ["milestone_id"])


def downgrade() -> None:
    for table in ("verification_reports", "deliverables", "acceptance_criteria"):
        op.drop_index(f"ix_{table}_milestone_id", table_name=table)
        op.drop_constraint(f"fk_{table}_milestone_id", table, type_="foreignkey")
        op.drop_column(table, "milestone_id")

    op.drop_index("ix_milestones_deal_id", table_name="milestones")
    op.drop_table("milestones")
