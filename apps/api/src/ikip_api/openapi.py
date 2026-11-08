"""Dump the FastAPI OpenAPI schema (Story 4.1).

`uv run python -m ikip_api.openapi > apps/web/openapi.json`

Produces the stable contract the web client's TS types are generated from (see
apps/web `gen:api`). Uses placeholder settings so the dump needs no live backend.
"""

from __future__ import annotations

import json
import os
import sys

# Placeholder config so Settings() (fail-fast) loads without real backends — we only
# build the app object to read its schema, never connect anything.
_PLACEHOLDER = {
    "DATABASE_URL": "postgresql://u:p@localhost/db",
    "R2_ACCOUNT_ID": "x",
    "R2_ENDPOINT": "https://x.r2.cloudflarestorage.com",
    "R2_BUCKET": "x",
    "R2_ACCESS_KEY_ID": "x",
    "R2_SECRET_ACCESS_KEY": "x",
    "REDIS_URL": "redis://localhost:6379/0",
    "JWT_SECRET": "openapi-dump-placeholder-secret-0123456789",
}


def schema() -> dict:
    for key, value in _PLACEHOLDER.items():
        os.environ.setdefault(key, value)
    from ikip_api.main import create_app

    return create_app().openapi()


def main() -> None:
    json.dump(schema(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
