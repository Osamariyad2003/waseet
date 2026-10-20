"""Password hashing and JWT handling."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config import Settings
from app.core.errors import AuthenticationError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.domain.enums import Role


def make_settings(**overrides) -> Settings:
    config = {
        "jwt_secret": "a-test-secret-long-enough-for-hs256",
        "database_url": "sqlite+aiosqlite:///:memory:",
        **overrides,
    }
    return Settings(**config)


class TestPasswordHashing:
    def test_a_password_verifies_against_its_hash(self):
        hashed = hash_password("correct-horse-battery-staple")
        assert verify_password("correct-horse-battery-staple", hashed)

    def test_a_wrong_password_does_not_verify(self):
        hashed = hash_password("correct-horse")
        assert not verify_password("wrong-horse", hashed)

    def test_the_hash_is_salted(self):
        """Two users with the same password must not share a hash."""
        assert hash_password("same") != hash_password("same")

    def test_the_plaintext_never_appears_in_the_hash(self):
        assert "correct-horse" not in hash_password("correct-horse")

    def test_long_passwords_are_not_silently_truncated(self):
        """bcrypt ignores anything past 72 bytes; pre-hashing removes that
        limit, so two long passwords differing only at the end stay
        distinct."""
        base = "x" * 80
        hashed = hash_password(base + "aaa")
        assert verify_password(base + "aaa", hashed)
        assert not verify_password(base + "bbb", hashed)

    def test_a_malformed_stored_hash_reads_as_a_wrong_password(self):
        assert not verify_password("anything", "not-a-bcrypt-hash")
        assert not verify_password("anything", "")

    def test_unicode_passwords_work(self):
        hashed = hash_password("كلمة-المرور-سرية")
        assert verify_password("كلمة-المرور-سرية", hashed)
        assert not verify_password("كلمة-المرور", hashed)


class TestAccessTokens:
    def test_a_token_round_trips_its_claims(self):
        settings = make_settings()
        user_id = uuid.uuid4()

        token, expires_in = create_access_token(
            settings=settings, user_id=user_id, role=Role.BUYER, email="b@example.com"
        )
        claims = decode_access_token(settings=settings, token=token)

        assert claims["sub"] == str(user_id)
        assert claims["role"] == "buyer"
        assert claims["email"] == "b@example.com"
        assert expires_in == settings.jwt_expiry_minutes * 60

    def test_an_expired_token_is_refused(self):
        settings = make_settings(jwt_expiry_minutes=-1)
        token, _ = create_access_token(
            settings=settings, user_id=uuid.uuid4(), role=Role.BUYER, email="b@example.com"
        )
        with pytest.raises(AuthenticationError, match="expired"):
            decode_access_token(settings=settings, token=token)

    def test_a_token_signed_with_another_secret_is_refused(self):
        token, _ = create_access_token(
            settings=make_settings(jwt_secret="secret-one-long-enough-for-hs256"),
            user_id=uuid.uuid4(),
            role=Role.BUYER,
            email="b@example.com",
        )
        with pytest.raises(AuthenticationError, match="not valid"):
            decode_access_token(
                settings=make_settings(jwt_secret="secret-two-long-enough-for-hs256"),
                token=token,
            )

    def test_an_unsigned_token_is_refused(self):
        """The classic alg=none attack."""
        settings = make_settings()
        forged = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "role": "reviewer",
                "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            },
            key="",
            algorithm="none",
        )
        with pytest.raises(AuthenticationError):
            decode_access_token(settings=settings, token=forged)

    def test_garbage_is_refused(self):
        with pytest.raises(AuthenticationError):
            decode_access_token(settings=make_settings(), token="not.a.token")

    def test_a_token_without_an_expiry_is_refused(self):
        settings = make_settings()
        forever = jwt.encode(
            {"sub": str(uuid.uuid4()), "role": "buyer"},
            settings.jwt_secret.get_secret_value(),
            algorithm="HS256",
        )
        with pytest.raises(AuthenticationError):
            decode_access_token(settings=settings, token=forever)

    def test_a_token_with_an_unknown_role_is_refused(self):
        """A forged privilege must not decode, even when correctly signed."""
        settings = make_settings()
        token = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "role": "administrator",
                "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            },
            settings.jwt_secret.get_secret_value(),
            algorithm="HS256",
        )
        with pytest.raises(AuthenticationError):
            decode_access_token(settings=settings, token=token)

    def test_a_token_whose_subject_is_not_a_uuid_is_refused(self):
        settings = make_settings()
        token = jwt.encode(
            {
                "sub": "' OR 1=1 --",
                "role": "buyer",
                "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            },
            settings.jwt_secret.get_secret_value(),
            algorithm="HS256",
        )
        with pytest.raises(AuthenticationError):
            decode_access_token(settings=settings, token=token)


class TestProductionConfiguration:
    def test_production_refuses_a_short_jwt_secret(self):
        with pytest.raises(ValueError, match="at least 32 bytes"):
            Settings(
                environment="production",
                jwt_secret="too-short",
                database_url="sqlite+aiosqlite:///:memory:",
            )

    def test_production_refuses_the_development_default(self):
        with pytest.raises(ValueError, match="development default"):
            Settings(
                environment="production",
                jwt_secret="dev-only-insecure-secret",
                database_url="sqlite+aiosqlite:///:memory:",
            )

    def test_production_refuses_a_live_paypal_url(self):
        """This prototype is sandbox-only by design."""
        with pytest.raises(ValueError, match="sandbox"):
            Settings(
                environment="production",
                jwt_secret="a-production-secret-long-enough-for-hs256",
                paypal_base_url="https://api-m.paypal.com",
                database_url="sqlite+aiosqlite:///:memory:",
            )

    def test_a_valid_production_config_is_accepted(self):
        settings = Settings(
            environment="production",
            jwt_secret="a-production-secret-long-enough-for-hs256",
            database_url="postgresql+asyncpg://user:pass@db:5432/waseet",
        )
        assert settings.is_production

    def test_secrets_are_not_exposed_by_repr(self):
        settings = make_settings(paypal_client_secret="super-secret-value")
        assert "super-secret-value" not in repr(settings)
        assert "super-secret-value" not in str(settings.paypal_client_secret)


class TestConfidenceThresholdValidation:
    @pytest.mark.parametrize("threshold", ["0", "1.5", "-0.2"])
    def test_an_out_of_range_threshold_is_refused(self, threshold):
        with pytest.raises(ValueError):
            Settings(
                auto_release_confidence_threshold=threshold,
                database_url="sqlite+aiosqlite:///:memory:",
            )

    def test_an_out_of_range_fee_is_refused(self):
        with pytest.raises(ValueError):
            Settings(platform_fee_percent="150", database_url="sqlite+aiosqlite:///:memory:")
