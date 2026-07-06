"""ObjectStore interface — the contract every storage backend implements."""
from __future__ import annotations

from abc import ABC, abstractmethod


class ObjectStore(ABC):
    """Backend-agnostic binary object storage.

    Keys are forward-slash separated paths, conventionally ``<tenant_id>/<...>``
    so artifacts are namespaced per tenant. ``put`` returns a storage URI that is
    persisted in Postgres and later resolved by ``get``/``presigned_url``.
    """

    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        """Store bytes at ``key``. Returns the storage URI."""

    @abstractmethod
    def get(self, key: str) -> bytes:
        """Fetch the bytes stored at ``key``."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        ...

    @abstractmethod
    def presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """A URL the caller can use to fetch the object directly."""
