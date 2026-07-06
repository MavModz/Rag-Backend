# Agent Orchestrator (reserved)

**Status:** skeleton only — activated in a post-M1 milestone.

**Responsibilities:** Receive user intent, select the correct agent, run it.

**Agents:** Support, Quiz, Meeting, Requirement, CRM, LMS, Document (future: HR,
Finance, Legal, Sales).

**Boundary rules:**
- Agents contain business logic only; **all** LLM access via the Model Gateway.
- Orchestrator composes module service interfaces — no reaching into internals.
- Multi-tenant: intent routing carries the full `TenantContext`.
