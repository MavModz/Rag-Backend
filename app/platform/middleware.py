"""HTTP middleware: request-id correlation, timing, and metrics.

Binds a request id for the duration of each request. Tenant/product/session
fields are reset here and populated later by the auth dependency once credentials
are resolved.
"""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from app.config import settings
from app.platform.observability import metrics, tracing
from app.platform.observability.logging import get_logger

logger = get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or tracing.new_request_id()
        trace_tokens = tracing.begin_http_request(request_id)

        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration = time.perf_counter() - start
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            if settings.metrics_enabled:
                metrics.http_requests_total.labels(
                    request.method, path, str(status)
                ).inc()
                metrics.http_request_duration_seconds.labels(
                    request.method, path
                ).observe(duration)
            snap = tracing.current_context()
            logger.info(
                "%s %s -> %s (%.1f ms) tenant=%s product=%s agent=%s auth=%s",
                request.method,
                request.url.path,
                status,
                duration * 1000,
                snap.get("tenant_id") or "-",
                snap.get("product") or "-",
                snap.get("agent") or "-",
                snap.get("auth_mode") or "-",
            )
            tracing.end_http_request(trace_tokens)


def install_middleware(app) -> None:
    """Attach platform middleware to the FastAPI app."""
    app.add_middleware(RequestContextMiddleware)
