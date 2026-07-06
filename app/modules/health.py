"""Health, readiness, and metrics routes.

- ``/health``       cheap liveness probe (process is up).
- ``/health/ready`` deep readiness: Postgres + Redis + Qdrant + Ollama.
- ``/metrics``      Prometheus exposition.
"""
from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter, Response

from app.config import settings
from app.platform.cache import redis as redis_cache
from app.platform.db import postgres
from app.platform.observability import metrics

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def _check_ollama() -> bool:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            return resp.status_code == 200
    except Exception:  # noqa: BLE001 - readiness must not raise
        return False


async def _check_qdrant() -> bool:
    # Only probe a server URL; the embedded/local store is single-process and
    # opening a second client would conflict with the app's own.
    if not settings.qdrant_path.lower().startswith(("http://", "https://")):
        return True
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{settings.qdrant_path}/readyz")
            return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


@router.get("/health/ready")
async def ready(response: Response) -> dict[str, object]:
    pg, rd, oll, qd = await asyncio.gather(
        postgres.ping(),
        redis_cache.ping(),
        _check_ollama(),
        _check_qdrant(),
    )
    checks = {"postgres": pg, "redis": rd, "ollama": oll, "qdrant": qd}
    ok = all(checks.values())
    if not ok:
        response.status_code = 503
    return {"status": "ready" if ok else "degraded", "checks": checks}


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    body, content_type = metrics.render()
    return Response(content=body, media_type=content_type)
