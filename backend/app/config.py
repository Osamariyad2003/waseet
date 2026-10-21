"""Settings. Every secret comes from the environment — nothing is hardcoded,
nothing is logged, nothing is committed.
"""

from __future__ import annotations

import os
from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Which dotenv file to read, if any. Tests set WASEET_ENV_FILE to empty so a
# developer's real .env can never change a test outcome — without this the
# suite silently inherits whatever is in the working copy.
_ENV_FILE = os.environ.get("WASEET_ENV_FILE", ".env") or None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Runtime ----------------------------------------------------------
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"

    # --- PayPal (sandbox) -------------------------------------------------
    paypal_client_id: str = ""
    paypal_client_secret: SecretStr = SecretStr("")
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    paypal_webhook_id: str = ""
    paypal_seller_receiver_email: str = ""
    paypal_timeout_seconds: float = 15.0

    # --- AI ---------------------------------------------------------------
    anthropic_api_key: SecretStr = SecretStr("")
    ai_model: str = "claude-sonnet-5"
    ai_timeout_seconds: float = 45.0

    # --- Database ---------------------------------------------------------
    database_url: str = "postgresql+asyncpg://waseet:waseet@localhost:5434/waseet"

    # --- Auth -------------------------------------------------------------
    jwt_secret: SecretStr = SecretStr("dev-only-insecure-secret")
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 1440

    # --- Decision policy / settlement -------------------------------------
    auto_release_confidence_threshold: Decimal = Decimal("0.8")
    platform_fee_percent: Decimal = Decimal("0")

    # --- Deliverable inspection (FR-5) ------------------------------------
    # The verifier fetches the deliverable so it judges the work rather than
    # a link. The URL comes from the seller, so the fetcher refuses private
    # addresses and caps what it will download.
    enable_deliverable_fetch: bool = True
    content_fetch_timeout_seconds: float = 10.0
    content_max_bytes: int = 5_000_000
    content_max_text_chars: int = 20_000

    # --- Dev affordances --------------------------------------------------
    enable_webhook_simulator: bool = False
    # Replaces the AI gateway with fixed keyword rules so the product can be
    # clicked through without a model. Never real judgment.
    use_stub_ai: bool = False

    @field_validator("auto_release_confidence_threshold")
    @classmethod
    def _check_threshold(cls, value: Decimal) -> Decimal:
        if not (Decimal("0") < value <= Decimal("1")):
            raise ValueError("auto_release_confidence_threshold must be in (0, 1]")
        return value

    @field_validator("platform_fee_percent")
    @classmethod
    def _check_fee(cls, value: Decimal) -> Decimal:
        if not (Decimal("0") <= value <= Decimal("100")):
            raise ValueError("platform_fee_percent must be between 0 and 100")
        return value

    @model_validator(mode="after")
    def _check_production_secrets(self) -> Settings:
        """Refuse to boot a production instance on dev defaults."""
        if not self.is_production:
            return self
        secret = self.jwt_secret.get_secret_value()
        # The more specific complaint first: the dev default is also short,
        # and "you forgot to set it" is more useful than "it is too short".
        if secret == "dev-only-insecure-secret":
            raise ValueError("JWT_SECRET is still the development default")
        if len(secret.encode("utf-8")) < 32:
            raise ValueError(
                "JWT_SECRET must be at least 32 bytes in production (RFC 7518 minimum for HS256)"
            )
        if self.use_stub_ai:
            raise ValueError(
                "USE_STUB_AI cannot be enabled in production — it replaces every "
                "AI judgment with a fixed keyword rule"
            )
        if "sandbox" not in self.paypal_base_url:
            # This prototype is sandbox-only by design.
            raise ValueError("PAYPAL_BASE_URL must point at the PayPal sandbox")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def paypal_configured(self) -> bool:
        return bool(self.paypal_client_id and self.paypal_client_secret.get_secret_value())

    @property
    def ai_configured(self) -> bool:
        return bool(self.anthropic_api_key.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    """Cached so the environment is read once per process."""
    return Settings()
