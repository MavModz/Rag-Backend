# WhatsApp Backend → AI Platform API Client

Reference for implementing the WhatsApp BFF HTTP client against the AI platform.
See also [INTEGRATION_WHATSAPP.md](./INTEGRATION_WHATSAPP.md).

**Base URL env:** `AI_BASE_URL` (e.g. `http://localhost:8000`)

---

## Environment variables (WhatsApp backend)

```env
AI_BASE_URL=http://localhost:8000
AI_PROVISIONING_KEY=<same as AI platform PROVISIONING_API_KEY>
```

Per workspace (encrypted in DB after connect):

- `ai_tenant_id` — UUID from provision response
- `ai_api_key` — `sk_...` from provision response (shown once)

---

## Auth headers summary

| Call type | Headers |
|-----------|---------|
| Provision (once per company) | `X-Provisioning-Key`, `Content-Type: application/json` |
| All tenant APIs | `X-API-Key: sk_...` |
| WhatsApp chat | + `X-Agent: whatsapp`, `X-Channel: whatsapp`, `X-Session-Id` — **tenant KB only**, chatbot tone applied |
| Platform admin chat (AI SPA) | `Authorization: Bearer`, `X-Agent: platform_help`, `X-Product` — **platform KB only**, no chatbot tone |
| Optional | `X-Product: crm`, `X-Request-ID: <uuid>` |

Never send provisioning key or API key to the browser.

---

## 1. Health check (no auth)

```http
GET /health
```

Response `200`: `{ "status": "ok" }`

```http
GET /health/ready
```

Response `200` when Postgres, Redis, Qdrant, Ollama reachable.

---

## 2. Provision tenant (Connect AI)

```http
POST /provisioning/tenants
X-Provisioning-Key: <AI_PROVISIONING_KEY>
Content-Type: application/json
```

**Body:**

```json
{
  "name": "Acme Corp WhatsApp",
  "plan": "standard",
  "admin_email": "whatsapp+acme@yourplatform.com",
  "admin_password": null
}
```

**Response `201`:**

```json
{
  "tenant_id": "uuid",
  "admin_email": "whatsapp+acme@yourplatform.com",
  "admin_password": "generated-if-omitted",
  "api_key": "sk_..."
}
```

**Errors:** `404` (provisioning disabled), `401` (bad key), `409` (email exists)

**Store:** `tenant_id`, `api_key` encrypted on workspace row.

---

## 3. Verify API key (after connect)

```http
GET /auth/whoami
X-API-Key: sk_...
```

**Response `200`:**

```json
{
  "tenant_id": "uuid",
  "user_id": null,
  "plan": "standard",
  "scopes": ["chat:write", "kb:read", "kb:write"],
  "authenticated": true
}
```

---

## 4. Live WhatsApp chat

```http
POST /chat
X-API-Key: sk_...
X-Agent: whatsapp
X-Channel: whatsapp
X-Session-Id: wa:{phone_number_id}:{customer_phone}
X-Product: crm
Content-Type: application/json
```

**Body:**

```json
{
  "message": "What are your pricing plans?",
  "user_number": "+15551234567",
  "company_id": "<ai_tenant_id or crm_company_id>",
  "product": "crm"
}
```

**Response `200`:**

```json
{
  "answer": "Our plans start at ...",
  "sources": ["pricing-guide.pdf"]
}
```

**Errors:** `401`, `422`, `429`, `503` — fall back to local handler on 503/429.

---

## 5. Upload knowledge base

```http
POST /ingest
X-API-Key: sk_...
Content-Type: multipart/form-data
```

**Form fields:**

| Field | Value |
|-------|-------|
| `file` | PDF or DOCX binary |
| `kb_scope` | `support` |
| `company_id` | optional; defaults to tenant from API key |

**Response `200`:**

```json
{
  "source": "pricing.pdf",
  "chunks_indexed": 42,
  "kb_scope": "support"
}
```

**Flow with tenant S3:** upload to tenant bucket first, then stream same file to `/ingest` (or future `storage_uri` field).

---

## 6. List KB documents

```http
GET /knowledge/bases/support/documents
X-API-Key: sk_...
```

**Response `200`:**

```json
{
  "scope": "support",
  "documents": [
    {
      "id": "doc-uuid",
      "source": "pricing.pdf",
      "filename": "pricing.pdf",
      "mime": "application/pdf",
      "chunk_count": 42,
      "kb_scope": "support"
    }
  ]
}
```

---

## 7. Delete KB document

```http
DELETE /knowledge/bases/support/documents/{document_id}
X-API-Key: sk_...
```

**Response `200`:**

```json
{
  "status": "deleted",
  "document_id": "doc-uuid"
}
```

Also delete object from tenant S3 bucket in WhatsApp backend if applicable.

---

## 8. Register conversation data source (superadmin only)

**Who:** AI platform superadmin SPA (not WhatsApp BFF). Uses platform JWT.

### Preset (form defaults)

```http
GET /admin/data-sources/whatsapp-preset
Authorization: Bearer <superadmin_jwt>
```

### CRUD for a provisioned tenant

```http
GET    /admin/tenants/{tenant_id}/data-sources
POST   /admin/tenants/{tenant_id}/data-sources
PATCH  /admin/tenants/{tenant_id}/data-sources/{source_id}
DELETE /admin/tenants/{tenant_id}/data-sources/{source_id}
Authorization: Bearer <superadmin_jwt>
```

Test / discover before save (superadmin JWT):

```http
POST /data-sources/test
POST /data-sources/discover
Authorization: Bearer <superadmin_jwt>
```

**Create body (Mongo WhatsApp example):**

```json
{
  "type": "mongo",
  "name": "WhatsApp conversations",
  "config": {
    "uri": "mongodb://...",
    "db": "whatsapp_db",
    "collections": ["active_chats", "history_chats"]
  },
  "field_mapping": {
    "company_field": "company_id",
    "company_is_object_id": true,
    "user_fields": ["from", "to"],
    "content_field": "body",
    "role_field": "sender_type",
    "role_user_value": "customer",
    "timestamp_field": "created_at"
  },
  "enabled": true
}
```

**Response `201`:** `{ "id", "type", "name", "config": { "uri": "****..." }, ... }`

```http
POST /data-sources/test
X-API-Key: sk_...
```

**Body:** same `type`, `config`, `field_mapping` — **Response:** `{ "ok": true }`

---

## 9. Chatbot config

Tenant-scoped WhatsApp behavior (tone, goals, instructions). Auto-creates defaults on first `GET`.
Requires `kb:read` for read and `kb:write` for save/test.

```http
GET /chatbot/whatsapp/config
X-API-Key: sk_...
```

**Response `200`:**

```json
{
  "id": "uuid",
  "channel": "whatsapp",
  "enabled": true,
  "name": "WhatsApp Bot",
  "tone": "friendly",
  "goals": ["support"],
  "instructions": "",
  "conversion": { "cta_text": null, "cta_url": null, "lead_capture_prompt": null },
  "greeting_message": null,
  "fallback_message": null,
  "handoff_keywords": [],
  "kb_scope": "support",
  "product": "crm",
  "model_profile": null,
  "version": 1,
  "updated_at": "2026-07-05T12:00:00Z"
}
```

```http
PUT /chatbot/whatsapp/config
PATCH /chatbot/whatsapp/config
X-API-Key: sk_...
```

**PUT body** (full replace; include current `version` for optimistic locking):

```json
{
  "version": 1,
  "enabled": true,
  "name": "WhatsApp Bot",
  "tone": "friendly",
  "goals": ["support", "convert"],
  "instructions": "Always mention our 14-day trial.",
  "conversion": { "cta_text": "Start trial", "cta_url": "https://example.com/trial" },
  "greeting_message": "Hi! How can I help?",
  "fallback_message": "I don't have that info — want to speak with an agent?",
  "handoff_keywords": ["human", "agent"],
  "kb_scope": "support",
  "product": "crm"
}
```

**Response `200`:** same shape as GET (with incremented `version`).

**Response `409`:** version conflict — refresh with GET and retry.

```http
POST /chatbot/whatsapp/test
X-API-Key: sk_...
X-Agent: whatsapp
X-Channel: whatsapp
```

**Body:**

```json
{
  "message": "What are your pricing plans?",
  "user_number": "test-user",
  "company_id": "optional-crm-company-id"
}
```

**Response `200`:** `{ "answer": "...", "sources": ["doc.pdf"] }` — uses current config + KB; does **not** persist or send to WhatsApp.

**Response `503`:** chatbot disabled (`enabled: false` on config) or `/chat` when `X-Agent: whatsapp` and AI chatbot is off.

---

## WhatsApp BFF routes (your API for frontend)

| BFF route | Proxies to AI |
|-----------|---------------|
| `POST /api/settings/ai/connect` | `POST /provisioning/tenants` |
| `GET /api/settings/ai/status` | `GET /health/ready` + `GET /auth/whoami` |
| `PATCH /api/settings/ai` | local `ai_enabled` toggle only |
| `POST /api/settings/kb/upload` | `POST /ingest` |
| `GET /api/settings/kb/documents` | `GET /knowledge/bases/support/documents` |
| `DELETE /api/settings/kb/documents/:id` | `DELETE /knowledge/bases/support/documents/:id` |
| `GET /api/settings/chatbot` | `GET /chatbot/whatsapp/config` |
| `PUT /api/settings/chatbot` | `PUT /chatbot/whatsapp/config` |
| `PATCH /api/settings/chatbot` | `PATCH /chatbot/whatsapp/config` |
| `POST /api/settings/chatbot/test` | `POST /chatbot/whatsapp/test` |
| Meta webhook handler | `POST /chat` when `ai_enabled` |
