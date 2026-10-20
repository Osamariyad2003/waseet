"""FastAPI app factory and router registration."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import (
    auth,
    deals,
    deliverables,
    disputes,
    funding,
    verification,
    webhooks,
)
from app.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.database import dispose_engine

logger = structlog.get_logger(__name__)

DESCRIPTION = """\
AI-mediated escrow on PayPal. A buyer funds a deal, the platform holds the
money, and an AI verifies the seller's deliverable against agreed criteria to
auto-release payment — or routes the deal to a human-reviewed dispute.

The AI verdict is advisory. A deterministic policy decides whether it may
move money, and a human resolves anything the policy will not auto-release.
All money movement runs against the PayPal sandbox.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.is_production)
    logger.info(
        "app.start",
        environment=settings.environment,
        paypal_configured=settings.paypal_configured,
        ai_configured=settings.ai_configured,
        confidence_threshold=str(settings.auto_release_confidence_threshold),
        platform_fee_percent=str(settings.platform_fee_percent),
    )
    if settings.is_production and settings.enable_webhook_simulator:
        # Belt and braces: the endpoint also refuses, but a misconfigured
        # deploy should be loud at boot.
        logger.error("app.unsafe_config", reason="the webhook simulator is enabled")

    yield

    gateway = getattr(app.state, "paypal_gateway", None)
    if gateway is not None and hasattr(gateway, "aclose"):
        await gateway.aclose()
    await dispose_engine()
    logger.info("app.stop")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(
        title="Waseet",
        description=DESCRIPTION,
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(auth.router)
    app.include_router(deals.router)
    app.include_router(funding.router)
    app.include_router(deliverables.router)
    app.include_router(verification.router)
    app.include_router(disputes.router)
    app.include_router(webhooks.router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
