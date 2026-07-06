# Enterprise AI Platform

A centralized AI platform that serves AI capabilities (conversation, knowledge/
RAG, model routing, orchestration) to multiple business systems (LMS, CRM, HRMS,
ERP) through APIs. Business systems own their data; the platform owns AI
workflows, vector search, memory, the model gateway, and agent execution.

This is **Milestone 1 (Foundation)** — a hardened, multi-tenant, authenticated
evolution of the original RAG chatbot. It is a **modular monolith**: one FastAPI
app whose internal modules are bounded so any one can later be extracted into its
own service without a rewrite.

**This repo is API-only.** LMS/CRM frontends call the platform via **tenant API
keys** (`X-API-Key`). Interactive API docs: `http://localhost:8000/docs` when the
server is running.

### Integration guides

| Guide | Audience |
|-------|----------|
| [docs/INTEGRATION_WHATSAPP.md](docs/INTEGRATION_WHATSAPP.md) | WhatsApp platform team — provision, KB, chat, data sources, identity |
| [docs/WHATSAPP_BACKEND_AI_CLIENT.md](docs/WHATSAPP_BACKEND_AI_CLIENT.md) | WhatsApp backend — API list, headers, responses for AI client |

---

## Quick start (LMS / CRM help chat)

```
1. alembic upgrade head && python -m scripts.seed
2. Ingest parent-company content (once):
     python -m scripts.sync_open_blogs          # NRICH Knowledge Base articles (API)
     python -m scripts.ingest_platform_cli --product lms --file guides/course.pdf
     python -m scripts.ingest_platform_cli --product crm --file guides/meta-leads.pdf
3. Provision a customer tenant → save API key (sk_…)
4. LMS/CRM backend calls:
     POST /chat
     X-API-Key: sk_…
     { "message": "How do I create a course?", "product": "lms" }
```

---

## Architecture

```
app/
  platform/              # shared kernel
    auth/      JWT, API keys, RBAC, RequestContext
    tenancy/   TenantContext + RequestContext (product, agent, session)
    gateway/   Model Gateway (Ollama / OpenAI-compatible)
    connectors/ tenant data sources (Mongo, SQL stub)
    storage/   local | S3/MinIO
    cache/     Redis
    observability/ logging, metrics, tracing
  modules/
    conversation/  /chat, /chat/stream
    knowledge/     tenant /ingest, /knowledge/bases/*, platform /platform/*
    memory/        /memory/feedback
    identity/      /auth/*
    admin/         /admin/*
    provisioning/  /provisioning/*
    datasources/   /data-sources/*
```

**Stack:** FastAPI · PostgreSQL · Qdrant · Redis · Ollama · Alembic · Celery (optional).

---

## Knowledge model (two layers)

| Layer | Who owns content | How it is ingested | Used by |
|-------|------------------|--------------------|---------|
| **Platform** | Parent company (you) | `POST /platform/ingest` or CLI | All tenants — LMS/CRM **help chat** |
| **Tenant** | Customer org | `POST /ingest` with tenant API key | Quiz, course, WhatsApp (future) |

Qdrant payload fields: `doc_scope` (`platform` \| `tenant`), `product` (`lms` \| `crm`),
`kb_scope` (`support` \| `quiz` \| `meeting`).

**`/chat` retrieval** depends on `X-Agent`:

| `X-Agent` | KB used | Prompt |
|-----------|---------|--------|
| `platform_help` | **Platform docs only** (`doc_scope=platform`) | Platform product assistant (no chatbot tone) |
| `whatsapp` | **Tenant docs only** (`doc_scope=tenant`) | Chatbot config (tone, goals, instructions) |
| `support` (default LMS/CRM) | Platform **+** tenant | Default support prompt |
| `quiz` / `meeting` | Tenant only | Default |

---

## Identity model (LMS / CRM embedded)

| Actor | Signs up on AI? | Auth |
|-------|-----------------|------|
| Parent company (you) | Superadmin / provisioning | JWT or `X-Provisioning-Key` |
| Customer org | Provisioned once | **API key** (`sk_…`) in LMS/CRM server config |
| LMS/CRM end-user | **No** | LMS/CRM backend calls AI; optional `user_number` / `session_id` in body |

**Typical LMS/CRM integration:** browser → your backend → AI with `X-API-Key` only.

---

## Authentication

| Method | Header | Used for |
|--------|--------|----------|
| Tenant API key | `X-API-Key: sk_…` | LMS/CRM backends (`/chat`, `/ingest`, …) |
| Platform JWT | `Authorization: Bearer <token>` | Superadmin UI (`/auth/login`) |
| Provisioning secret | `X-Provisioning-Key: <secret>` | `/provisioning/*`, `/platform/*` |
| Anonymous | (none) | Dev only when `AUTH_ALLOW_ANONYMOUS=true` |

### Optional routing headers (all routes)

| Header | Values | Purpose |
|--------|--------|---------|
| `X-Product` | `lms`, `crm` | Which parent help docs to retrieve |
| `X-Agent` | `platform_help`, `support`, `quiz`, `whatsapp`, `meeting` | Retrieval layer + prompt profile |
| `X-Session-Id` | string | Conversation thread (CRM WhatsApp, etc.) |
| `X-Acting-User-Id` | string | CRM admin acting on behalf of a lead |
| `X-Request-ID` | string | Correlation id (echoed in response) |

`product` can also be sent in the `/chat` JSON body.

Default scopes on API keys: `chat:write`, `kb:read`, `kb:write`.

---

## API reference

Base URL: `http://localhost:8000` (dev). All JSON bodies use `Content-Type: application/json`
unless noted as multipart.

### Health & ops

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | none | Liveness |
| GET | `/health/ready` | none | Postgres, Redis, Qdrant, Ollama |
| GET | `/metrics` | none | Prometheus metrics |

### Identity (`/auth`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/register` | public* | Self-serve signup → tenant + user + API key + JWT |
| POST | `/auth/login` | public | Email/password → access + refresh JWT |
| POST | `/auth/refresh` | public | Rotate JWT |
| GET | `/auth/whoami` | any | Current `RequestContext` |
| POST | `/auth/tenants` | `admin:tenants` | Create tenant |
| POST | `/auth/users` | `admin:users` | Create user |
| POST | `/auth/api-keys` | `admin:keys` | Mint API key (shown once) |

\* Requires `ALLOW_PUBLIC_REGISTRATION=true`.

### Admin (`/admin`) — superadmin

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/admin/provision` | `admin:tenants` | Bulk onboard tenants (JSON) |
| POST | `/admin/provision/csv` | `admin:tenants` | Bulk onboard (CSV upload) |
| GET | `/admin/tenants` | `admin:tenants` | List tenants |
| POST | `/admin/tenants` | `admin:tenants` | Create tenant |
| GET | `/admin/tenants/{id}` | `admin:tenants` | Get tenant |
| PATCH | `/admin/tenants/{id}` | `admin:tenants` | Update tenant |
| GET | `/admin/tenants/{id}/users` | `admin:users` | List users |
| POST | `/admin/tenants/{id}/users` | `admin:users` | Create user |
| PATCH | `/admin/users/{id}` | `admin:users` | Update user |
| GET | `/admin/tenants/{id}/api-keys` | `admin:keys` | List API keys |
| POST | `/admin/tenants/{id}/api-keys` | `admin:keys` | Create API key |
| POST | `/admin/api-keys/{id}/revoke` | `admin:keys` | Revoke API key |
| GET | `/admin/roles` | `admin:users` | List roles |

### Provisioning (`/provisioning`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/provisioning/tenants` | `X-Provisioning-Key` | Create tenant + admin + API key (billing webhook) |

Disabled when `PROVISIONING_API_KEY` is empty.

Set `PROVISIONING_API_KEY` in `.env` (generate with `openssl rand -hex 32`). The
same secret is configured on trusted product backends (e.g. WhatsApp) as
`X-Provisioning-Key` — it is **not** returned by any API. After provision, use
the returned `api_key` (`sk_…`) as `X-API-Key` for `/chat`, `/ingest`, etc.

```bash
curl -X POST http://localhost:8000/provisioning/tenants \
  -H "X-Provisioning-Key: $PROVISIONING_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Acme Corp WhatsApp",
    "plan": "standard",
    "admin_email": "admin@acme.com"
  }'
```

Response (`201`): `tenant_id`, `api_key` (shown once), `admin_email`,
`admin_password` (generated if omitted). Full WhatsApp + CRM flow:
[docs/INTEGRATION_WHATSAPP.md](docs/INTEGRATION_WHATSAPP.md).

### Data sources (`/data-sources`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/data-sources` | `datasources:manage` | List tenant data sources |
| POST | `/data-sources` | `datasources:manage` | Create data source |
| GET | `/data-sources/{id}` | `datasources:manage` | Get data source |
| PATCH | `/data-sources/{id}` | `datasources:manage` | Update data source |
| DELETE | `/data-sources/{id}` | `datasources:manage` | Delete data source |
| POST | `/data-sources/test` | `datasources:manage` | Test connection (no save) |
| POST | `/data-sources/discover` | `datasources:manage` | Discover DBs/tables/collections |

Tenant self-service `/data-sources` remains for **LMS/CRM** embedded products.
**WhatsApp** does not use AI-side Mongo registration; history is pushed on `/chat` (planned).

### Platform knowledge (`/platform`) — parent company docs

Shared across **all** tenants. Requires `X-Provisioning-Key`.

| Method | Path | Body | Description |
|--------|------|------|-------------|
| GET | `/platform/documents` | query `?product=lms` | List indexed platform docs |
| POST | `/platform/ingest` | multipart: `product`, `file`, optional `kb_scope`, `external_id`, `title` | Ingest PDF/DOCX manual |
| POST | `/platform/ingest/text` | JSON: `product`, `external_id`, `title`, `text`, optional `kb_scope`, `source_type` | Ingest article/FAQ text (API sync ready) |
| POST | `/platform/sync/open-blogs` | form: `product` (default `lms`), `kb_scope`, `force` | Pull [NRICH open-blogs API](https://knowledgebasebackend.nrichlearning.com/api/open-blogs/) into platform KB |

```bash
curl -X POST http://localhost:8000/platform/ingest \
  -H "X-Provisioning-Key: $PROVISIONING_API_KEY" \
  -F product=lms \
  -F kb_scope=support \
  -F file=@guides/course-guide.pdf

curl -X POST http://localhost:8000/platform/ingest/text \
  -H "X-Provisioning-Key: $PROVISIONING_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"product":"crm","external_id":"meta-leads","title":"Import Meta leads","text":"..."}'

curl -X POST http://localhost:8000/platform/sync/open-blogs \
  -H "X-Provisioning-Key: $PROVISIONING_API_KEY" \
  -F product=lms \
  -F kb_scope=support
```

Articles from the [NRICH open-blogs API](https://knowledgebasebackend.nrichlearning.com/api/open-blogs/) are synced as platform docs (`source_type=api`). Tenants retrieve them on `POST /chat` with `product=lms`. Unchanged articles are skipped unless `force=true`.

### Tenant knowledge (`/ingest`, `/knowledge`)

Per-tenant uploads (quiz papers, custom docs). Requires tenant `X-API-Key`.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/ingest` | `kb:write` | Upload PDF/DOCX (`kb_scope` form field, default `support`) |
| GET | `/knowledge/bases` | `kb:read` | List KB scopes for tenant |
| GET | `/knowledge/bases/{scope}/documents` | `kb:read` | List docs in scope (`support`, `quiz`, `meeting`) |
| DELETE | `/knowledge/bases/{scope}/documents/{id}` | `kb:write` | Delete doc + Qdrant vectors |

```bash
curl -X POST http://localhost:8000/ingest \
  -H "X-API-Key: sk_..." \
  -F file=@quiz-bank.docx \
  -F kb_scope=quiz
```

### Chat (`/chat`)

| Method | Path | Auth | Body | Description |
|--------|------|------|------|-------------|
| POST | `/chat` | `chat:write` | See below | Grounded answer + `sources` |
| POST | `/chat/stream` | `chat:write` | Same | SSE stream: `token` events then `done` |

**Request body:**

```json
{
  "message": "How do I create a course?",
  "product": "lms",
  "user_number": "optional-external-user-id",
  "session_id": "optional-thread-id",
  "company_id": "optional-legacy-override"
}
```

**Response:**

```json
{
  "answer": "...",
  "sources": ["course-guide.pdf"]
}
```

```bash
curl -X POST http://localhost:8000/chat \
  -H "X-API-Key: sk_..." \
  -H "Content-Type: application/json" \
  -d '{"message":"How do I fetch leads from Meta?","product":"crm"}'
```

Retrieves per `X-Agent` (see table above). With no agent, behavior matches `support`
(platform + tenant). Includes **memory** context when `MEMORY_ENABLED=true`.

**Platform admin UI** (tenant logged into AI platform):

```bash
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer <platform_jwt>" \
  -H "X-Agent: platform_help" \
  -H "X-Product: lms" \
  -H "Content-Type: application/json" \
  -d '{"message":"How do I upload documents to the knowledge base?"}'
```

### Memory (`/memory`)

| Method | Path | Auth | Body | Description |
|--------|------|------|------|-------------|
| POST | `/memory/feedback` | `chat:write` | `{ question, answer, user_number? }` | Store verified Q+A |

---

## Agent-scoped knowledge (`kb_scope`)

| `kb_scope` | Use case | Default retrieval |
|------------|----------|-------------------|
| `support` | Help chat, WhatsApp | `/chat` |
| `quiz` | Quiz generation (future) | Tenant `/ingest` only today |
| `meeting` | Meeting intel (future) | — |

Set on ingest via form field `kb_scope` or header `X-Agent` on chat.

---

## Run locally

```bash
cp .env.example .env
# Set POSTGRES_URL, REDIS_URL, PROVISIONING_API_KEY, OLLAMA_CHAT_MODEL

ollama pull qwen2.5:7b-instruct
ollama pull mxbai-embed-large

venv/Scripts/python -m alembic upgrade head
venv/Scripts/python -m scripts.seed

venv/Scripts/python -m uvicorn app.main:app --reload
```

### Docker (app only)

```bash
docker compose -f docker/compose.yaml up --build
```

Provide external Postgres + Redis in `.env`. Qdrant is embedded on disk.

---

## CLI & maintenance scripts

Stop the API server before Qdrant maintenance on **local on-disk** Qdrant.

### Database

```bash
python -m alembic upgrade head          # apply migrations
python -m scripts.seed                # bootstrap admin + default tenant + API key
```

### Ingest — platform (parent company, shared)

```bash
python -m scripts.ingest_platform_cli --product lms --file guides/course.pdf
python -m scripts.ingest_platform_cli --product crm --file guides/meta-leads.pdf
python -m scripts.ingest_platform_cli --product lms --file x.pdf --kb-scope support \
  --external-id course-guide --title "Course guide"
```

### Sync — NRICH Knowledge Base (open-blogs API)

```bash
python -m scripts.sync_open_blogs
python -m scripts.sync_open_blogs --product lms --force   # re-embed all articles
```

Optional env: `NRICH_KB_API_BASE_URL` (default `https://knowledgebasebackend.nrichlearning.com`).

### Ingest — tenant (customer uploads)

```bash
python -m scripts.ingest_cli --file quiz.docx --company <tenant_uuid_or_id> --kb-scope quiz
python -m scripts.ingest_cli --file policy.pdf --company <tenant_id>   # default support
```

### Qdrant migrations (one-time, legacy data)

```bash
python -m scripts.reset_vectors --yes              # rebuild collection (wipes all chunks)
python -m scripts.migrate_qdrant_payload --yes     # backfill tenant_id from company_id
python -m scripts.migrate_kb_scope --yes         # backfill kb_scope=support on old points
```

---

## Key environment variables

| Variable | Purpose |
|----------|---------|
| `POSTGRES_URL` | Primary DB |
| `REDIS_URL` | Cache / rate limits |
| `JWT_SECRET` | Platform admin JWT |
| `PROVISIONING_API_KEY` | `/provisioning/*` and `/platform/*` |
| `LMS_JWT_SECRET` / `CRM_JWT_SECRET` | Optional product-user JWT validation |
| `AUTH_ALLOW_ANONYMOUS` | Dev: allow unauthenticated access (`false` in prod) |
| `DEFAULT_CHAT_PRODUCT` | Default `product` when omitted on `/chat` (`lms`) |
| `MEMORY_ENABLED` | Learn from past chats |
| `OLLAMA_CHAT_MODEL` / `OLLAMA_EMBED_MODEL` | Generation + embeddings |
| `QDRANT_PATH` | On-disk Qdrant path |
| `RATE_LIMIT_CHAT` / `RATE_LIMIT_INGEST` | Per-tenant limits |

See `.env.example` for the full list.

---

## RAG pipeline

- **Platform + tenant retrieval** — `/chat` searches shared parent docs and tenant docs.
- **Agent-scoped** — `kb_scope` filter on every search.
- **Reranking** — `RETRIEVAL_RERANK=true` (default).
- **Hybrid** — `RETRIEVAL_HYBRID=true` (changes Qdrant schema → `reset_vectors` + re-ingest).
- **Small-talk bypass** — greetings skip retrieval.
- **Memory** — parallel retrieval of past chat summaries.

---

## Tests

```bash
venv/Scripts/python -m pip install -r requirements-dev.txt
venv/Scripts/python -m pytest tests/ -q

# Integration (needs Postgres):
RUN_INTEGRATION=1 venv/Scripts/python -m pytest tests/integration -q
```

---

## Roadmap

| Item | Status |
|------|--------|
| Platform-shared docs (files + text ingest) | **Done** |
| Tenant help chat via API key + `product` | **Done** |
| KB REST API sync (blogs, FAQs) | Next phase |
| WhatsApp integration guide | **Done** — [docs/INTEGRATION_WHATSAPP.md](docs/INTEGRATION_WHATSAPP.md) |
| `chatbot/` config module (`/chatbot/whatsapp/config`) | Planned |
| Quiz / course agents | Planned |
| `tenant_external_ids` (LMS institute / CRM org mapping) | Planned |

---

## Notes

- **Parent docs** are ingested once under `doc_scope=platform`; every tenant API key sees them on `/chat`.
- **Tenant docs** are for future creation agents (quiz, course, bots) via `POST /ingest`.
- **Models do not learn** — memory + RAG improve answers without fine-tuning.
- **OpenAPI:** `GET /docs` and `GET /redoc` when the server is running.
