"""Seed the three demo accounts.

Waseet models the PayPal sandbox's three parties as three users:

    buyer     funds the deal          (sandbox personal account)
    seller    receives the payout     (sandbox personal account)
    reviewer  resolves disputes       (platform staff; no PayPal account)

`paypal_account_ref` on the seller is the sandbox email that receives
payouts, so it must match a real sandbox personal account for a release to
land. Everything comes from the environment: pass the sandbox emails in, or
accept the defaults for a dry run.

    uv run python scripts/seed.py            # create or update the accounts
    uv run python scripts/seed.py --reset    # wipe every deal first

--reset uses TRUNCATE rather than DELETE: the audit log is append-only and
the database trigger rejects DELETE, which is the point of it.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import sys

from sqlalchemy import select, text

from app.config import get_settings
from app.core.security import hash_password
from app.database import dispose_engine, get_session_factory
from app.domain.enums import Role
from app.models.user import User

# Override with SEED_BUYER_EMAIL / SEED_SELLER_EMAIL / SEED_REVIEWER_EMAIL.
#
# example.com, not .test: the API validates addresses with email-validator,
# which rejects reserved TLDs like .test and .local outright — a seeded
# account on one of those could never log in.
DEFAULT_ACCOUNTS = {
    Role.BUYER: ("buyer@waseet.example.com", "Sama the Buyer"),
    Role.SELLER: ("seller@waseet.example.com", "Karim the Seller"),
    Role.REVIEWER: ("reviewer@waseet.example.com", "Layla the Reviewer"),
}

TABLES = (
    "deals",
    "acceptance_criteria",
    "deliverables",
    "verification_reports",
    "audit_log",
    "webhook_events",
)


def account_for(role: Role) -> tuple[str, str]:
    default_email, name = DEFAULT_ACCOUNTS[role]
    email = os.environ.get(f"SEED_{role.value.upper()}_EMAIL", default_email).strip().lower()
    return email, name


def resolve_password() -> tuple[str, bool]:
    """The demo password. Generated if not supplied, and printed once.

    A generated password is printed because there is no other way to recover
    it; a supplied one never is.
    """
    supplied = os.environ.get("SEED_PASSWORD", "").strip()
    if supplied:
        return supplied, False
    return secrets.token_urlsafe(12), True


async def reset_deals() -> None:
    async with get_session_factory()() as session:
        await session.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
        await session.commit()
    print("  cleared every deal, criterion, deliverable, report and audit entry")


async def seed(reset: bool) -> int:
    settings = get_settings()
    print(f"\nSeeding Waseet demo accounts -> {_safe_database_label(settings.database_url)}")

    if reset:
        await reset_deals()

    password, generated = resolve_password()
    password_hash = hash_password(password)

    # The seller's payout address. Release goes here, so a wrong value means
    # a payout that silently lands nowhere useful.
    seller_payout = (
        settings.paypal_seller_receiver_email.strip()
        or os.environ.get("SEED_SELLER_EMAIL", "").strip()
    )

    async with get_session_factory()() as session:
        for role in (Role.BUYER, Role.SELLER, Role.REVIEWER):
            email, full_name = account_for(role)
            paypal_ref = (
                seller_payout or email
                if role is Role.SELLER
                else (email if role is Role.BUYER else None)
            )

            existing = (
                (await session.execute(select(User).where(User.email == email))).scalars().first()
            )

            if existing is None:
                session.add(
                    User(
                        email=email,
                        full_name=full_name,
                        role=role,
                        password_hash=password_hash,
                        paypal_account_ref=paypal_ref,
                    )
                )
                action = "created"
            else:
                # Re-running the seed resets the password and the payout
                # address, so a half-configured demo can be repaired without
                # dropping the database.
                existing.full_name = full_name
                existing.role = role
                existing.password_hash = password_hash
                existing.paypal_account_ref = paypal_ref
                action = "updated"

            suffix = f"  payout -> {paypal_ref}" if role is Role.SELLER else ""
            print(f"  {action:8} {role.value:9} {email}{suffix}")

        await session.commit()

    print("\n  password:", password if generated else "(as supplied in SEED_PASSWORD)")
    if generated:
        print("  this was generated and is not stored anywhere — note it now")

    if not settings.paypal_seller_receiver_email:
        print(
            "\n  warning: PAYPAL_SELLER_RECEIVER_EMAIL is not set, so a release "
            "would be sent to the seller's login email. Set it to the sandbox "
            "personal account that should receive payouts."
        )

    print()
    return 0


def _safe_database_label(url: str) -> str:
    """Host and database only — never the credentials in the URL."""
    return url.rsplit("@", 1)[-1] if "@" in url else url


async def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the Waseet demo accounts.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete every deal before seeding (accounts are kept)",
    )
    args = parser.parse_args()

    try:
        return await seed(reset=args.reset)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
