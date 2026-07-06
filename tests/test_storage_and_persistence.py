"""Object-store round-trip + the tenant persistence guard (no DB needed)."""
import uuid

import pytest

from app.platform.storage.local import LocalObjectStore
from app.platform.tenancy.context import TenantContext


def test_local_object_store_roundtrip(tmp_path):
    store = LocalObjectStore(root=str(tmp_path))
    uri = store.put("tenantA/doc.pdf", b"hello bytes", "application/pdf")
    assert uri.startswith("file://")
    assert store.exists("tenantA/doc.pdf")
    assert store.get("tenantA/doc.pdf") == b"hello bytes"
    store.delete("tenantA/doc.pdf")
    assert not store.exists("tenantA/doc.pdf")


def test_local_object_store_rejects_traversal(tmp_path):
    store = LocalObjectStore(root=str(tmp_path))
    with pytest.raises(ValueError):
        store.put("../escape.txt", b"x")


def test_tenant_uuid_guard():
    # Anonymous/dev context -> not persistable.
    assert TenantContext("anonymous", scopes=["*"]).tenant_uuid() is None
    # Real UUID tenant -> persistable.
    tid = uuid.uuid4()
    assert TenantContext(str(tid)).tenant_uuid() == tid
