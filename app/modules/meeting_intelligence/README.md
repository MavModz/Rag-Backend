# Meeting Intelligence Service (reserved)

**Status:** skeleton only — activated in a post-M1 milestone.

**Responsibilities:** Audio upload, transcription, speaker detection, meeting
summary, action items, requirement extraction.

**Outputs:** Summary, Tasks, Requirements, Decisions.

**Boundary rules:**
- Transcription/summarization run on the worker seam as `jobs`.
- LLM calls go through the Model Gateway (`gateway.generate(profile=...)`), never a provider.
- Audio bytes through `app.platform.storage`; structured outputs to Postgres + Qdrant.
- Multi-tenant: every artifact carries `tenant_id`.
