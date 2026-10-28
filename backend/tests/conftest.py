"""Shared fixtures.

Unit tests are pure and need nothing. Integration tests run against a real
Postgres — the one in docker-compose — because the guarantees under test are
database guarantees: SELECT ... FOR UPDATE, the unique index that makes
webhooks idempotent, JSONB, and the append-only trigger on audit_log. None
of that is faithfully testable on SQLite.

If Postgres is not reachable, the integration tests skip with a clear
message rather than silently passing against a weaker engine.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
import pytest_asyncio

# A deterministic, credential-free environment. Setting WASEET_ENV_FILE empty
# stops Settings reading backend/.env, so a developer's real credentials and
# local flags can never change a test outcome. This must happen before
# app.config is imported.
os.environ["WASEET_ENV_FILE"] = ""
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-a-real-key-padded-to-32-bytes")
os.environ.setdefault("PAYPAL_CLIENT_ID", "test-client-id")
os.environ.setdefault("PAYPAL_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("PAYPAL_WEBHOOK_ID", "WH-TEST")
os.environ.setdefault("PAYPAL_SELLER_RECEIVER_EMAIL", "seller@sandbox.example.com")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-ai-key")
os.environ.setdefault("ENABLE_WEBHOOK_SIMULATOR", "true")

ADMIN_URL = os.environ.get(
    "TEST_ADMIN_DATABASE_URL", "postgresql+asyncpg://waseet:waseet@localhost:5434/waseet"
)
TEST_DB_NAME = "waseet_test"
TEST_DATABASE_URL = ADMIN_URL.rsplit("/", 1)[0] + f"/{TEST_DB_NAME}"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL


@pytest.fixture
def settings():
    from app.config import get_settings

    get_settings.cache_clear()
    return get_settings()


# --- database -------------------------------------------------------------


async def _postgres_available() -> bool:
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect():
            return True
    except Exception:
        return False
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def postgres_available() -> bool:
    return asyncio.run(_postgres_available())


@pytest_asyncio.fixture(scope="session")
async def database(postgres_available: bool) -> AsyncIterator[str]:
    """Create a dedicated test database, migrate it, and drop it after."""
    if not postgres_available:
        pytest.skip(
            "Postgres is not reachable at "
            f"{ADMIN_URL.rsplit('@', 1)[-1]} — run `docker compose up -d postgres`"
        )

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    admin = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    async with admin.connect() as connection:
        await connection.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
        await connection.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    await admin.dispose()

    # Build the schema through the real migration, so the tests exercise
    # what a fresh checkout actually gets — including the audit trigger.
    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    await asyncio.to_thread(command.upgrade, config, "head")

    yield TEST_DATABASE_URL

    from app.database import dispose_engine

    await dispose_engine()
    admin = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    async with admin.connect() as connection:
        await connection.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
    await admin.dispose()


@pytest_asyncio.fixture
async def clean_tables(database: str) -> AsyncIterator[None]:
    """Empty every table between tests.

    TRUNCATE, not DELETE: the append-only trigger on audit_log rejects
    DELETE, which is the point of it.
    """
    from sqlalchemy import text

    from app.database import get_session_factory

    async with get_session_factory()() as session:
        await session.execute(
            text(
                "TRUNCATE users, deals, acceptance_criteria, deliverables, "
                "verification_reports, audit_log, webhook_events RESTART IDENTITY CASCADE"
            )
        )
        await session.commit()
    yield


@pytest_asyncio.fixture
async def session(database: str, clean_tables: None) -> AsyncIterator:
    from app.database import get_session_factory

    async with get_session_factory()() as session:
        yield session


# --- gateways -------------------------------------------------------------


@pytest.fixture
def fake_paypal():
    from tests.fakes import FakePayPalGateway

    return FakePayPalGateway()


@pytest.fixture
def fake_ai():
    from tests.fakes import FakeAIGateway

    return FakeAIGateway()


@pytest.fixture
def fake_fetcher():
    """So a test that submits a link never makes a real request."""
    from tests.fakes import FakeContentFetcher

    return FakeContentFetcher()


@pytest.fixture
def email_spy():
    """Records notification emails instead of sending them."""
    from tests.fakes import FakeEmailGateway

    return FakeEmailGateway()


# --- app client -----------------------------------------------------------


@pytest_asyncio.fixture
async def client(
    database: str, clean_tables: None, fake_paypal, fake_ai, fake_fetcher, email_spy
) -> AsyncIterator:
    """An httpx client against the real app, with both gateways faked.

    Only the two external dependencies are replaced. Routing, validation,
    auth, services, the state machine and the database are all the real
    thing.
    """
    from httpx import ASGITransport, AsyncClient

    from app.dependencies import (
        get_ai_gateway,
        get_content_fetcher,
        get_email_gateway,
        get_paypal_gateway,
    )
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_paypal_gateway] = lambda: fake_paypal
    app.dependency_overrides[get_ai_gateway] = lambda: fake_ai
    app.dependency_overrides[get_content_fetcher] = lambda: fake_fetcher
    app.dependency_overrides[get_email_gateway] = lambda: email_spy

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://waseet.test"
    ) as http_client:
        yield http_client


# --- users ----------------------------------------------------------------


@pytest_asyncio.fixture
async def users(session) -> dict:
    """A buyer, a seller and a reviewer, with known passwords."""
    from app.core.security import hash_password
    from app.domain.enums import Role
    from app.models.user import User

    password_hash = hash_password("correct-horse")
    created = {}
    for role, email in (
        (Role.BUYER, "buyer@sandbox.example.com"),
        (Role.SELLER, "seller@sandbox.example.com"),
        (Role.REVIEWER, "reviewer@waseet.example.com"),
    ):
        user = User(
            id=uuid.uuid4(),
            email=email,
            full_name=role.value.title(),
            role=role,
            password_hash=password_hash,
            paypal_account_ref=email,
        )
        session.add(user)
        created[role.value] = user
    await session.commit()
    return created


@pytest_asyncio.fixture
async def tokens(client, users) -> dict:
    """A bearer token per role, obtained through the real login endpoint."""
    issued = {}
    for role, user in users.items():
        response = await client.post(
            "/auth/login", json={"email": user.email, "password": "correct-horse"}
        )
        assert response.status_code == 200, response.text
        issued[role] = response.json()["access_token"]
    return issued


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- deal helpers ---------------------------------------------------------


@pytest.fixture
def deal_payload() -> dict:
    return {
        "seller_email": "seller@sandbox.example.com",
        "title": "Coffee shop logo",
        "description": (
            "Design a logo for a coffee shop and deliver it as a vector file, "
            "with a transparent background."
        ),
        "amount": "250.00",
        "currency": "USD",
    }


DEAL_AMOUNT = Decimal("250.00")
