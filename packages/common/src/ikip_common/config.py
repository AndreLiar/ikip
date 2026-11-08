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

    # --- Auth (Story 1.6) -----------------------------------------------
    # HS256 signing secret for dev-issued JWTs. In prod, auth is Entra ID (OIDC).
    # >= 32 chars per RFC 7518 §3.2 for HS256 (rejects a weak secret at startup).
    jwt_secret: SecretStr = Field(alias="JWT_SECRET", min_length=32)
    jwt_expire_minutes: int = Field(default=60, alias="JWT_EXPIRE_MINUTES")
    # Enables the dev-only token endpoint; must be False in prod.
    auth_dev_login: bool = Field(default=False, alias="AUTH_DEV_LOGIN")
    rate_limit_per_minute: int = Field(default=120, alias="RATE_LIMIT_PER_MINUTE", ge=1)

    # --- LLM observability: Langfuse Cloud (ADR 0013) -------------------
    langfuse_host: str = Field(default="https://cloud.langfuse.com", alias="LANGFUSE_HOST")
    langfuse_public_key: SecretStr | None = Field(default=None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: SecretStr | None = Field(default=None, alias="LANGFUSE_SECRET_KEY")

    # --- LLM + embeddings: Azure OpenAI / Foundry (ADR 0007/0010) -------
    # Optional until Epic 3 wires the LLMClient.
    azure_openai_endpoint: str | None = Field(default=None, alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: SecretStr | None = Field(default=None, alias="AZURE_OPENAI_API_KEY")
    azure_openai_api_version: str | None = Field(default=None, alias="AZURE_OPENAI_API_VERSION")
    azure_openai_embedding_deployment: str | None = Field(
        default=None, alias="AZURE_OPENAI_EMBEDDING_DEPLOYMENT"
    )
    # Embedding vector dimension. `text-embedding-3-small` is reduced to 512 via
    # Matryoshka so vectors fit Neon's storage budget (ADR 0020 / ADR 0015). This
    # is baked into the pgvector column type (`vector(512)`) — changing it is a
    # migration + versioned re-embedding, not a hot toggle.
    embedding_dimensions: int = Field(default=512, alias="EMBEDDING_DIMENSIONS")
    # Max texts per embeddings API call. Keep small on low Azure tiers (S0) to stay
    # under the per-minute call/token rate limit; a bigger quota allows larger batches.
    # 429s are retried with backoff regardless (ADR 0020 / dev-on-azure-cost-control).
    embedding_batch_size: int = Field(default=16, alias="EMBEDDING_BATCH_SIZE")

    # Chat model for grounded-answer generation (Story 3.5, ADR 0022). gpt-5.4-mini
    # is reasoning-capable; `reasoning_effort` tunes depth vs cost/latency ("minimal"
    # keeps it cheap/fast for grounded synthesis). Parameterized to swap the model.
    azure_openai_chat_deployment: str | None = Field(
        default=None, alias="AZURE_OPENAI_CHAT_DEPLOYMENT"
    )
    # Reasoning models (gpt-5.x, o-series) are tuned by reasoning_effort and fix
    # temperature at 1. Non-reasoning models (e.g. gpt-4.1-mini) accept an explicit
    # temperature instead. Only the relevant knob is sent per model (ADR 0022);
    # setting chat_temperature on a reasoning model is rejected at config time.
    chat_reasoning_effort: str = Field(default="minimal", alias="CHAT_REASONING_EFFORT")
    chat_temperature: float | None = Field(default=None, alias="CHAT_TEMPERATURE")

    @property
    def embedding_model_version(self) -> str:
        """Stable tag stored on every embedding row (e.g. 'text-embedding-3-small@512').
        Vectors are only comparable within the same model_version; re-embedding with a
        new one is additive, never destructive (FR14, ADR 0020)."""
        model = self.azure_openai_embedding_deployment or "unknown"
        return f"{model}@{self.embedding_dimensions}"


@lru_cache
def get_settings() -> Settings:
    """Return the cached Settings singleton (loaded once per process)."""
    return Settings()  # type: ignore[call-arg]  # values come from env/.env
