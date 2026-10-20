"""Shared fixtures.

Phase 1 covers the domain, which is pure and needs nothing. The PayPal and
AI gateway fakes land here in Phase 2, and the DB/app fixtures for the
integration suite in Phase 3.
"""

from __future__ import annotations

import os

import pytest

# A deterministic, credential-free environment, so a developer's real .env can
# never leak into a test run and the suite works on a clean checkout.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-a-real-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("PAYPAL_CLIENT_ID", "test-client-id")
os.environ.setdefault("PAYPAL_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-ai-key")
os.environ.setdefault("ENABLE_WEBHOOK_SIMULATOR", "false")


@pytest.fixture
def settings():
    from app.config import get_settings

    get_settings.cache_clear()
    return get_settings()
