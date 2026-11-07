"""IKIP FastAPI application (Story 1.3).

App factory wires structured logging, loads settings (fail-fast), and mounts the
versioned API under `/api/v1`.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, FastAPI
from ikip_common import get_settings
from ikip_common.auth import Principal
from ikip_common.db.models import UserRole
from pydantic import BaseModel

from ikip_api import auth, health, retrieval
from ikip_api.auth import CurrentPrincipal, require_role
from ikip_api.logging_config import configure_logging

API_V1_PREFIX = "/api/v1"


class WhoAmI(BaseModel):
    user_id: str
    tenant_id: str
    role: str


def create_app() -> FastAPI:
    configure_logging()
    # Load settings once at startup — fail fast on missing required config.
    get_settings()
    logging.getLogger("ikip_api").info("starting ikip-api")

    app = FastAPI(title="IKIP API", version="0.1.0")
    app.include_router(health.router, prefix=API_V1_PREFIX, tags=["health"])
    app.include_router(auth.router, prefix=API_V1_PREFIX)
    app.include_router(retrieval.router, prefix=API_V1_PREFIX)

    @app.get(f"{API_V1_PREFIX}/me", response_model=WhoAmI, tags=["auth"])
    def whoami(principal: CurrentPrincipal) -> WhoAmI:
        return WhoAmI(
            user_id=str(principal.user_id),
            tenant_id=str(principal.tenant_id),
            role=principal.role.value,
        )

    @app.get(f"{API_V1_PREFIX}/admin/ping", tags=["auth"])
    def admin_ping(
        principal: Annotated[Principal, Depends(require_role(UserRole.admin))],
    ) -> dict[str, str]:
        return {"pong": principal.role.value}

    return app


app = create_app()
