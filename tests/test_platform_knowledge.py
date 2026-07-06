"""Platform-shared parent docs: ingest + tenant retrieval."""
from app.modules.knowledge.constants import DOC_SCOPE_PLATFORM, DOC_SCOPE_TENANT
from app.modules.knowledge.rag import vector_store
from app.modules.knowledge import service as ingestion_service


def test_upsert_platform_payload(monkeypatch):
    captured: dict = {}

    class _FakeClient:
        def collection_exists(self, _name):
            return True

        def delete(self, **kwargs):
            pass

        def upsert(self, *, collection_name, points):
            captured["points"] = points

    monkeypatch.setattr(vector_store, "ensure_collection", lambda: None)
    monkeypatch.setattr(vector_store, "_get_client", lambda: _FakeClient())
    monkeypatch.setattr(vector_store.settings, "retrieval_hybrid", False)

    vector_store.upsert_platform_chunks(
        product="lms",
        external_id="course-guide",
        source="course-guide.pdf",
        source_type="file",
        chunks=["Step 1"],
        vectors=[[0.1, 0.2]],
        kb_scope="support",
    )
    payload = captured["points"][0].payload
    assert payload["doc_scope"] == DOC_SCOPE_PLATFORM
    assert payload["product"] == "lms"
    assert payload["external_id"] == "course-guide"
    assert "tenant_id" not in payload


def test_tenant_upsert_sets_doc_scope(monkeypatch):
    captured: dict = {}

    class _FakeClient:
        def collection_exists(self, _name):
            return True

        def delete(self, **kwargs):
            pass

        def upsert(self, *, collection_name, points):
            captured["points"] = points

    monkeypatch.setattr(vector_store, "ensure_collection", lambda: None)
    monkeypatch.setattr(vector_store, "_get_client", lambda: _FakeClient())
    monkeypatch.setattr(vector_store.settings, "retrieval_hybrid", False)

    vector_store.upsert_chunks(
        tenant_id="tenant-1",
        source="quiz.pdf",
        chunks=["Q1"],
        vectors=[[0.1]],
        kb_scope="quiz",
    )
    assert captured["points"][0].payload["doc_scope"] == DOC_SCOPE_TENANT


def test_retrieval_filter_platform_only(monkeypatch):
    fake = type("_Hits", (), {"points": []})()

    class _FakeClient:
        def query_points(self, *, collection_name, query, query_filter, limit, with_payload, using=None):
            self.last_filter = query_filter
            return fake

    client = _FakeClient()
    monkeypatch.setattr(vector_store, "ensure_collection", lambda: None)
    monkeypatch.setattr(vector_store, "_get_client", lambda: client)

    vector_store.search(
        tenant_id="tenant-abc",
        query_vector=[0.1],
        top_k=3,
        kb_scope="support",
        product="lms",
        retrieval_profile="platform_only",
    )
    assert client.last_filter is not None
    assert client.last_filter.must is not None
    assert client.last_filter.should is None


def test_retrieval_filter_tenant_only(monkeypatch):
    fake = type("_Hits", (), {"points": []})()

    class _FakeClient:
        def query_points(self, *, collection_name, query, query_filter, limit, with_payload, using=None):
            self.last_filter = query_filter
            return fake

    client = _FakeClient()
    monkeypatch.setattr(vector_store, "ensure_collection", lambda: None)
    monkeypatch.setattr(vector_store, "_get_client", lambda: client)

    vector_store.search(
        tenant_id="tenant-abc",
        query_vector=[0.1],
        top_k=3,
        kb_scope="support",
        product="lms",
        retrieval_profile="tenant_only",
    )
    assert client.last_filter is not None
    assert client.last_filter.must is not None
    assert client.last_filter.should is None


def test_retrieval_filter_includes_platform_and_tenant(monkeypatch):
    fake = type("_Hits", (), {"points": []})()

    class _FakeClient:
        def query_points(self, *, collection_name, query, query_filter, limit, with_payload, using=None):
            self.last_filter = query_filter
            return fake

    monkeypatch.setattr(vector_store, "ensure_collection", lambda: None)
    monkeypatch.setattr(vector_store, "_get_client", lambda: _FakeClient())
    client = _FakeClient()
    monkeypatch.setattr(vector_store, "_get_client", lambda: client)

    vector_store.search(
        tenant_id="tenant-abc", query_vector=[0.1], top_k=3, kb_scope="support", product="lms"
    )
    assert client.last_filter is not None
    assert len(client.last_filter.should) == 2


def test_content_hash_helper():
    assert ingestion_service.content_hash("hello") == ingestion_service.content_hash("hello")
    assert ingestion_service.content_hash("a") != ingestion_service.content_hash("b")
