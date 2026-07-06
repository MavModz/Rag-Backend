"""Per-tenant rate limiting.

A single ``slowapi`` Limiter keyed by the authenticated tenant (from the tracing
contextvar set by the auth dependency), falling back to the client IP for the
anonymous/dev context. Storage is ``memory://`` by default so dev runs without
Redis; point ``rate_limit_storage_uri`` at Redis in production for shared,
multi-process counters. Per-route limits are applied via the ``limiter.limit``
decorator on the routers.
"""
from __future__ import annotations

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.config import settings
from app.platform.observability import tracing


def _tenant_key(request: Request) -> str:
    tenant_id = tracing.get_tenant_id()
    if tenant_id and tenant_id != "anonymous":
        return f"tenant:{tenant_id}"
    return get_remote_address(request)


# Per-route limits are applied with @limiter.limit(...) decorators (no global
# middleware). headers_enabled stays off so dict-returning endpoints don't need a
# Response parameter just for the rate-limit headers.
limiter = Limiter(
    key_func=_tenant_key,
    storage_uri=settings.rate_limit_storage_uri,
    enabled=settings.rate_limit_enabled,
    headers_enabled=False,
    # Fail open: if the storage backend (Redis) is unreachable, allow the request
    # rather than 500. Rate limiting should never take the whole API down.
    swallow_errors=True,
)


def install_rate_limiting(app) -> None:
    """Register the limiter and its 429 handler on the app."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
