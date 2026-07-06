"""Local-disk object store (dev/default backend).

Writes under ``settings.storage_root``; the storage URI is a ``file://`` path.
``presigned_url`` returns a ``file://`` URI (no signing) — adequate for local dev.
"""
from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.platform.observability.logging import get_logger
from app.platform.storage.base import ObjectStore

logger = get_logger(__name__)


class LocalObjectStore(ObjectStore):
    def __init__(self, root: str | None = None) -> None:
        self._root = Path(root or settings.storage_root)

    def _path(self, key: str) -> Path:
        # Prevent escaping the root via "../" segments.
        safe = Path(key.replace("\\", "/"))
        if safe.is_absolute() or ".." in safe.parts:
            raise ValueError(f"Invalid storage key: {key!r}")
        return self._root / safe

    def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        logger.info("Stored %d bytes at %s", len(data), path)
        return path.resolve().as_uri()

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def presigned_url(self, key: str, expires_in: int = 3600) -> str:
        return self._path(key).resolve().as_uri()
