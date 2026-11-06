"""IKIP FastAPI application (Story 1.3).

App factory wires structured logging, loads settings (fail-fast), and mounts the
versioned API under `/api/v1`.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from ikip_common import get_settings

from ikip_api import health
from ikip_api.logging_config import configure_logging

API_V1_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    configure_logging()
    # Load settings once at startup — fail fast on missing required config.
    get_settings()
    logging.getLogger("ikip_api").info("starting ikip-api")

    app = FastAPI(title="IKIP API", version="0.1.0")
    app.include_router(health.router, prefix=API_V1_PREFIX, tags=["health"])
    return app


app = create_app()
