"""Health endpoint (Story 1.3 AC1).

`GET /api/v1/health` reports the API status plus the status of each configured
backend (Neon/Postgres, R2, Redis, Langfuse), reusing the connectivity checks
from `ikip_common.doctor`. Readiness semantics: 200 when healthy, 503 when any
dependency check fails. Dependency checks are mockable (tests patch `run_checks`)
so CI needs no live managed services.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Response, status
from ikip_common.doctor import CheckResult, run_checks
from pydantic import BaseModel

router = APIRouter()

SERVICE_NAME = "ikip-api"
VERSION = "0.1.0"


class DependencyStatus(BaseModel):
    service: str
    ok: bool | None  # None = skipped (e.g. optional backend not configured)
    detail: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    dependencies: list[DependencyStatus]


def _to_status(results: list[CheckResult]) -> HealthResponse:
    deps = [DependencyStatus(service=r.service, ok=r.ok, detail=r.detail) for r in results]
    degraded = any(r.ok is False for r in results)
    return HealthResponse(
        status="degraded" if degraded else "ok",
        service=SERVICE_NAME,
        version=VERSION,
        dependencies=deps,
    )


@router.get("/health", response_model=HealthResponse)
def health(response: Response) -> HealthResponse:
    body = _to_status(run_checks())
    response.status_code = (
        status.HTTP_503_SERVICE_UNAVAILABLE if body.status == "degraded" else status.HTTP_200_OK
    )
    return body
