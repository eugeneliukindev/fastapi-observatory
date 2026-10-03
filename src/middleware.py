from __future__ import annotations

import logging
import time
import uuid
from http import HTTPStatus
from typing import TYPE_CHECKING, Final, final, override

from fastapi.routing import APIRoute
from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

from observability import logger, request_id_ctx_var

if TYPE_CHECKING:
    from collections.abc import Iterable

    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.types import ASGIApp

REQUEST_ID_HEADER: Final = "X-Request-ID"
"""The header a request's key arrives in, if the caller has one, and is returned in."""
_MILLISECONDS_IN_SECOND: Final = 1000


@final
class AccessMiddleware(BaseHTTPMiddleware):
    """Give the request a key, return it in the response and write a line for every response."""

    def __init__(self, app: ASGIApp, *, excluded_paths: Iterable[str] = ()) -> None:
        """Wrap the application.

        Args:
            app: The ASGI application to wrap.
            excluded_paths: Paths that get neither a key nor a line — liveness probes.
        """
        super().__init__(app)
        self._excluded_paths = frozenset(excluded_paths)

    @override
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Pass the request through under its key and record the outcome."""
        if request.url.path in self._excluded_paths:
            return await call_next(request)

        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        started = time.perf_counter()
        token = request_id_ctx_var.set(request_id)
        try:
            response = await call_next(request)
        except Exception as error:
            # Answered here, not re-raised: the server would log the stack again, without the keys.
            trace.get_current_span().record_exception(error)
            response = PlainTextResponse("Internal Server Error", status_code=HTTPStatus.INTERNAL_SERVER_ERROR)
            _write(
                "HTTP request failed with an unhandled exception", request, response.status_code, started, exc_info=True
            )
        else:
            _write("HTTP request handled", request, response.status_code, started)
        finally:
            request_id_ctx_var.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def _write(message: str, request: Request, status: int, started: float, *, exc_info: bool = False) -> None:
    logger.log(
        _severity(status),
        message,
        exc_info=exc_info,
        extra={
            "method": request.method,
            "path": request.url.path,
            "route": _route_template(request),
            "query": request.url.query,
            "status": status,
            "duration_ms": int((time.perf_counter() - started) * _MILLISECONDS_IN_SECOND),
        },
    )


def _route_template(request: Request) -> str | None:
    # The template the metrics carry as `http_route`; none outside the API: a 404, the static files.
    route = request.scope.get("route")
    return route.path if isinstance(route, APIRoute) else None


def _severity(status: int) -> int:
    if HTTPStatus(status).is_server_error:
        return logging.ERROR
    return logging.WARNING if HTTPStatus(status).is_client_error else logging.INFO
