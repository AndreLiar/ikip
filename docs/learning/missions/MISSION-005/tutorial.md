# MISSION-005 — Reproduction tutorial

Add JWT auth + RBAC to the FastAPI app.

## Prerequisites
- MISSIONs 001–004 done; `uv`; a `JWT_SECRET` (>=32 chars) in `.env`:
  `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

## Steps

1. **Config** — add to `Settings`: `jwt_secret: SecretStr = Field(alias="JWT_SECRET", min_length=32)`, `jwt_expire_minutes`, `auth_dev_login: bool`. Add `pyjwt>=2.9` to `ikip-common` deps.

2. **Pure primitives** `ikip_common/auth.py`:
   - `@dataclass(frozen=True) class Principal: user_id, tenant_id, role` + `has_role(required)` using an ordered role map.
   - `encode_token(principal, secret, expires_minutes)` → PyJWT `encode` (HS256) with claims `sub/tenant_id/role/iat/exp`.
   - `decode_token(token, secret)` → `jwt.decode`; wrap `PyJWTError` in `AuthError`; rebuild `Principal` from claims.

3. **FastAPI wiring** `apps/api/auth.py`:
   - `get_current_principal(authorization: Header)` → 401 if no `Bearer`; else `decode_token(...)` (401 on `AuthError`). Export `CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]`.
   - `require_role(min_role)` returns a dep that 403s if `not principal.has_role(min_role)`.
   - `POST /auth/dev-token` — 404 if `not settings.auth_dev_login`; else mint a token.

4. **Protect endpoints** `main.py`:
   ```python
   @app.get("/api/v1/me")
   def me(principal: CurrentPrincipal): ...
   @app.get("/api/v1/admin/ping")
   def admin_ping(p: Annotated[Principal, Depends(require_role(UserRole.admin))]): ...
   ```

5. **Tests** `apps/api/tests/test_auth.py` — unit: round-trip, bad-signature, expiry, hierarchy. Integration (`TestClient`): `/me` 401 without token; mint via `/auth/dev-token`; `/me` 200 + tenant match; technician→`/admin` 403; admin→`/admin` 200.
   ```bash
   uv run pytest apps packages -q    # all green
   ```

6. **Run it** (optional)
   ```bash
   uv run uvicorn ikip_api.main:app --port 8000
   TOK=$(curl -s localhost:8000/api/v1/auth/dev-token -H 'content-type: application/json' -d '{"tenant_id":"...","role":"admin"}' | jq -r .access_token)
   curl -s localhost:8000/api/v1/me -H "Authorization: Bearer $TOK"
   ```

## Common mistakes
- **B008 ruff error** → don't call `Depends(...)` in a default; use `Annotated[T, Depends(...)]`.
- **PyJWT InsecureKeyLength warning** → HS256 secret must be ≥32 bytes; validate in Settings.
- **`role ==` for gates** → use the hierarchy (`has_role`) so higher roles pass lower gates.
- **dev-token in prod** → guard with `AUTH_DEV_LOGIN` and keep it `false` in prod (else backdoor).
- **Trusting a body `tenant_id`** → take tenant from the token's `Principal`, not the request body.

## Recovery
Additive; revert the branch/commit. No data touched.
