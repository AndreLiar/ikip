# Concept — Authentication, authorization & RBAC

_Write-once concept note. First used by [MISSION-005](../missions/MISSION-005/mission.md). Reused by every protected endpoint._

## Three distinct ideas (often conflated)
- **Authentication (authn)** — *who are you?* Prove identity (a signed token).
- **Authorization (authz)** — *what may you do?* Check permission for an action.
- **RBAC** — a way to do authz by **role** (admin/manager/technician) instead of per-user rules.

## The `Principal`: identity + tenant + role
Every authenticated request acts as a **Principal**: `user_id`, `tenant_id`, `role`. Carrying `tenant_id` *in the token* is what lets us **authorize before retrieval** and bind the request to one tenant (FR21) — it pairs directly with the tenant-scoped repository ([multi-tenancy](./multi-tenancy.md)).

## JWT in one minute
A **JWT** (JSON Web Token) is `header.payload.signature`, base64url-encoded:
- **payload** = claims: `sub` (user), `tenant_id`, `role`, `iat` (issued), `exp` (expiry).
- **signature** = HMAC of header+payload with a secret (**HS256**). The server re-computes it to verify the token wasn't forged or altered.
- It is **signed, not encrypted** — never put secrets in the payload; anyone can read it, only the server can *trust* it.
- `decode()` fails (we raise `AuthError`) on bad signature, expiry, or malformed claims.

> HS256 secret must be **≥ 32 bytes** (RFC 7518 §3.2). IKIP validates this in `Settings` so a weak secret fails at startup.

## IKIP's wiring (Story 1.6)
- **Pure primitives** in `ikip_common.auth` (`Principal`, `encode_token`, `decode_token`, `has_role`) — framework-agnostic, unit-testable without FastAPI.
- **FastAPI dependencies** in `apps/api/auth.py`:
  - `get_current_principal` extracts the `Bearer` token and returns a `Principal` (**401** if missing/invalid). This is the reusable authentication dependency.
  - `require_role(min_role)` is a **dependency factory** for RBAC (**403** if under-privileged).
- **Role hierarchy** (admin > manager > technician): `has_role(required)` is `order[role] >= order[required]`, so `require_role(manager)` also admits admins.

```python
@app.get("/api/v1/me")
def me(principal: CurrentPrincipal): ...          # any authenticated user

@app.get("/api/v1/admin/ping")
def admin_ping(p: Annotated[Principal, Depends(require_role(UserRole.admin))]): ...
```

## Dev vs prod login
- **Dev:** a guarded `POST /auth/dev-token` mints HS256 tokens for local accounts (enabled by `AUTH_DEV_LOGIN`, **off in prod**). Lets us develop/test without an identity provider.
- **Prod:** **Microsoft Entra ID (OIDC)** — validate Entra-issued tokens (JWKS, RS256, issuer/audience) instead of minting our own. The `Principal`/dependency surface stays the same; only token *validation* changes. (Deferred — the dev-token path is replaced, not the authz model.)

## Rules to remember
1. Authenticate **once** via the dependency; never parse tokens ad-hoc in handlers.
2. Authorize with `require_role(...)` on the endpoint — don't scatter role `if`s in business logic.
3. 401 = not authenticated · 403 = authenticated but not allowed. Don't leak *why* beyond that.
4. Token carries `tenant_id` → use it to scope data (repository), never trust a tenant id from the request body.
5. Never log tokens or secrets; secrets are `SecretStr`.

## Related
- [multi-tenancy](./multi-tenancy.md) (tenant_id from the Principal drives repo scoping) · [config-12-factor](./config-12-factor.md) (JWT secret) · [health-checks](./health-checks.md).
- [ADR 0007](../../adr/0007-pluggable-llm-client-azure-openai.md)/[ADR 0010](../../adr/0010-foundry-model-platform-no-dedicated-ai-gateway.md) context; Entra ID is the prod IdP (brief/architecture).
