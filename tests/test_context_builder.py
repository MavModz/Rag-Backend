from app.modules.conversation import intent as chat_intent
from app.modules.conversation import prompts
from app.modules.knowledge.rag import context_builder
from app.modules.knowledge.rag.vector_store import RetrievedChunk
from app.platform.connectors.base import ChatTurn


def _chunk(text, source, score=0.9, idx=0):
    return RetrievedChunk(text=text, source=source, score=score, chunk_index=idx)


def test_build_kb_context_empty():
    assert "No relevant" in context_builder.build_kb_context([])


def test_build_kb_context_numbers_and_attributes_sources():
    chunks = [_chunk("Refund policy is 30 days.", "policy.pdf")]
    out = context_builder.build_kb_context(chunks)
    assert "[1]" in out
    assert "policy.pdf" in out
    assert "Refund policy" in out


def test_build_procedural_context_extracts_steps():
    text = (
        "Step 1: Complete Your Profile\n"
        "[Image (PNG): https://cdn.example.com/profile.png]\n"
        "Click Complete Institute Profile on the Assist page.\n\n"
        "Step 2: Create Your First Course\n"
        "Click Create Your First Course, then Start Now."
    )
    chunks = [_chunk(text, "onboarding-guide")]
    out = context_builder.build_kb_context(chunks, procedural=True)
    assert "Procedure extracted from" in out
    assert "1. Complete Your Profile" in out
    assert "2. Create Your First Course" in out
    assert "Complete Institute Profile" in out
    assert "profile.png" in out


def test_is_procedural_query():
    assert chat_intent.is_procedural_query("How do I create a course?")
    assert chat_intent.is_procedural_query("Steps to reset password")
    assert not chat_intent.is_procedural_query("What is your refund policy?")


def test_build_system_prompt_procedural():
    proc = prompts.build_system_prompt(procedural=True)
    general = prompts.build_system_prompt(procedural=False)
    assert "numbered steps" in proc
    assert "2–5 sentences" in general


def test_build_user_prompt_includes_memory():
    out = prompts.build_user_prompt("kb", "hist", "q?", memory_context="past insight")
    assert "past insight" in out
    assert "Learnings from past conversations" in out


def test_build_history_roles():
    turns = [
        ChatTurn(role="user", content="Need a demo"),
        ChatTurn(role="assistant", content="Sure, when works?"),
    ]
    out = context_builder.build_history(turns)
    assert "User: Need a demo" in out
    assert "Agent: Sure, when works?" in out


def test_build_history_empty():
    assert "No previous conversation" in context_builder.build_history([])


def test_unique_sources_dedupes_preserving_order():
    chunks = [_chunk("a", "a.pdf"), _chunk("b", "b.pdf"), _chunk("c", "a.pdf")]
    assert context_builder.unique_sources(chunks) == ["a.pdf", "b.pdf"]
