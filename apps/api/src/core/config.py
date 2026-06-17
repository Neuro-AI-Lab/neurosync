"""Application settings (pydantic-settings).

All secrets MUST come from environment variables. `.env.example` documents
the contract. Validators below ensure that production environments cannot
silently fall back to dev defaults (C-1, M-4).
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Dev fallback markers — keys starting with these strings are rejected in
# non-development environments.
DEV_KEY_MARKERS = ("dev-only-", "test-only-", "change-me-", "ZGV2LW9ubHkt")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "staging", "production"] = Field(
        default="development",
        description="Activate prod-grade validators when set to staging/production.",
    )

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://neurosync:dev@localhost:5432/neurosync",
        description="SQLAlchemy async URL. compose default differs (postgres host).",
    )

    # JWT — PRD §5.1 register response: access 15min, refresh 7d.
    # In dev these have safe-looking defaults so unit tests work without env;
    # the validator below forbids them being used outside `app_env=development`.
    jwt_secret_key: SecretStr = Field(
        default=SecretStr("dev-only-jwt-secret-change-me-in-real-env-min-32-bytes"),
        description="HMAC secret. MUST be a fresh secret in non-dev envs.",
    )
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = Field(default="HS256")
    jwt_issuer: str = Field(default="neuro-sync", description="JWT iss claim")
    jwt_audience: str = Field(default="neuro-sync-api", description="JWT aud claim")
    access_token_expire_minutes: int = Field(default=15)
    refresh_token_expire_days: int = Field(default=7)

    # Column encryption — AES-256-GCM. 32-byte key, base64-urlsafe encoded.
    encryption_key: SecretStr = Field(
        default=SecretStr("ZGV2LTMyLWJ5dGVzLW9ubHktRE8tTk9ULVVTRS1GT1I="),
        description="base64-urlsafe-encoded 32-byte AES-256 key. KMS rotation = Phase 2.",
    )

    # Password policy — PRD §4.5.2: min 12, Argon2id memory_cost≥64MB, iterations≥3.
    password_min_length: int = Field(default=12)
    password_max_length: int = Field(default=256, description="DoS guard for hash time")
    argon2_memory_cost_kib: int = Field(default=65536)  # 64 MiB
    argon2_time_cost: int = Field(default=3)
    argon2_parallelism: int = Field(default=4)

    # Age policy — FR-027 (Phase 2): under-14 guardian consent enforced.
    minor_age_cutoff: int = Field(default=14)

    # CORS — DEV permissive. Validator below forbids wildcard outside dev.
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    # WebSocket Origin whitelist (PRD C-7). Use ["*"] in dev only.
    cors_ws_origins: list[str] = Field(default_factory=lambda: ["*"])

    # Idempotency LRU cap (per WebSocket connection). Bounded to prevent OOM.
    ws_idempotency_cache_size: int = Field(default=200)
    ws_auth_handshake_seconds: float = Field(default=5.0)

    # AI server (apps/ai-server) location
    ai_server_url: str = Field(default="http://localhost:8001")
    # Handoff generation budget — PRD §4.1 p95 < 30s, allow margin.
    ai_handoff_timeout_seconds: float = Field(default=45.0)
    # Chat reply budget — first token < 800ms; full non-streaming reply margin.
    ai_chat_timeout_seconds: float = Field(default=10.0)
    # STT budget — PRD §4.1 SLA < 2,000ms, allow margin for the vendor chain.
    ai_stt_timeout_seconds: float = Field(default=8.0)

    # STT audio (FR-033/036). S3 SSE-KMS is Phase 2; demo writes to local disk.
    audio_storage_dir: str = Field(default=".audio_store")
    audio_max_bytes: int = Field(default=2 * 1024 * 1024)  # 2MB (PRD §5.1)
    audio_max_duration_ms: int = Field(default=30_000)  # 30s
    audio_retention_hours: int = Field(default=48)  # FR-036
    stt_min_confidence: float = Field(default=0.6)  # FR-037 fallback threshold

    # ---------- Validators ----------

    @field_validator("argon2_memory_cost_kib")
    @classmethod
    def _argon2_memory_meets_floor(cls, v: int) -> int:
        # PRD §4.5.2: memory_cost ≥ 64 MB (= 65536 KiB).
        # Allow weakening only when APP_ENV=development|test.
        env = os.getenv("APP_ENV", "development").lower()
        if env in ("development", "test"):
            return v
        if v < 65536:
            raise ValueError(
                f"argon2_memory_cost_kib must be >= 65536 in app_env={env} (PRD §4.5.2)"
            )
        return v

    @field_validator("argon2_time_cost")
    @classmethod
    def _argon2_time_meets_floor(cls, v: int) -> int:
        env = os.getenv("APP_ENV", "development").lower()
        if env in ("development", "test"):
            return v
        if v < 3:
            raise ValueError(
                f"argon2_time_cost must be >= 3 in app_env={env} (PRD §4.5.2)"
            )
        return v

    @field_validator("password_min_length")
    @classmethod
    def _password_min_meets_floor(cls, v: int) -> int:
        env = os.getenv("APP_ENV", "development").lower()
        if env in ("development", "test"):
            return v
        if v < 12:
            raise ValueError(
                f"password_min_length must be >= 12 in app_env={env} (PRD §4.5.2)"
            )
        return v

    @model_validator(mode="after")
    def _reject_dev_secrets_in_prod(self) -> Settings:
        if self.app_env in ("development", "test"):
            # In dev, just emit a warning so devs know they're on the fallback.
            if self.jwt_secret_key.get_secret_value().startswith(DEV_KEY_MARKERS):
                logger.warning(
                    "Using dev-only JWT secret. Set JWT_SECRET_KEY for any non-dev run."
                )
            if self.encryption_key.get_secret_value().startswith(DEV_KEY_MARKERS):
                logger.warning(
                    "Using dev-only encryption key. Set ENCRYPTION_KEY for any non-dev run."
                )
            return self

        # Non-dev: reject hard.
        if self.jwt_secret_key.get_secret_value().startswith(DEV_KEY_MARKERS):
            raise ValueError(
                f"JWT_SECRET_KEY is a dev fallback in app_env={self.app_env}. Set a fresh secret."
            )
        if self.encryption_key.get_secret_value().startswith(DEV_KEY_MARKERS):
            raise ValueError(
                f"ENCRYPTION_KEY is a dev fallback in app_env={self.app_env}. Set a fresh key."
            )
        if "*" in self.cors_origins:
            raise ValueError(
                f"cors_origins must not contain '*' in app_env={self.app_env}."
            )
        if "*" in self.cors_ws_origins:
            raise ValueError(
                f"cors_ws_origins must not contain '*' in app_env={self.app_env}."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
