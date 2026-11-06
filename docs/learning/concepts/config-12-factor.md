# Concept — 12-factor configuration (env + Pydantic Settings)

_Write-once concept note. First used by [MISSION-002](../missions/MISSION-002/mission.md). Reused by every service that reads config._

## The principle (12-factor, factor III)
**Config lives in the environment, not in code.** Anything that varies between dev/staging/prod — connection strings, keys, endpoints — comes from environment variables (loaded from `.env` in dev, from the secrets manager in prod). Benefits:
- the **same build** runs in any environment (just different env),
- **secrets never get committed** (only `.env.example` with placeholders is tracked),
- changing a backend (Neon → local Postgres) is a config switch, not a code change — which is exactly what the ports & adapters design ([ADR 0003](../../adr/0003-local-first-ports-and-adapters.md)) relies on.

## Why a typed Settings class (not raw `os.environ`)
Reading `os.environ["DATABASE_URL"]` ad-hoc scatters config access, gives no validation, and fails *late* (deep in a request) when a var is missing. A **Pydantic `BaseSettings`** class centralizes it:
- **Typed + validated** — wrong/missing values are caught at load.
- **Fail-fast** — a missing required var raises at startup with a clear message, not at 2 a.m. in production.
- **One source of truth** — api + services import the same `Settings`.

### Shape (IKIP's `ikip_common.config`)
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")
    database_url: str = Field(alias="DATABASE_URL")              # required -> fail fast
    r2_region: str = Field(default="auto", alias="R2_REGION")    # optional -> default
    r2_secret_access_key: SecretStr = Field(alias="R2_SECRET_ACCESS_KEY")  # masked
```
- `alias=` maps a field to its ENV name (`R2_REGION`), keeping Pythonic attribute names.
- **No default on a credential** = required = fail-fast if absent.
- **`SecretStr`** — the key is masked in `repr()`/`str()`/logs (`SecretStr('**********')`); read it only via `.get_secret_value()`. This is the single most important habit for not leaking secrets.
- `get_settings()` is `@lru_cache`d — parsed once per process.

## Keeping secrets out of git
- `.env` is **gitignored**; only `.env.example` (placeholders) is committed.
- CI greps for **secret assignments** (`KEY=value`), not identifiers — so `alias="AZURE_OPENAI_API_KEY"` in code is fine, but `AZURE_OPENAI_API_KEY=sk-…` fails the build.
- A real scanner (gitleaks) is added in Epic 6 / Story 6.4.

## Testing config without live services
Unit tests must be **hermetic** (run in CI without secrets). Pattern:
```python
def test_x(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db"); ...
    Settings(_env_file=None)   # _env_file=None disables reading the real .env
```
`_env_file=None` is the key: it ignores the developer's `.env` so the test depends only on the monkey-patched env.

## Related
- Verifying the *actual* backends (not config) = the **connectivity doctor** (`ikip_common.doctor`) — a dev/ops tool, separate from config.
- Tooling (uv groups, ruff, pytest): [concepts/dev-tooling.md](./dev-tooling.md).
- [ADR 0003](../../adr/0003-local-first-ports-and-adapters.md) ports (config feeds the adapters) · [ADR 0012](../../adr/0012-local-first-dev-cloud-models-only.md) managed-first.
