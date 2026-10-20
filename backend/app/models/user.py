from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.domain.enums import Role
from app.models.sql_enums import role_enum


class User(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Minimal identity for auth. Onboarding is out of scope (SRS assumptions)."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    role: Mapped[Role] = mapped_column(role_enum, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # The sandbox PayPal account this user transacts with (payout receiver for
    # a seller, payer for a buyer). Never a credential — just an account ref.
    paypal_account_ref: Mapped[str | None] = mapped_column(String(320), nullable=True)
