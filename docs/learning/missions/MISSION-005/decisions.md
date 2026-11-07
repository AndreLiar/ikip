# MISSION-005 — Decisions

## D1 — JWT (HS256) for dev; Entra ID (OIDC) for prod
- **Choice:** mint our own HS256 JWTs in dev (`/auth/dev-token`); validate Microsoft Entra ID OIDC tokens in prod.
- **Why here:** lets us build/test auth now without standing up an IdP; prod uses the enterprise IdP from the architecture. The `Principal` + dependency surface is identical — only token *validation* swaps.
- **Alternative:** Entra ID from day one (needs a tenant/app registration to develop) or sessions/cookies.
- **Trade-off:** two token paths; the dev path must be **disabled in prod** (`AUTH_DEV_LOGIN=false`) or it's a backdoor.
- **Switch when:** wiring prod → implement OIDC/JWKS validation and drop the dev-token route.

## D2 — Pure primitives (ikip_common.auth) + FastAPI wiring (apps/api/auth.py)
- **Choice:** token encode/decode + role logic are framework-free in `ikip_common`; FastAPI `Depends` wrappers live in the app.
- **Why here:** the core is unit-testable without HTTP; other services (workers) can reuse it; matches ports/clean-boundary style.
- **Trade-off:** a thin extra layer.

## D3 — Role hierarchy via `require_role(min_role)` dependency factory
- **Choice:** ordered roles (technician<manager<admin); `require_role(m)` admits anyone `>= m`.
- **Why here:** one reusable dependency instead of per-endpoint role `if`s; admins implicitly pass manager/technician gates.
- **Alternative:** explicit permission/scopes system (finer-grained).
- **Trade-off:** coarse-grained; fine for MVP. Scopes/permissions can layer on later.

## D4 — Enforce `JWT_SECRET` length (>=32) in Settings
- **Choice:** `jwt_secret: SecretStr = Field(min_length=32)`.
- **Why here:** PyJWT warns that <32-byte HS256 keys are insecure (RFC 7518 §3.2); validating at startup turns a silent warning into a fail-fast config error.
- **Lesson:** library warnings often encode a real rule — promote them to validation.

## D5 — `has_role` not `role ==`
- **Choice:** compare on the hierarchy, never equality.
- **Why here:** `role == admin` would wrongly exclude a higher role from a lower gate; hierarchy is the correct model for "at least".
