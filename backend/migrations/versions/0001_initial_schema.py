"""Initial Waseet schema: users, deals, criteria, deliverables, reports, audit, webhooks.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Enum types are created once here and referenced with create_type=False
# afterwards, so no table tries to CREATE TYPE a second time.
deal_state = postgresql.ENUM(
    "DRAFT",
    "FUNDED",
    "DELIVERED",
    "VERIFYING",
    "RELEASED",
    "REFUNDED",
    "DISPUTED",
    "SPLIT",
    name="deal_state",
)
deliverable_type = postgresql.ENUM("url", "file", "image", "repo", "text", name="deliverable_type")
verdict = postgresql.ENUM("pass", "fail", "inconclusive", name="verdict")
decided_by = postgresql.ENUM("ai", "human", name="decided_by")
role = postgresql.ENUM("buyer", "seller", "reviewer", name="role")
actor = postgresql.ENUM(
    "buyer", "seller", "reviewer", "system", "ai", "paypal_webhook", name="actor"
)

ALL_ENUMS = (deal_state, deliverable_type, verdict, decided_by, role, actor)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in ALL_ENUMS:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("role", postgresql.ENUM(name="role", create_type=False), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("paypal_account_ref", sa.String(length=320), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    # unique=True + index=True on the model renders as a single unique index.
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "deals",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=False),
        sa.Column("seller_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("platform_fee", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("state", postgresql.ENUM(name="deal_state", create_type=False), nullable=False),
        sa.Column("paypal_order_id", sa.String(length=64), nullable=True),
        sa.Column("paypal_capture_id", sa.String(length=64), nullable=True),
        sa.Column("payout_batch_id", sa.String(length=64), nullable=True),
        sa.Column("refund_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["buyer_id"], ["users.id"], name="fk_deals_buyer_id_users"),
        sa.ForeignKeyConstraint(["seller_id"], ["users.id"], name="fk_deals_seller_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_deals"),
    )
    op.create_index("ix_deals_state", "deals", ["state"])
    op.create_index("ix_deals_buyer_id_seller_id", "deals", ["buyer_id", "seller_id"])
    op.create_index("ix_deals_paypal_order_id", "deals", ["paypal_order_id"])
    op.create_index("ix_deals_paypal_capture_id", "deals", ["paypal_capture_id"])

    op.create_table(
        "acceptance_criteria",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("confirmed_by_buyer", sa.Boolean(), nullable=False),
        sa.Column("confirmed_by_seller", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["deal_id"],
            ["deals.id"],
            name="fk_acceptance_criteria_deal_id_deals",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_acceptance_criteria"),
    )
    op.create_index("ix_acceptance_criteria_deal_id", "acceptance_criteria", ["deal_id"])

    op.create_table(
        "deliverables",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column(
            "type", postgresql.ENUM(name="deliverable_type", create_type=False), nullable=False
        ),
        sa.Column("content_ref", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["deal_id"], ["deals.id"], name="fk_deliverables_deal_id_deals", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_deliverables"),
    )
    op.create_index("ix_deliverables_deal_id", "deliverables", ["deal_id"])

    op.create_table(
        "verification_reports",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column("deliverable_id", sa.Uuid(), nullable=True),
        sa.Column("verdict", postgresql.ENUM(name="verdict", create_type=False), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("per_criterion", postgresql.JSONB(), nullable=False),
        sa.Column(
            "decided_by", postgresql.ENUM(name="decided_by", create_type=False), nullable=False
        ),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column(
            "decided_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["deal_id"],
            ["deals.id"],
            name="fk_verification_reports_deal_id_deals",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["deliverable_id"],
            ["deliverables.id"],
            name="fk_verification_reports_deliverable_id_deliverables",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_verification_reports"),
    )
    op.create_index("ix_verification_reports_deal_id", "verification_reports", ["deal_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column(
            "from_state", postgresql.ENUM(name="deal_state", create_type=False), nullable=True
        ),
        sa.Column(
            "to_state", postgresql.ENUM(name="deal_state", create_type=False), nullable=False
        ),
        sa.Column("actor", postgresql.ENUM(name="actor", create_type=False), nullable=False),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("paypal_reference", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["deal_id"], ["deals.id"], name="fk_audit_log_deal_id_deals", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
    )
    op.create_index("ix_audit_log_deal_id_created_at", "audit_log", ["deal_id", "created_at"])

    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_webhook_events"),
    )
    op.create_index("ix_webhook_events_event_id", "webhook_events", ["event_id"], unique=True)

    # FR-10: the audit log is append-only. Enforced in the database, not just
    # by convention in the repository.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION waseet_audit_log_is_append_only()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only; % is not permitted', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_no_update_or_delete
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION waseet_audit_log_is_append_only();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update_or_delete ON audit_log;")
    op.execute("DROP FUNCTION IF EXISTS waseet_audit_log_is_append_only();")

    op.drop_table("webhook_events")
    op.drop_table("audit_log")
    op.drop_table("verification_reports")
    op.drop_table("deliverables")
    op.drop_table("acceptance_criteria")
    op.drop_table("deals")
    op.drop_table("users")

    bind = op.get_bind()
    for enum_type in ALL_ENUMS:
        enum_type.drop(bind, checkfirst=True)
