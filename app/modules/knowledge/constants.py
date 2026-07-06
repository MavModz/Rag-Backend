"""Knowledge base scope slugs and defaults (one bucket per agent use-case)."""
from __future__ import annotations

DEFAULT_KB_SCOPE = "support"

KNOWN_KB_SCOPES = frozenset({"support", "quiz", "meeting"})

# Document ownership in Qdrant + Postgres.
DOC_SCOPE_PLATFORM = "platform"
DOC_SCOPE_TENANT = "tenant"

SOURCE_TYPE_FILE = "file"
SOURCE_TYPE_API = "api"

DEFAULT_CHAT_PRODUCT = "lms"

# (scope, display name, description) — seeded per tenant on provision.
DEFAULT_KNOWLEDGE_BASES: tuple[tuple[str, str, str], ...] = (
    ("support", "Support", "Customer support and WhatsApp RAG documents"),
    ("quiz", "Quiz", "Quiz banks and assessment content"),
    ("meeting", "Meeting", "Meeting transcripts and summaries"),
)
