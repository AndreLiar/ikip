"""Typed, 12-factor configuration for IKIP (Story 1.2).

All backend connections come from the environment / `.env` — never hard-coded.
Required values missing -> fail fast at load with a clear error (no silent defaults
for credentials). Secrets are typed as `SecretStr` so they never appear in logs/repr.

Backends (all managed by default — ADR 0012/0014/0015/0009/0013):
  - DATABASE_URL        Neon Postgres + pgvector
  - R2_*                Cloudflare R2 (S3-compatible object storage)
  - REDIS_URL           Redis Cloud / Docker (cache + job queue)
  - LANGFUSE_*          Langfuse Cloud (LLM observability)
  - AZURE_OPENAI_*      Azure OpenAI / Foundry (optional until Epic 3)
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment / `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # --- Database: Neon Postgres + pgvector (ADR 0015) -------------------
    database_url: str = Field(alias="DATABASE_URL")

    # --- Object storage: Cloudflare R2 (ADR 0014) -----------------------
    r2_account_id: str = Field(alias="R2_ACCOUNT_ID")
    r2_endpoint: str = Field(alias="R2_ENDPOINT")
    r2_bucket: str = Field(alias="R2_BUCKET")
    r2_region: str = Field(default="auto", alias="R2_REGION")
    r2_access_key_id: SecretStr = Field(alias="R2_ACCESS_KEY_ID")
    r2_secret_access_key: SecretStr = Field(alias="R2_SECRET_ACCESS_KEY")

    # --- Cache + job queue: Redis (ADR 0009) ----------------------------
    redis_url: str = Field(alias="REDIS_URL")

    # --- LLM observability: Langfuse Cloud (ADR 0013) -------------------
    langfuse_host: str = Field(default="https://cloud.langfuse.com", alias="LANGFUSE_HOST")
    langfuse_public_key: SecretStr | None = Field(default=None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: SecretStr | None = Field(default=None, alias="LANGFUSE_SECRET_KEY")

    # --- LLM + embeddings: Azure OpenAI / Foundry (ADR 0007/0010) -------
    # Optional until Epic 3 wires the LLMClient.
    azure_openai_endpoint: str | None = Field(default=None, alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: SecretStr | None = Field(default=None, alias="AZURE_OPENAI_API_KEY")
    azure_openai_api_version: str | None = Field(default=None, alias="AZURE_OPENAI_API_VERSION")


@lru_cache
def get_settings() -> Settings:
    """Return the cached Settings singleton (loaded once per process)."""
    return Settings()  # type: ignore[call-arg]  # values come from env/.env
