"""
app/core/config.py
──────────────────
Centralised, typed application configuration via Pydantic Settings v2.

All values are read from environment variables or a .env file.
Secrets are never logged.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from typing import Any, List, Optional

from pydantic import (
    AnyHttpUrl,
    EmailStr,
    PostgresDsn,
    RedisDsn,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings.

    Environment variables are resolved in this order:
    1. OS environment
    2. .env file (if present)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ───────────────────────────────────────────────────────────
    APP_NAME: str = "RiskIntel Public API"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"  # development | staging | production
    DEBUG: bool = False

    # ── Server ────────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8080

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalise_database_url(cls, v: Any) -> Any:
        """
        Accept the connection string a managed platform actually hands out.

        Render (and Heroku, and Neon, and every other managed Postgres) supplies
        `postgresql://…`, sometimes `postgres://…`, usually with `?sslmode=…`
        appended. SQLAlchemy reads the scheme as the driver: `postgresql://`
        means psycopg2, which is not installed, so the process dies on the first
        connection attempt with a driver error that says nothing about the real
        cause. `sslmode` is a libpq spelling that asyncpg rejects outright.

        Rather than requiring a human to hand-edit a secret into a different
        dialect — a step that is easy to forget and invisible until deploy —
        the translation happens here, once, in the one place the URL enters the
        application.

        `postgresql+asyncpg://` supplied explicitly is left exactly as it is.
        """
        if not isinstance(v, str) or not v.strip():
            return v

        url = v.strip()

        # Driver: only rewrite when no dialect was named.
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url[len("postgresql://"):]

        if "+asyncpg" not in url or "sslmode=" not in url:
            return url

        # TLS: translate libpq's `sslmode` to the spelling asyncpg understands.
        # The modes that require encryption become `ssl=require`; the modes that
        # merely permit it are dropped, because asyncpg negotiates TLS when the
        # server offers it anyway.
        from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

        parts = urlsplit(url)
        kept: list[tuple[str, str]] = []
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            if key != "sslmode":
                kept.append((key, value))
            elif value in {"require", "verify-ca", "verify-full"}:
                kept.append(("ssl", "require"))
        return urlunsplit(parts._replace(query=urlencode(kept)))

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Password / Token expiry ───────────────────────────────────────────────
    EMAIL_VERIFICATION_EXPIRE_HOURS: int = 24
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_DEFAULT: str = "100/minute"
    RATE_LIMIT_AUTH: str = "10/minute"

    # ── Email (SMTP) ──────────────────────────────────────────────────────────
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USE_TLS: bool = True
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAIL_FROM_ADDRESS: Optional[EmailStr] = None
    EMAIL_FROM_NAME: str = "RiskIntel"

    @field_validator(
        "SMTP_HOST",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "EMAIL_FROM_ADDRESS",
        mode="before",
    )
    @classmethod
    def empty_string_means_unset(cls, v: Any) -> Any:
        """
        Treat an empty environment variable as absent.

        Container platforms and Compose have no way to express "not set" for a
        declared variable: `${SMTP_HOST:-}` produces an empty string, and so
        does an unfilled field in a dashboard. Without this, an empty
        EMAIL_FROM_ADDRESS fails EmailStr validation and the process exits at
        import time — a deployment that dies on startup because optional mail
        settings were left blank, which is the expected state when SMTP is not
        configured.
        """
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    # ── Security ──────────────────────────────────────────────────────────────
    MAX_REQUEST_SIZE: int = 1_048_576  # 1 MB
    TRUSTED_PROXIES: List[str] = ["127.0.0.1/8"]

    @field_validator("TRUSTED_PROXIES", mode="before")
    @classmethod
    def parse_proxies(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return v

    # ── File Storage ──────────────────────────────────────────────────────────
    RELEASE_FILES_BASE_PATH: str = "/data/releases"

    # ── Derived helpers ───────────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV.lower() == "development"

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> "Settings":
        """Enforce that production environments never use placeholder secrets."""
        if self.is_production:
            if not self.JWT_SECRET_KEY or len(self.JWT_SECRET_KEY) < 32:
                raise ValueError(
                    "JWT_SECRET_KEY must be at least 32 characters in production."
                )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return a cached singleton Settings instance.
    Thread-safe via CPython's GIL + lru_cache.
    """
    return Settings()
