# Document Service (reserved)

**Status:** skeleton only — activated in a post-M1 milestone.

**Responsibilities:** File upload, OCR, parsing, chunking, embeddings, metadata.

**Workflow:** Upload → OCR → Chunk → Embedding → Store.

**Boundary rules:**
- Owns document processing; hands embeddings to the Knowledge Service vector store.
- Long-running work runs on the worker seam (`app.platform.events`) as `jobs` rows.
- All file bytes go through `app.platform.storage`; only paths/URIs in Postgres.
- Multi-tenant: every document/chunk carries `tenant_id`.

Do not add cross-module imports that reach into other modules' internals; depend
on their service interfaces only.
