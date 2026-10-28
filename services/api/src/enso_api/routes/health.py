"""Health and readiness endpoints.

* `/health` (Liveness): reports only that the API process is alive.
* `/health/ready` (Readiness): checks dependent services (database) before
  declaring the service ready to receive operational traffic.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from enso_api import __version__
from enso_api.config import Settings
from enso_api.db import check_database_readiness

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


class DatabaseStatus(BaseModel):
    status: Literal["connected", "unreachable", "disabled"]
    latency_ms: float | None = None
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    database: DatabaseStatus


@router.get("/health", response_model=HealthResponse)
def health_liveness(response: Response) -> HealthResponse:
    """Liveness probe: verifies the API process is running."""
    response.headers["Cache-Control"] = "no-store"
    return HealthResponse(status="ok", service="enso-shield-api", version=__version__)


@router.get("/health/ready", response_model=ReadinessResponse)
async def health_readiness(request: Request, response: Response) -> Any:
    """Readiness probe: verifies process state and database responsiveness."""
    response.headers["Cache-Control"] = "no-store"
    settings: Settings = request.app.state.settings

    db_check = await check_database_readiness(settings)
    db_status = DatabaseStatus(
        status=db_check["status"],
        latency_ms=db_check.get("latency_ms"),
        detail=db_check.get("detail"),
    )

    is_ready = db_status.status in ("connected", "disabled")
    overall_status: Literal["ok", "degraded"] = "ok" if is_ready else "degraded"

    if not is_ready:
        response.status_code = 503

    return ReadinessResponse(
        status=overall_status,
        service="enso-shield-api",
        version=__version__,
        database=db_status,
    )
