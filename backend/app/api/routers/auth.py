"""Authentication. Unauthenticated endpoints for login and signup."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.schemas.deals import LoginRequest, LoginResponse, SignupRequest, UserResponse
from app.core.errors import AuthenticationError, ConflictError, ValidationError
from app.core.security import create_access_token, hash_password, verify_password
from app.dependencies import CurrentUserDep, SessionDep, SettingsDep
from app.domain.enums import Role
from app.models.user import User

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["auth"])


@router.post("/auth/signup", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest, session: SessionDep, settings: SettingsDep) -> LoginResponse:
    email_clean = payload.email.lower().strip()
    result = await session.execute(select(User).where(User.email == email_clean))
    existing = result.scalars().first()
    if existing is not None:
        logger.info("auth.signup_duplicate_email", email_domain=email_clean.split("@")[-1])
        raise ConflictError("an account with this email already exists")

    if payload.role == Role.REVIEWER:
        raise ValidationError("reviewer accounts cannot be created via public signup")

    paypal_ref = payload.paypal_account_ref.strip() if payload.paypal_account_ref else None

    new_user = User(
        email=email_clean,
        full_name=payload.full_name.strip(),
        role=payload.role,
        password_hash=hash_password(payload.password),
        paypal_account_ref=paypal_ref,
    )
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)

    token, expires_in = create_access_token(
        settings=settings, user_id=new_user.id, role=new_user.role, email=new_user.email
    )
    logger.info("auth.signup_success", user_id=str(new_user.id), role=new_user.role.value)
    return LoginResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserResponse.model_validate(new_user),
    )


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
