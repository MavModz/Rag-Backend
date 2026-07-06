"""HTTP client for the NRICH Knowledge Base open-blogs API."""
from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.platform.observability.logging import get_logger

logger = get_logger(__name__)


class NrichKbError(Exception):
    pass


def _base_url() -> str:
    return settings.nrich_kb_api_base_url.rstrip("/")


def _unwrap_article(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    raise NrichKbError("Unexpected article response shape")


async def fetch_open_blogs(*, client: httpx.AsyncClient | None = None) -> list[dict[str, Any]]:
    """List all public open-blog articles (includes body in list response)."""
    url = f"{_base_url()}/api/open-blogs/"
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=settings.nrich_kb_api_timeout)
    try:
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise NrichKbError("Unexpected list response shape")
        return [row for row in rows if isinstance(row, dict)]
    except httpx.HTTPError as exc:
        raise NrichKbError(f"Failed to fetch open blogs: {exc}") from exc
    finally:
        if own_client:
            await client.aclose()


async def fetch_open_blog_by_slug(
    slug: str, *, client: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    """Fetch a single article when the list payload has no body."""
    url = f"{_base_url()}/api/open-blogs/{slug.strip('/')}"
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=settings.nrich_kb_api_timeout)
    try:
        response = await client.get(url)
        response.raise_for_status()
        return _unwrap_article(response.json())
    except httpx.HTTPError as exc:
        raise NrichKbError(f"Failed to fetch article {slug!r}: {exc}") from exc
    finally:
        if own_client:
            await client.aclose()
