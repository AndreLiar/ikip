# MISSION-005 — Execution log

Labels: `[verified]` = run with observed output · `[proposed]` = not run here.

## Steps
1. **Config** `[verified]` — added `jwt_secret` (SecretStr, min_length 32), `jwt_expire_minutes`, `auth_dev_login` to Settings; `.env`/`.env.example` auth vars (dev JWT secret generated with `secrets.token_urlsafe`).
2. **Pure auth primitives** `[verified]` — `ikip_common/auth.py`: `Principal`, `encode_token`/`decode_token` (PyJWT HS256), role hierarchy `has_role`, `AuthError`.
3. **FastAPI wiring** `[verified]` — `apps/api/auth.py`: `get_current_principal` (401), `require_role` factory (403), guarded `/auth/dev-token`. `main.py`: protected `/me` + `/admin/ping`.
4. **Updated existing tests** `[verified]` — config/health tests now provide `JWT_SECRET` (now required).
5. **Auth tests** `[verified]` — `test_auth.py` (9): token round-trip, bad-signature, expiry, role hierarchy; endpoints 401/403/200 + tenant binding.
6. **ruff B008 fix** `[verified]` — `Depends(require_role(...))` in a default tripped B008; switched to `Annotated[Principal, Depends(...)]` (modern FastAPI style).
7. **JWT key-length warning → validation** `[verified]` — PyJWT warned <32-byte HS256 key; added `min_length=32` to `jwt_secret` and lengthened dummy test secrets. Warnings cleared.
8. **Live end-to-end** `[verified]` — ran uvicorn, exercised the flow:
   ```
   1. GET /me no token      -> 401
   3. GET /me (technician)  -> role technician | tenant match: True
   4. GET /admin/ping tech  -> 403
   5. GET /admin/ping admin -> 200 {'pong': 'admin'}
   ```

## Validation summary
- 9 auth tests pass (unit + integration) `[verified]`
- Full suite: 17 passed, 3 skipped `[verified]`
- Live 401/403/200 + tenant binding `[verified]`
- ruff lint+format green `[verified]`

## Rollback
Additive (new auth modules + endpoints + config fields). Revert branch/commit. No data touched.

## Follow-up (prod)
Replace `/auth/dev-token` with Microsoft Entra ID OIDC validation (JWKS/RS256, issuer/audience); keep `AUTH_DEV_LOGIN=false` in prod.
