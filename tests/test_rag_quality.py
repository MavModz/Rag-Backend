"""Tests for the RAG quality upgrades: context-aware chunking + reranking.

No model downloads — the reranker is exercised via its fallback path and a
monkeypatched encoder, so these run offline.
"""
from app.config import settings
from app.modules.knowledge.rag import chunker, reranker
from app.modules.knowledge.rag.vector_store import RetrievedChunk


def _chunk(text: str) -> RetrievedChunk:
    return RetrievedChunk(text=text, source="s.pdf", score=0.0, chunk_index=0)


# --- context-aware chunking ---
def test_chunks_never_split_a_sentence(monkeypatch):
    monkeypatch.setattr(settings, "chunk_strategy", "structure")
    text = "Refunds are processed in 30 days. Shipping is free over $50. " * 20
    chunks = chunker.chunk_text(text, chunk_size=200, chunk_overlap=40)
    assert len(chunks) > 1
    # Every chunk ends on sentence punctuation (no mid-sentence cut).
    assert all(c.strip()[-1] in ".!?" for c in chunks)
    assert all(c.strip() for c in chunks)


def test_long_unbroken_block_is_hard_wrapped(monkeypatch):
    monkeypatch.setattr(settings, "chunk_strategy", "structure")
    chunks = chunker.chunk_text("word " * 1000, chunk_size=300, chunk_overlap=50)
    assert chunks and all(len(c) <= 350 for c in chunks)


def test_empty_text():
    assert chunker.chunk_text("") == []
    assert chunker.chunk_text("   \n  ") == []


# --- reranking ---
def test_rerank_disabled_keeps_order(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_rerank", False)
    chunks = [_chunk("a"), _chunk("b"), _chunk("c")]
    assert reranker.rerank("q", chunks, top_k=2) == chunks[:2]


def test_rerank_orders_by_score(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_rerank", True)

    class FakeEncoder:
        def rerank(self, query, docs):
            # higher score for the doc containing "match"
            return [10.0 if "match" in d else 1.0 for d in docs]

    monkeypatch.setattr(reranker, "_get_encoder", lambda: FakeEncoder())
    chunks = [_chunk("nope"), _chunk("the match here"), _chunk("also nope")]
    ranked = reranker.rerank("q", chunks, top_k=2)
    assert ranked[0].text == "the match here"
    assert len(ranked) == 2


def test_rerank_falls_back_on_error(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_rerank", True)

    def boom():
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(reranker, "_get_encoder", boom)
    chunks = [_chunk("a"), _chunk("b")]
    assert reranker.rerank("q", chunks, top_k=1) == chunks[:1]
