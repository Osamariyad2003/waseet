"""Add the pre-flight intake result to verification reports.

Additive and nullable: existing reports simply have no intake record, and the
column holds the security gate's JSON (status, risk, findings) for new ones.

Revision ID: 0004_verification_intake
Revises: 0003_offers
Create Date: 2026-10-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_verification_intake"
down_revision: str | None = "0003_offers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "verification_reports",
        sa.Column("intake", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("verification_reports", "intake")
