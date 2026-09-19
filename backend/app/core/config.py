"""Application configuration.

All runtime configuration is environment driven so the same image can be
promoted across dev / qualification / production environments without a
rebuild -- a hard requirement for computerised systems under GxP.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Identity ─────────────────────────────────────────────────────────────
    app_name: str = "AIVOA Complaint Intelligence"
    environment: Literal["development", "qualification", "production"] = "development"
    api_prefix: str = "/api/v1"
    debug: bool = True

    # ── Persistence ──────────────────────────────────────────────────────────
    # Postgres in compose / production; SQLite keeps `git clone && run` viable.
    database_url: str = "sqlite+pysqlite:///./aivoa.db"
    sql_echo: bool = False

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalise_database_url(cls, value: str) -> str:
        """Managed Postgres providers (Render, Railway, Heroku, Supabase) hand
        back a bare `postgres://` or `postgresql://` connection string.
        SQLAlchemy needs an explicit driver on that scheme, and this project
        standardises on `psycopg` (v3), not the legacy `psycopg2` most blog
        posts assume -- so normalise it here rather than relying on every
        deployment target to know that detail."""
        if not isinstance(value, str):
            return value
        if value.startswith("postgres://"):
            return "postgresql+psycopg://" + value[len("postgres://"):]
        if value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value[len("postgresql://"):]
        return value

    # ── Groq / LLM ───────────────────────────────────────────────────────────
    groq_api_key: str | None = None
    # The assignment mandates gemma2-9b-it (extraction) and
    # llama-3.3-70b-versatile (reasoning). As of this build, Groq has
    # decommissioned gemma2-9b-it outright (verified: HTTP 400
    # model_decommissioned) and gated llama-3.3-70b-versatile behind an
    # Enterprise-tier account (verified: HTTP 404 against a standard key).
    # Both are confirmed dead ends for a fresh reviewer key, not just this
    # one, so the defaults below point at the nearest current equivalents on
    # Groq -- openai/gpt-oss-20b (fast, small) for extraction and
    # openai/gpt-oss-120b (larger, higher quality) for reasoning -- and both
    # env vars remain fully overridable for a deployment that does have
    # access to the originally-named models. See docs/DEPLOYMENT.md, Step 0.
    extraction_model: str = "openai/gpt-oss-20b"
    reasoning_model: str = "openai/gpt-oss-120b"
    llm_temperature: float = 0.1
    llm_max_retries: int = 2
    llm_timeout_seconds: float = 45.0

    # ── Ingestion limits ─────────────────────────────────────────────────────
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB, matches UI copy
    max_document_chars: int = 24_000

    # ── Duplicate detection ──────────────────────────────────────────────────
    duplicate_score_threshold: float = 0.62
    duplicate_lookback_days: int = 540

    # ── CORS ─────────────────────────────────────────────────────────────────
    # NoDecode: accept a plain comma-separated string from the environment
    # instead of pydantic-settings' default JSON decoding.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
        ]
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value):
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    @property
    def llm_enabled(self) -> bool:
        """When no key is configured the agent falls back to its
        deterministic heuristic engine so the product still demos end-to-end."""
        return bool(self.groq_api_key and self.groq_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
