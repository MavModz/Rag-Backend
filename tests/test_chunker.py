from app.modules.knowledge.rag import chunker


def test_empty_text_returns_no_chunks():
    assert chunker.chunk_text("") == []
    assert chunker.chunk_text("   \n  ") == []


def test_chunks_have_no_blank_entries():
    text = "Sentence one. " * 300
    chunks = chunker.chunk_text(text, chunk_size=200, chunk_overlap=20)
    assert len(chunks) > 1
    assert all(c.strip() for c in chunks)


def test_overlap_keeps_chunks_within_size_bound():
    text = "word " * 1000
    chunks = chunker.chunk_text(text, chunk_size=300, chunk_overlap=50)
    # RecursiveCharacterTextSplitter may slightly exceed on hard splits; allow margin.
    assert all(len(c) <= 350 for c in chunks)
