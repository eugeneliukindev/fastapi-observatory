from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Final

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor

from cache import MemoryCache
from config import Settings
from middleware import REQUEST_ID_HEADER, AccessMiddleware
from observability import (
    ServiceIdentity,
    configure_logging,
    configure_metrics,
    configure_profiling,
    configure_tracing,
    contextualize_logging,
    logger,
)
from router import router

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

_STATIC: Final = Path(__file__).parent / "static"
_PLACEHOLDER_URL: Final = "https://jsonplaceholder.typicode.com"
_PLACEHOLDER_TIMEOUT_SECONDS: Final = 5.0
_BUSY_TIMEOUT_SECONDS: Final = 5.0


def create_app() -> FastAPI:
    """Set this process up — logging, telemetry, clients — and return the application.

    Nothing is assumed set up already, so the process may be forked, spawned or the only one.
    """
    settings = Settings()
    configure_logging(settings.log_level)
    contextualize_logging()
    service = ServiceIdentity(name=settings.obs.service_name, environment=settings.obs.environment)
    tracer_provider = configure_tracing(service, otlp_endpoint=settings.obs.otlp.endpoint)
    configure_metrics(service, otlp_endpoint=settings.obs.otlp.endpoint)
    configure_profiling(service, tracer_provider, pyroscope_url=settings.obs.pyroscope.url)

    http = httpx.AsyncClient(base_url=_PLACEHOLDER_URL, timeout=_PLACEHOLDER_TIMEOUT_SECONDS)
    HTTPXClientInstrumentor.instrument_client(http)

    # Other processes share the file: the timeout waits out their writes.
    connection = sqlite3.connect(settings.db.path, autocommit=True, timeout=_BUSY_TIMEOUT_SECONDS)
    connection.row_factory = sqlite3.Row
    database = SQLite3Instrumentor.instrument_connection(connection)
    logger.info("SQLite database opened", extra={"database_path": str(settings.db.path)})

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await http.aclose()
        connection.close()
        logger.info("SQLite database closed")

    app = FastAPI(title="observatory", lifespan=lifespan)
    app.state.http = http
    app.state.cache = MemoryCache[dict[str, object]]()
    app.state.database = database
    app.state.settings = settings
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=_STATIC), name="static")

    app.add_middleware(AccessMiddleware, excluded_paths=["/health"])
    # The probe says nothing, and the ASGI send and receive spans only repeat the request span.
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="/health",
        exclude_spans=["receive", "send"],
        # The request's key on its span, so a trace is found by the key a log line or a caller has.
        http_capture_headers_server_response=[REQUEST_ID_HEADER],
    )
    return app
