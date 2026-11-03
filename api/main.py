"""Run with: python -m uvicorn api.main:app --host 127.0.0.1 --port 8000."""

import logging
from ipaddress import IPv4Address
from pathlib import Path
from time import monotonic
from uuid import uuid4

import psycopg
from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ingestion.ip_evidence import FEEDS
from vpnlens.config import ROOT, Settings
from vpnlens.database import SnapshotNotFound, SourcesUnavailable, read_connection
from vpnlens.service import lookup, source_status

from .models import LookupResponse

LOGGER = logging.getLogger("vpnlens.api")


def create_app(settings=None, frontend_dir=None):
    settings = settings or Settings.from_env()
    app = FastAPI(
        title="VPNLens",
        version="1.0.0",
        description="Local IPv4 geolocation, routing, organization ownership, and public-list evidence. "
        "Unknown evidence never means confirmed non-VPN or non-Tor.",
    )
    app.state.settings = settings
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET"],
            allow_headers=["Accept", "Content-Type"],
        )

    def connection():
        with read_connection(settings) as conn:
            yield conn

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        started = monotonic()
        request_id = str(uuid4())
        try:
            response = await call_next(request)
        except Exception as error:
            LOGGER.error("request_failed id=%s type=%s", request_id, type(error).__name__)
            response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
        response.headers["X-Request-ID"] = request_id
        LOGGER.info(
            "request id=%s method=%s status=%s duration_ms=%.2f",
            request_id,
            request.method,
            response.status_code,
            (monotonic() - started) * 1000,
        )
        return response

    @app.exception_handler(SnapshotNotFound)
    async def missing_snapshot(request, error):
        return JSONResponse(status_code=404, content={"detail": "Requested snapshot is not loaded"})

    @app.exception_handler(SourcesUnavailable)
    async def unavailable_source(request, error):
        return JSONResponse(
            status_code=503,
            content={"detail": "Required lookup data or database configuration is unavailable"},
        )

    @app.exception_handler(psycopg.Error)
    async def database_error(request, error):
        temporary = isinstance(
            error,
            (
                psycopg.OperationalError,
                psycopg.errors.UndefinedTable,
                psycopg.errors.UndefinedColumn,
                psycopg.errors.UndefinedFunction,
                psycopg.errors.InsufficientPrivilege,
            ),
        )
        LOGGER.error("database_request_failed type=%s", type(error).__name__)
        return JSONResponse(
            status_code=503 if temporary else 500,
            content={
                "detail": "Database unavailable or query timed out"
                if temporary
                else "Internal server error"
            },
        )

    @app.get("/health/live")
    def live():
        return {"status": "alive"}

    @app.get("/health/ready")
    def ready(conn=Depends(connection)):
        sources = source_status(conn, extended_enabled=settings.extended_evidence)
        if (
            not sources["geolocation"]["available"]
            or not sources["routing"]
            or not sources["organization"]
        ):
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "reason": "Core lookup datasets are not loaded",
                },
            )
        expected = {feed.source_id for feed in FEEDS} | set(
            sources.get("security_expected_source_ids", [])
        )
        recent = {item["source_id"] for item in sources["security"] if not item["stale"]}
        checked = len(expected & recent)
        return {
            "status": "ready" if expected <= recent else "degraded",
            "core_datasets_available": True,
            "recently_checked_security_sources": checked,
            "expected_security_sources": len(expected),
        }

    @app.get("/v1/sources")
    def sources(conn=Depends(connection)):
        return source_status(conn, extended_enabled=settings.extended_evidence)

    @app.get(
        "/v1/lookup/{ip_address}", response_model=LookupResponse, response_model_exclude_unset=True
    )
    def ip_lookup(
        ip_address: IPv4Address,
        source_file: str | None = Query(default=None, min_length=1, max_length=255),
        org_source_file: str | None = Query(default=None, min_length=1, max_length=255),
    ):
        # Validate before opening a database connection, including invalid paths.
        with read_connection(settings) as conn:
            return lookup(
                conn,
                str(ip_address),
                source_file,
                org_source_file,
                extended_enabled=settings.extended_evidence,
            )

    # Serve only the explicit frontend entry/assets. API paths keep their own 404s.
    built = Path(frontend_dir) if frontend_dir is not None else ROOT / "frontend" / "dist"
    if (built / "index.html").is_file():
        if (built / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=built / "assets"), name="frontend-assets")

        @app.get("/", include_in_schema=False)
        def frontend_index():
            return FileResponse(built / "index.html", media_type="text/html")

    return app


app = create_app()
