"""Object storage abstraction.

Business systems own their data; the platform stores binary artifacts (uploaded
documents, audio, exports) behind a backend-agnostic ``ObjectStore`` interface.
Only the resulting storage URI is recorded in Postgres — never the bytes.
``get_object_store()`` selects the backend from config (local disk for dev,
MinIO/S3 for production).
"""
from __future__ import annotations

from functools import lru_cache

from app.config import settings
from app.platform.storage.base import ObjectStore


@lru_cache
def get_object_store() -> ObjectStore:
    backend = settings.object_store_backend.lower()
    if backend == "s3":
        from app.platform.storage.s3 import S3ObjectStore

        return S3ObjectStore()
    from app.platform.storage.local import LocalObjectStore

    return LocalObjectStore()
