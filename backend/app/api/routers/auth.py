"""Authentication. The only unauthenticated endpoint."""

from __future__ import annotations

import structlog
from fastapi import APIRouter
from sqlalchemy import select

from app.api.schemas.deals import LoginRequest, LoginResponse, UserResponse
from app.core.errors import AuthenticationError
from app.core.security import create_access_token, verify_password
from app.dependencies import CurrentUserDep, SessionDep, SettingsDep
from app.models.user import User

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest, session: SessionDep, settings: SettingsDep) -> LoginResponse:
    result = await session.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalars().first()

    # One message for both "no such user" and "wrong password", so the
    # endpoint does not reveal which emails are registered.
    if user is None or not verify_password(payload.password, user.password_hash):
        logger.info("auth.login_failed", email_domain=payload.email.split("@")[-1])
        raise AuthenticationError("the email or password is incorrect")

    token, expires_in = create_access_token(
        settings=settings, user_id=user.id, role=user.role, email=user.email
    )
    logger.info("auth.login", user_id=str(user.id), role=user.role.value)
    return LoginResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserResponse.model_validate(user),
    )


@router.get("/auth/me", response_model=UserResponse)
async def me(user: CurrentUserDep, session: SessionDep) -> UserResponse:
    """Lets the frontend restore a session without storing the user object."""
    result = await session.execute(select(User).where(User.id == user.id))
    found = result.scalars().first()
    if found is None:
        raise AuthenticationError("the authentication token is not valid")
    return UserResponse.model_validate(found)
