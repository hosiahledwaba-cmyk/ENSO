"""FastAPI application factory."""

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure repo root is on sys.path for ml.* imports across environments
_REPO_ROOT = Path(__file__).resolve().parents[4]
if _REPO_ROOT.is_dir() and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from enso_api import __version__
from enso_api.config import Settings, get_settings
from enso_api.db import close_db, init_db
from enso_api.routes import (
    datasets,
    defense,
    experiments,
    features,
    forecast,
    health,
    ingestion,
    jobs,
    models,
    preparedness,
    security,
    system,
)
from enso_api.security import SecurityHeadersMiddleware

logger = logging.getLogger("enso_api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    await init_db(settings)

    # Initialize and start persistent daily climate data ingestion scheduler
    from enso_api.ingestion import get_ingestion_scheduler

    scheduler = get_ingestion_scheduler()
    scheduler.start()

    yield

    scheduler.shutdown()
    await close_db()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)

    app = FastAPI(
        title="ENSO Shield API",
        version=__version__,
        docs_url=None,  # Handled by custom route to display brand logo & favicon
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = settings

    static_dir = Path(__file__).resolve().parent / "static"

    from fastapi.responses import FileResponse, HTMLResponse

    @app.get("/favicon.ico", include_in_schema=False)
    @app.get("/favicon.png", include_in_schema=False)
    async def get_favicon() -> FileResponse:
        fav_path = static_dir / "favicon.png"
        return FileResponse(fav_path, media_type="image/png")

    @app.get("/logo.png", include_in_schema=False)
    async def get_logo() -> FileResponse:
        logo_path = static_dir / "logo.png"
        return FileResponse(logo_path, media_type="image/png")

    if settings.docs_enabled:
        from fastapi.openapi.docs import get_swagger_ui_html

        @app.get("/docs", include_in_schema=False)
        async def custom_swagger_ui() -> HTMLResponse:
            html_response = get_swagger_ui_html(
                openapi_url="/openapi.json",
                title="ENSO Shield API · Swagger UI",
                swagger_favicon_url="/favicon.png",
            )
            raw_body = html_response.body
            body_bytes = bytes(raw_body) if isinstance(raw_body, (bytes, memoryview)) else b""
            body = body_bytes.decode("utf-8")
            banner = (
                '<div style="background-color:#1F1F1F;padding:12px 24px;'
                'display:flex;align-items:center;gap:16px;border-bottom:3px solid #C96A3E;">'
                '<img src="/logo.png" alt="ENSO Shield" style="height:36px;'
                'object-fit:contain;background:#F7F4EF;padding:2px 8px;border-radius:4px;" />'
                '<span style="color:#F7F4EF;font-family:system-ui,-apple-system,sans-serif;'
                'font-weight:600;font-size:16px;letter-spacing:0.02em;">'
                "ENSO Shield · Climate Intelligence API Engine</span>"
                "</div>"
            )
            body = body.replace("<body>", f"<body>{banner}")
            return HTMLResponse(content=body)

    # Order: last added runs first. Host validation must reject before anything else.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Accept", "Content-Type"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.api_allowed_hosts)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Log details server-side; never leak internals to the client.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    app.include_router(health.router)
    app.include_router(system.router)
    app.include_router(datasets.router)
    app.include_router(features.router)
    app.include_router(models.router)
    app.include_router(experiments.router)
    app.include_router(forecast.router)
    app.include_router(defense.router)
    app.include_router(ingestion.router)
    app.include_router(jobs.router)
    app.include_router(preparedness.router)
    app.include_router(security.router)
    return app


app = create_app()
