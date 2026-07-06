# Workflow Engine (reserved)

**Status:** skeleton only — activated in a post-M1 milestone.

**Responsibilities:** Execute AI pipelines as reusable, declarative workflows.

**Examples:**
- Upload PDF → OCR → Question Extraction → Validation → Quiz Creation → LMS API.
- Meeting Recording → Transcription → Summary → Action Items → CRM Task Creation.

**Boundary rules:**
- Steps run on the worker seam (`app.platform.events`); state tracked in `workflow_runs`.
- Steps invoke other modules' service interfaces and the Model Gateway only.
- Multi-tenant: every run carries `tenant_id`.
