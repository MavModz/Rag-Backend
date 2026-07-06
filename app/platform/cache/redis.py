"""Redis async client (lazy, fault-tolerant).

Backs tenant-context caching, the embedding cache, conversation cache, rate-limit
counters and the JWT blocklist. Created lazily; a connection failure degrades
gracefully (callers treat a cache miss / unavailable as non-fatal).
"""
from __future__ import annotations

import redis.asyncio as aioredis

from app.config import settings
from app.platform.observability.logging import get_logger

logger = get_logger(__name__)

_client: aioredis.Redis | None = None


def get_client() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=1.0,
            socket_timeout=2.0,
        )
        logger.info("Created Redis client for %s", settings.redis_url)
    return _client


async def ping() -> bool:
    """Best-effort connectivity check for readiness probes."""
    try:
        return bool(await get_client().ping())
    except Exception as exc:  # noqa: BLE001 - readiness must not raise
        logger.warning("Redis ping failed: %s", exc)
        return False


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        logger.info("Closed Redis client")
