# MISSION-005 — Authentication & RBAC (Epic 1, Story 1.6)

**Mode:** Autonome + knowledge transfer.
**Objective:** authenticate a request into a `Principal` (user + tenant + role), enforce role-based access with a reusable dependency, and protect endpoints — closing the Epic 1 foundation.
**Maps to:** Epic 1 / Story 1.6.

## Acceptance criteria
1. Auth issues a session/token carrying tenant + role (dev accounts/OIDC; Entra ID in prod). — **[verified]** (`/auth/dev-token` mints HS256 JWT with `tenant_id` + `role`; prod = Entra ID OIDC, deferred)
2. Roles defined + enforced by a reusable authorization dependency. — **[verified]** (`UserRole` hierarchy; `require_role(min_role)` factory)
3. Protected endpoints reject unauthenticated/unauthorized. — **[verified live]** (401 no token, 403 technician→admin, 200 admin)
4. Unit + security tests cover role enforcement + tenant binding. — **[verified]** (9 auth tests pass)

## Deliverables
- `ikip_common/auth.py` — `Principal`, `encode_token`/`decode_token`, role hierarchy (`has_role`), `AuthError`. Pure, framework-agnostic.
- `apps/api/auth.py` — `get_current_principal` (401), `require_role` factory (403), guarded `POST /auth/dev-token`.
- `apps/api/main.py` — protected `/me` (any authed) and `/admin/ping` (admin-only).
- `config.py` — `jwt_secret` (SecretStr, min_length 32), `jwt_expire_minutes`, `auth_dev_login`.
- Tests: `apps/api/tests/test_auth.py` (9). `.env`/`.env.example` auth vars.
- Learning: [decisions.md](./decisions.md) · [execution.md](./execution.md) · [tutorial.md](./tutorial.md).

## Concepts
Introduces [auth-rbac](../../concepts/auth-rbac.md) (authn vs authz, JWT, Principal, role hierarchy, dev vs Entra ID). Reuses [multi-tenancy](../../concepts/multi-tenancy.md), [config-12-factor](../../concepts/config-12-factor.md).

## Related
Entra ID is the prod IdP (brief/architecture); the dev-token path is replaced by OIDC validation, not the authz model.
