"""Agent-scoped knowledge base helpers and vector-store scoping."""
import pytest

from app.modules.knowledge import repository as kb_repo
from app.modules.knowledge.constants import DEFAULT_KB_SCOPE, KNOWN_KB_SCOPES
from app.modules.knowledge.rag import vector_store


def test_normalize_kb_scope_defaults_to_support():
    assert kb_repo.normalize_kb_scope(None) == DEFAULT_KB_SCOPE
    assert kb_repo.normalize_kb_scope("  Support ") == "support"


def test_normalize_kb_scope_rejects_unknown():
    with pytest.raises(ValueError, match="kb_scope must be one of"):
        kb_repo.normalize_kb_scope("billing")


def test_known_kb_scopes_match_plan():
    assert KNOWN_KB_SCOPES == frozenset({"support", "quiz", "meeting"})


def test_delete_by_source_passes_kb_scope(monkeypatch):
    captured: dict = {}

    class _FakeClient:
        def collection_exists(self, _name):
            return True

        def delete(self, *, collection_name, points_selector):
            captured["selector"] = points_selector

    monkeypatch.setattr(vector_store, "_get_client", lambda: _FakeClient())
    vector_store.delete_by_source("tenant-a", "policy.pdf", kb_scope="quiz")

    must = captured["selector"].must
    source_cond = next(c for c in must if getattr(c, "key", None) == "source")
    assert source_cond.match.value == "policy.pdf"
    scope_filter = next(
        c
        for c in must
        if hasattr(c, "should")
        and any(getattr(s, "key", None) == "kb_scope" for s in c.should)
    )
    scope_values = [c.match.value for c in scope_filter.should if c.key == "kb_scope"]
    assert scope_values == ["quiz"]


def test_upsert_payload_includes_kb_scope(monkeypatch):
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
        tenant_id="t1",
        source="quiz.docx",
        chunks=["Q1"],
        vectors=[[0.1, 0.2]],
        kb_scope="quiz",
    )
    assert captured["points"][0].payload["kb_scope"] == "quiz"
    assert captured["points"][0].payload["tenant_id"] == "t1"
