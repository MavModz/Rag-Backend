# Memory Service

**Status:** implemented — tenant-scoped chat learnings via Qdrant + Postgres.

**Responsibilities:** User preferences, customer history, long-term memory, AI
reflections.

**Principle:** Never store every chat — only important summaries.

**How it works:**
- After substantive `/chat` turns, `memory.summarize` extracts one insight → Qdrant `memory` collection + `memories` table.
- On future `/chat`, memory hits are retrieved in parallel with KB chunks and injected into the prompt.
- `POST /memory/feedback` promotes a verified Q+A without LLM summarization.

**Boundary rules:**
- Summaries embedded into the Qdrant `memory` collection (tenant-scoped).
- Reflection/summarization via the Model Gateway (`memory.summarize` profile).
- Multi-tenant: every memory row/vector carries `tenant_id`.
