"""Password hashing and JWT issuing/decoding.

Kept separate from `dependencies.py` so the crypto is unit-testable without
FastAPI. The secret and expiry come from settings, which read the
environment — never a literal in the code.
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.config import Settings
from app.core.errors import AuthenticationError
from app.domain.enums import Role


def _digest(password: str) -> bytes:
    """Pre-hash to a fixed 44-byte value before bcrypt.

    bcrypt silently ignores anything past 72 bytes, which would make two
    different long passwords interchangeable. Hashing first removes the
    limit instead of truncating, and base64 keeps the result free of NUL
    bytes, which bcrypt treats as a terminator.
    """
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_digest(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_digest(password), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        # A malformed stored hash must read as "wrong password", not crash.
        return False


def create_access_token(
    *, settings: Settings, user_id: uuid.UUID, role: Role, email: str
) -> tuple[str, int]:
    """Issue a bearer token. Returns (token, expires_in_seconds)."""
    expires_in = settings.jwt_expiry_minutes * 60
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "role": role.value,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expiry_minutes)).timestamp()),
    }
    token = jwt.encode(
        claims, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm
    )
    return token, expires_in


def decode_access_token(*, settings: Settings, token: str) -> dict[str, Any]:
    """Decode and validate a bearer token.

    Raises AuthenticationError on anything suspect — expired, wrong
    signature, wrong algorithm, or missing the claims we rely on.
    """
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("the session has expired; sign in again") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("the authentication token is not valid") from exc

    if not _is_uuid(claims.get("sub", "")):
        raise AuthenticationError("the authentication token is not valid")
    if claims.get("role") not in {role.value for role in Role}:
        raise AuthenticationError("the authentication token is not valid")
    return claims


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return True
