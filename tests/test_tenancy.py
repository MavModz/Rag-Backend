"""Tenancy guardrail: vector search is always scoped to the tenant.

Verifies that ``vector_store.search`` never issues an unfiltered query and that
the filter dual-reads the new ``tenant_id`` and legacy ``company_id`` payloads.
"""
from app.modules.knowledge.rag import vector_store


class _Hits:
    points: list = []


class _FakeClient:
    def __init__(self):
        self.last_filter = None

    def query_points(self, *, collection_name, query, query_filter, limit, with_payload, using=None):
        self.last_filter = query_filter
        return _Hits()


def test_search_without_product_uses_legacy_tenant_filter(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(vector_store, "ensure_collection", lambda: None)
    monkeypatch.setattr(vector_store, "_get_client", lambda: fake)

    vector_store.search(
        tenant_id="tenant-123", query_vector=[0.1, 0.2], top_k=3, kb_scope="quiz"
    )

    assert fake.last_filter is not None
    assert fake.last_filter.must is not None
    tenant_filter = fake.last_filter.must[0]
    keys = {c.key for c in tenant_filter.should}
    assert keys == {"tenant_id", "company_id"}


def test_search_with_product_includes_platform_and_tenant(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(vector_store, "ensure_collection", lambda: None)
    monkeypatch.setattr(vector_store, "_get_client", lambda: fake)

    vector_store.search(
        tenant_id="tenant-123",
        query_vector=[0.1, 0.2],
        top_k=3,
        kb_scope="support",
        product="lms",
    )

    assert fake.last_filter is not None
    assert len(fake.last_filter.should) == 2


def test_kb_scope_match_includes_legacy_empty_for_support():
    conds = vector_store._kb_scope_match("support")
    assert len(conds) == 2
    assert any(getattr(c, "key", None) == "kb_scope" for c in conds)
    quiz_conds = vector_store._kb_scope_match("quiz")
    assert len(quiz_conds) == 1


def test_tenant_match_builds_both_conditions():
    conds = vector_store._tenant_match("abc")
    assert [c.key for c in conds] == ["tenant_id", "company_id"]
    assert all(c.match.value == "abc" for c in conds)
