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
    # A sandbox access token supplied directly — the same one the PayPal AI
    # Toolkit mints into ~/.claude/settings.json. When set, the server uses it
    # for REST calls instead of doing its own OAuth exchange; it cannot be
    # refreshed, so on a 401 the client falls back to the client id/secret.
    paypal_sandbox_access_token: SecretStr = SecretStr("")

    # --- AI ---------------------------------------------------------------
    # Which provider backs the judgment agents. All three run the same
    # agent logic and guardrails (app/integrations/ai/base.py); only the API
    # call differs. USE_STUB_AI overrides this for a keyless demo.
    ai_provider: Literal["anthropic", "gemini"] = "anthropic"
    ai_timeout_seconds: float = 45.0

    # Anthropic
    anthropic_api_key: SecretStr = SecretStr("")

    # Gemini (Google)
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.8-flash"

    # The model id used for whichever provider is selected. Left unset, it
    # defaults to that provider's sensible default.
    ai_model_override: str = ""

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

    # --- Email notifications ----------------------------------------------
    # Real email on lifecycle events. Off by default; with a Gmail address and
    # an App Password (not the account password) it sends through Gmail SMTP.
    # Disabled, the console gateway just logs what would have been sent.
    email_enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = ""
    smtp_starttls: bool = True
    # Used to build links back into the app from an email.
    app_base_url: str = "http://localhost:3000"

    # --- Channel3 product catalog -----------------------------------------
    # Powers "Shop & Escrow": search a real product catalog to start a deal
    # from. Without a key, a small stub catalog stands in so the demo works.
    channel3_api_key: SecretStr = SecretStr("")
    channel3_base_url: str = "https://api.trychannel3.com/v1"

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
    def paypal_token_configured(self) -> bool:
        """Whether a ready-made sandbox access token was supplied."""
        return bool(self.paypal_sandbox_access_token.get_secret_value())

    @property
    def email_configured(self) -> bool:
        """Whether Gmail SMTP has enough to actually send."""
        return bool(
            self.email_enabled
            and self.smtp_host
            and self.smtp_username
            and self.smtp_password.get_secret_value()
        )

    @property
    def email_from_address(self) -> str:
        return self.smtp_from.strip() or self.smtp_username.strip()

    @property
    def catalog_configured(self) -> bool:
        """Whether a real Channel3 key is set; otherwise the stub stands in."""
        return bool(self.channel3_api_key.get_secret_value().strip())

    @property
    def ai_configured(self) -> bool:
        """Whether the Anthropic provider has a key (kept for the Anthropic
        gateway and its tests)."""
        return bool(self.anthropic_api_key.get_secret_value())

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key.get_secret_value())

    @property
    def provider_configured(self) -> bool:
        """Whether the selected provider has credentials."""
        if self.use_stub_ai:
            return True
        return self.gemini_configured if self.ai_provider == "gemini" else self.ai_configured

    @property
    def ai_model(self) -> str:
        """The model id for the selected provider, honouring an override."""
        if self.ai_model_override:
            return self.ai_model_override
        return self.gemini_model if self.ai_provider == "gemini" else "claude-sonnet-5"


@lru_cache
def get_settings() -> Settings:
    """Cached so the environment is read once per process."""
    return Settings()
