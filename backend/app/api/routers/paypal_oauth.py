"""PayPal OAuth 2.0 "Log in with PayPal" flow.

1. GET  /auth/paypal/redirect?app=escrow  → returns the PayPal authorize URL
2. POST /auth/paypal/callback             → exchanges the auth code for user
   info, finds or creates the local user, and returns a JWT.
"""

from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx
import structlog
from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.api.schemas.deals import LoginResponse, UserResponse
from app.core.errors import AuthenticationError
from app.core.security import create_access_token, hash_password
from app.config import Settings
from app.dependencies import SessionDep, SettingsDep
from app.domain.enums import Role
from app.models.user import User

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["auth"])

PAYPAL_SANDBOX_AUTH_URL = "https://www.sandbox.paypal.com/signin/authorize"
PAYPAL_SANDBOX_TOKEN_URL = "https://api-m.sandbox.paypal.com/v1/oauth2/token"
PAYPAL_SANDBOX_USERINFO_URL = "https://api-m.sandbox.paypal.com/v1/identity/openidconnect/userinfo?schema=openid"


class PayPalRedirectResponse(BaseModel):
    authorize_url: str


class PayPalCallbackRequest(BaseModel):
    code: str
    app: str = "escrow"


@router.get("/auth/paypal/redirect", response_model=PayPalRedirectResponse)
async def paypal_redirect(
    settings: SettingsDep,
    app: str = Query("escrow", pattern="^(escrow|admin)$"),
) -> PayPalRedirectResponse:
    if not settings.paypal_configured:
        raise AuthenticationError("PayPal credentials are not configured")

    redirect_uri = _redirect_uri(settings, app)
    params = {
        "flowEntry": "static",
        "client_id": settings.paypal_client_id,
        "response_type": "code",
        "scope": "openid email profile",
        "redirect_uri": redirect_uri,
    }
    url = f"{PAYPAL_SANDBOX_AUTH_URL}?{urlencode(params)}"
    return PayPalRedirectResponse(authorize_url=url)


@router.get("/auth/paypal/status")
async def paypal_oauth_status(settings: SettingsDep) -> dict:
    redirect_uri = _redirect_uri(settings, "escrow")
    return {
        "paypal_configured": settings.paypal_configured,
        "redirect_uri": redirect_uri,
        "paypal_oauth_return_url_override": settings.paypal_oauth_return_url or None,
        "instructions": (
            "Add the redirect_uri above as a Return URL in the PayPal Developer "
            "Dashboard under Apps & Credentials > [Your App] > Log in with PayPal > "
            "Manage. Or set PAYPAL_OAUTH_RETURN_URL in .env to match a URL already "
            "registered in the Dashboard."
        ),
    }


@router.post("/auth/paypal/callback", response_model=LoginResponse)
async def paypal_callback(
    payload: PayPalCallbackRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> LoginResponse:
    if not settings.paypal_configured:
        raise AuthenticationError("PayPal credentials are not configured")

    redirect_uri = _redirect_uri(settings, payload.app)

    async with httpx.AsyncClient(timeout=15) as http:
        token_resp = await http.post(
            PAYPAL_SANDBOX_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": payload.code,
                "redirect_uri": redirect_uri,
            },
            auth=(
                settings.paypal_client_id,
                settings.paypal_client_secret.get_secret_value(),
            ),
        )
        if token_resp.status_code != 200:
            logger.warning("paypal_oauth.token_failed", status=token_resp.status_code)
            raise AuthenticationError("PayPal authorization failed")

        tokens = token_resp.json()
        access_token = tokens.get("access_token")
        if not access_token:
            raise AuthenticationError("PayPal did not return an access token")

        userinfo_resp = await http.get(
            PAYPAL_SANDBOX_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_resp.status_code != 200:
            logger.warning("paypal_oauth.userinfo_failed", status=userinfo_resp.status_code)
            raise AuthenticationError("could not retrieve PayPal profile")

        userinfo = userinfo_resp.json()

    email = (userinfo.get("email") or "").lower().strip()
    if not email:
        emails = userinfo.get("emails", [])
        for e in emails:
            if e.get("primary") or e.get("confirmed"):
                email = e.get("value", "").lower().strip()
                break
        if not email and emails:
            email = emails[0].get("value", "").lower().strip()

    if not email:
        raise AuthenticationError("PayPal account has no email address")

    full_name = userinfo.get("name", "")
    if not full_name:
        given = userinfo.get("given_name", "")
        family = userinfo.get("family_name", "")
        full_name = f"{given} {family}".strip()

    paypal_id = userinfo.get("payer_id") or userinfo.get("user_id") or ""

    result = await session.execute(select(User).where(User.email == email))
    user = result.scalars().first()

    if user is None:
        role = Role.BUYER
        user = User(
            email=email,
            full_name=full_name or email.split("@")[0],
            role=role,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            paypal_account_ref=paypal_id or None,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        logger.info("paypal_oauth.user_created", user_id=str(user.id), email_domain=email.split("@")[-1])
    else:
        if paypal_id and not user.paypal_account_ref:
            user.paypal_account_ref = paypal_id
            await session.commit()
            await session.refresh(user)
        logger.info("paypal_oauth.user_found", user_id=str(user.id))

    token, expires_in = create_access_token(
        settings=settings, user_id=user.id, role=user.role, email=user.email
    )
    return LoginResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserResponse.model_validate(user),
    )


def _redirect_uri(settings: Settings, app: str) -> str:
    if settings.paypal_oauth_return_url:
        return settings.paypal_oauth_return_url
    base = settings.app_base_url.rstrip("/")
    if app == "admin":
        base = base.replace(":3000", ":3001")
    return f"{base}/en/login/paypal/callback"
