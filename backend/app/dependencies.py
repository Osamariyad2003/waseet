"""FastAPI dependencies: settings, DB session, gateways, services, and auth.

Wiring lives here so routers stay thin — a router declares what it needs and
never constructs a gateway or a repository itself.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

import structlog
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.errors import AuthenticationError
from app.core.security import decode_access_token
from app.database import get_db_session
from app.domain.enums import Role
from app.domain.errors import NotAuthorizedForDeal
from app.integrations.ai.client import AnthropicAIGateway
from app.integrations.ai.gemini import GeminiAIGateway
from app.integrations.ai.interface import AIGateway
from app.integrations.ai.stub import StubAIGateway
from app.integrations.catalog.channel3 import Channel3CatalogGateway
from app.integrations.catalog.interface import CatalogGateway
from app.integrations.catalog.stub import StubCatalogGateway
from app.integrations.content.client import HttpContentFetcher
from app.integrations.content.interface import ContentFetcher
from app.integrations.email.console import ConsoleEmailGateway
from app.integrations.email.interface import EmailGateway
from app.integrations.email.smtp import SmtpEmailGateway
from app.integrations.paypal.client import PayPalClient
from app.integrations.paypal.interface import PayPalGateway
from app.repositories.audit_repo import AuditRepository
from app.repositories.deal_repo import DealRepository
from app.repositories.deliverable_repo import DeliverableRepository
from app.repositories.offer_repo import OfferRepository
from app.repositories.verification_repo import VerificationRepository
from app.repositories.webhook_repo import WebhookRepository
from app.services.deal_service import DealService
from app.services.dispute_service import DisputeService
from app.services.milestone_service import MilestoneService
from app.services.notification_service import NotificationService
from app.services.settlement_service import SettlementService
from app.services.verification_service import VerificationService

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]

# auto_error=False so a missing header raises our own typed error, with the
# same body shape as every other failure.
_bearer = HTTPBearer(auto_error=False)


# --- gateways --------------------------------------------------------------
# Held on app.state so one httpx client and one SDK client serve the whole
# process, and so a test can override them with fakes.


def get_paypal_gateway(request: Request, settings: SettingsDep) -> PayPalGateway:
    gateway = getattr(request.app.state, "paypal_gateway", None)
    if gateway is None:
        gateway = PayPalClient(settings)
        request.app.state.paypal_gateway = gateway
    return gateway


def _build_ai_gateway(settings: Settings) -> AIGateway:
    # The stub exists so the product can be demonstrated without a key.
    # Settings refuse it in production, so this cannot be reached there.
    if settings.use_stub_ai:
        return StubAIGateway()
    if settings.ai_provider == "gemini":
        return GeminiAIGateway(settings)
    return AnthropicAIGateway(settings)


def get_ai_gateway(request: Request, settings: SettingsDep) -> AIGateway:
    gateway = getattr(request.app.state, "ai_gateway", None)
    if gateway is None:
        gateway = _build_ai_gateway(settings)
        request.app.state.ai_gateway = gateway
    return gateway


def get_email_gateway(request: Request, settings: SettingsDep) -> EmailGateway:
    """Gmail SMTP when configured, otherwise a console gateway that logs the
    email instead of sending it (so the demo works without credentials)."""
    gateway = getattr(request.app.state, "email_gateway", None)
    if gateway is None:
        gateway = SmtpEmailGateway(settings) if settings.email_configured else ConsoleEmailGateway()
        request.app.state.email_gateway = gateway
    return gateway


def get_catalog_gateway(request: Request, settings: SettingsDep) -> CatalogGateway:
    """Channel3 when a key is set, otherwise a stub catalog so the Shop &
    Escrow flow works keyless (the same pattern as the AI and email stubs)."""
    gateway = getattr(request.app.state, "catalog_gateway", None)
    if gateway is None:
        gateway = (
            Channel3CatalogGateway(settings)
            if settings.catalog_configured
            else StubCatalogGateway()
        )
        request.app.state.catalog_gateway = gateway
    return gateway


def get_content_fetcher(request: Request, settings: SettingsDep) -> ContentFetcher:
    """Resolves deliverable links so the verifier judges the work (FR-5)."""
    fetcher = getattr(request.app.state, "content_fetcher", None)
    if fetcher is None:
        fetcher = HttpContentFetcher(settings)
        request.app.state.content_fetcher = fetcher
    return fetcher


PayPalDep = Annotated[PayPalGateway, Depends(get_paypal_gateway)]
AIDep = Annotated[AIGateway, Depends(get_ai_gateway)]
ContentFetcherDep = Annotated[ContentFetcher, Depends(get_content_fetcher)]
EmailDep = Annotated[EmailGateway, Depends(get_email_gateway)]
CatalogDep = Annotated[CatalogGateway, Depends(get_catalog_gateway)]


def get_notification_service(settings: SettingsDep, email: EmailDep) -> NotificationService:
    return NotificationService(settings=settings, email=email)


NotificationsDep = Annotated[NotificationService, Depends(get_notification_service)]


# --- repositories ----------------------------------------------------------


def get_deal_repo(session: SessionDep) -> DealRepository:
    return DealRepository(session)


def get_deliverable_repo(session: SessionDep) -> DeliverableRepository:
    return DeliverableRepository(session)


def get_verification_repo(session: SessionDep) -> VerificationRepository:
    return VerificationRepository(session)


def get_audit_repo(session: SessionDep) -> AuditRepository:
    return AuditRepository(session)


def get_webhook_repo(session: SessionDep) -> WebhookRepository:
    return WebhookRepository(session)


def get_offer_repo(session: SessionDep) -> OfferRepository:
    return OfferRepository(session)


DealRepoDep = Annotated[DealRepository, Depends(get_deal_repo)]
DeliverableRepoDep = Annotated[DeliverableRepository, Depends(get_deliverable_repo)]
VerificationRepoDep = Annotated[VerificationRepository, Depends(get_verification_repo)]
AuditRepoDep = Annotated[AuditRepository, Depends(get_audit_repo)]
WebhookRepoDep = Annotated[WebhookRepository, Depends(get_webhook_repo)]
OfferRepoDep = Annotated[OfferRepository, Depends(get_offer_repo)]


# --- services --------------------------------------------------------------


def get_settlement_service(
    settings: SettingsDep, paypal: PayPalDep, audit_repo: AuditRepoDep
) -> SettlementService:
    return SettlementService(settings=settings, paypal=paypal, audit_repo=audit_repo)


SettlementDep = Annotated[SettlementService, Depends(get_settlement_service)]


def get_deal_service(
    session: SessionDep,
    deal_repo: DealRepoDep,
    deliverable_repo: DeliverableRepoDep,
    audit_repo: AuditRepoDep,
    ai: AIDep,
    paypal: PayPalDep,
) -> DealService:
    return DealService(
        session=session,
        deal_repo=deal_repo,
        deliverable_repo=deliverable_repo,
        audit_repo=audit_repo,
        ai=ai,
        paypal=paypal,
    )


def get_verification_service(
    session: SessionDep,
    settings: SettingsDep,
    deal_repo: DealRepoDep,
    deliverable_repo: DeliverableRepoDep,
    verification_repo: VerificationRepoDep,
    audit_repo: AuditRepoDep,
    settlement: SettlementDep,
    ai: AIDep,
    fetcher: ContentFetcherDep,
) -> VerificationService:
    return VerificationService(
        session=session,
        settings=settings,
        deal_repo=deal_repo,
        deliverable_repo=deliverable_repo,
        verification_repo=verification_repo,
        audit_repo=audit_repo,
        settlement=settlement,
        ai=ai,
        fetcher=fetcher,
    )


def get_dispute_service(
    session: SessionDep,
    deal_repo: DealRepoDep,
    deliverable_repo: DeliverableRepoDep,
    verification_repo: VerificationRepoDep,
    audit_repo: AuditRepoDep,
    settlement: SettlementDep,
    ai: AIDep,
    fetcher: ContentFetcherDep,
) -> DisputeService:
    return DisputeService(
        session=session,
        deal_repo=deal_repo,
        deliverable_repo=deliverable_repo,
        verification_repo=verification_repo,
        audit_repo=audit_repo,
        settlement=settlement,
        ai=ai,
        fetcher=fetcher,
    )


def get_milestone_service(
    session: SessionDep,
    settings: SettingsDep,
    deal_repo: DealRepoDep,
    deliverable_repo: DeliverableRepoDep,
    verification_repo: VerificationRepoDep,
    audit_repo: AuditRepoDep,
    settlement: SettlementDep,
    ai: AIDep,
    fetcher: ContentFetcherDep,
) -> MilestoneService:
    return MilestoneService(
        session=session,
        settings=settings,
        deal_repo=deal_repo,
        deliverable_repo=deliverable_repo,
        verification_repo=verification_repo,
        audit_repo=audit_repo,
        settlement=settlement,
        ai=ai,
        fetcher=fetcher,
    )


DealServiceDep = Annotated[DealService, Depends(get_deal_service)]
VerificationServiceDep = Annotated[VerificationService, Depends(get_verification_service)]
DisputeServiceDep = Annotated[DisputeService, Depends(get_dispute_service)]
MilestoneServiceDep = Annotated[MilestoneService, Depends(get_milestone_service)]


# --- auth ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: uuid.UUID
    email: str
    role: Role

    @property
    def is_reviewer(self) -> bool:
        return self.role is Role.REVIEWER


async def get_current_user(
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> CurrentUser:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("an authentication token is required")

    claims = decode_access_token(settings=settings, token=credentials.credentials)
    user = CurrentUser(
        id=uuid.UUID(claims["sub"]),
        email=claims.get("email", ""),
        role=Role(claims["role"]),
    )
    # So every log line for this request names who made it.
    structlog.contextvars.bind_contextvars(user_id=str(user.id), role=user.role.value)
    return user


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


async def require_reviewer(user: CurrentUserDep) -> CurrentUser:
    """Role check for the dispute endpoints (FR-8).

    Authenticated but wrong role is a 403, not a 401 — re-authenticating
    would not help.
    """
    if not user.is_reviewer:
        raise NotAuthorizedForDeal("this action requires the reviewer role")
    return user


ReviewerDep = Annotated[CurrentUser, Depends(require_reviewer)]
