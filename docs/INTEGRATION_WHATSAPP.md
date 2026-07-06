# WhatsApp + LMS/CRM Integration Guide

How external products (WhatsApp platform, LMS, CRM) connect to this AI platform.
**Meta WhatsApp API lives on the WhatsApp project** — this repo is a headless RAG
backend called over HTTPS.

---

## Two-system architecture

```
Meta WhatsApp API
       │
       ▼
WhatsApp Project (owns Meta webhook, admin UI, shouldRouteToAI toggle)
       │  HTTPS + X-API-Key (server-to-server)
       ▼
AI Platform (this repo — tenant, KB, chat, connectors, Postgres + Qdrant)
```

| Responsibility | WhatsApp / LMS / CRM project | AI platform |
|----------------|------------------------------|-------------|
| Meta webhook + Graph API send | Yes | No |
| Admin settings UI (KB, chatbot) | Yes (proxies to AI) | Stores data |
| `shouldRouteToAI()` routing | Yes | No |
| `X-API-Key` storage | Encrypted on product backend | `api_keys` table |
| KB vectors + tenant docs | No | Yes |
| Mongo/MySQL chat history (source of truth) | Yes | Read via connector |
| End-user login to AI | No | N/A |

---

## Actors and authentication

| Actor | Signs up on AI? | Credential |
|-------|-----------------|------------|
| Platform operator (you) | Optional superadmin JWT | `PROVISIONING_API_KEY` in `.env` |
| Customer org (tenant) | Provisioned once | `sk_…` API key on product backend |
| Company admin | No — uses WhatsApp/LMS/CRM UI only | Product JWT (WhatsApp), not AI |
| End user (student, lead, WhatsApp customer) | No | IDs passed per request |

### Which key when?

| Key | Who holds it | Used for |
|-----|--------------|----------|
| `X-Provisioning-Key` | AI `.env` + trusted product **backend** only | `POST /provisioning/tenants` (once per org) |
| `X-API-Key` (`sk_…`) | Product backend per company | `/chat`, `/ingest`, `/data-sources`, config |
| WhatsApp admin JWT | Browser session | WhatsApp BFF only — **never** sent to AI |

---

## `PROVISIONING_API_KEY` setup

Not issued by an API — **you generate and configure it**.

1. Generate: `openssl rand -hex 32`
2. Set on **AI platform** (`.env`):

   ```env
   PROVISIONING_API_KEY=your_generated_secret
   ```

3. Set the **same value** on **WhatsApp backend** (server env only):

   ```env
   AI_PROVISIONING_KEY=your_generated_secret
   AI_BASE_URL=https://ai.yourcompany.com
   ```

4. Restart AI server. If `PROVISIONING_API_KEY` is empty, `/provisioning/*` returns **404**.

Never expose provisioning key in browser, CRM admin UI, or git.

---

## Phase A — Provision tenant (one-time per company)

**Who calls:** WhatsApp backend when admin clicks **Connect AI** (or on company signup).

**Creates in AI Postgres:**

| Table | What |
|-------|------|
| `tenants` | Customer org |
| `users` | One AI admin user (email + password) |
| `api_keys` | One `sk_…` for API calls |

Does **not** create LMS/CRM/WhatsApp end users.

### Request

```http
POST /provisioning/tenants
X-Provisioning-Key: <PROVISIONING_API_KEY from .env>
Content-Type: application/json
```

```json
{
  "name": "Acme Corp WhatsApp",
  "plan": "standard",
  "admin_email": "admin@acme.com",
  "admin_password": null
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `name` | Yes | Company display name |
| `admin_email` | Yes | Valid email; idempotent skip if already exists globally |
| `plan` | No | Defaults to `DEFAULT_SIGNUP_PLAN` |
| `admin_password` | No | Omitted → generated and returned once |

### Response (`201`)

```json
{
  "tenant_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "admin_email": "admin@acme.com",
  "admin_password": "generated-if-omitted",
  "api_key": "sk_xxxxxxxx"
}
```

**Save on WhatsApp backend (encrypted):**

- `ai_tenant_id` ← `tenant_id`
- `ai_api_key` ← `api_key` (shown **once**)
- `crm_company_id` ← link to CRM Mongo `company_id`

### curl example

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

### Errors

| Code | Meaning |
|------|---------|
| `404` | `PROVISIONING_API_KEY` not set on AI |
| `401` | Wrong `X-Provisioning-Key` |
| `409` | `admin_email` already exists |

---

## Phase B — Register conversation data source (superadmin only)

**Who calls:** Superadmin console (platform JWT) — **not** company admin UI.

Stores encrypted Mongo URI + collection names + field mapping in AI `data_sources` for the **provisioned tenant**.

### Preset (load form defaults)

```http
GET /admin/data-sources/whatsapp-preset
Authorization: Bearer <superadmin_jwt>
```

Returns default `type`, `name`, `config.collections` (`active_chats`, `history_chats`), and `field_mapping` for WhatsApp Mongo.

### CRUD per tenant

```http
GET    /admin/tenants/{tenant_id}/data-sources
POST   /admin/tenants/{tenant_id}/data-sources
GET    /admin/tenants/{tenant_id}/data-sources/{source_id}
PATCH  /admin/tenants/{tenant_id}/data-sources/{source_id}
DELETE /admin/tenants/{tenant_id}/data-sources/{source_id}
Authorization: Bearer <superadmin_jwt>
```

Test connection and schema discovery (before save):

```http
POST /data-sources/test
POST /data-sources/discover
Authorization: Bearer <superadmin_jwt>
```

**Create body example:**

```json
{
  "type": "mongo",
  "name": "WhatsApp conversations",
  "config": {
    "uri": "mongodb://ai_reader:pass@host:27017",
    "db": "whatsapp_production",
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

- **URI** is encrypted at rest (`DATA_SOURCE_ENCRYPTION_KEY` in prod).
- **Collection names** are not secret.
- **Field mapping** adapts your Mongo schema to the connector — see below.

Verify: `POST /data-sources/test` with same config.

### LMS (MySQL) example

```json
{
  "type": "mysql",
  "name": "LMS conversations",
  "config": {
    "dsn": "mysql://ai_reader:pass@host/lms_db",
    "table": "chat_messages"
  },
  "field_mapping": {
    "user_columns": ["user_id"],
    "company_column": "institute_id",
    "content_column": "message",
    "role_column": "sender",
    "role_user_value": "student",
    "timestamp_column": "created_at"
  }
}
```

---

## Field mapping (why it is required)

The connector normalizes every DB into `ChatTurn { role, content, timestamp }`.
Your LMS/CRM/WhatsApp schemas use different column names — mapping tells the
connector which fields mean user, content, role, and timestamp.

| Mapping key (Mongo) | Default | Purpose |
|---------------------|---------|---------|
| `user_fields` | `["from","to"]` | Match end-user id (phone, user_id) |
| `content_field` | `"content"` | Message text |
| `role_field` | `"direction"` | Who sent it |
| `role_user_value` | `"incoming"` | Value = customer spoke |
| `timestamp_field` | `"timestamp"` | Sort order |
| `company_field` | `"company_id"` | Org filter (`""` to skip) |

Without correct mapping, history is empty or roles are inverted.

---

## Phase C — Admin enables AI (WhatsApp settings)

**Who:** Company admin in WhatsApp platform → Settings → AI Chatbot.

| Action | Where stored | AI API called? |
|--------|--------------|----------------|
| Toggle AI ON | WhatsApp DB `ai_enabled` | No |
| Toggle AI OFF | WhatsApp DB | No — local handler only |

`shouldRouteToAI()` lives on WhatsApp backend. AI is not involved in the toggle.

---

## Phase D — Admin uploads knowledge base

**Admin uses WhatsApp UI** — does **not** call AI directly or see `sk_…`.

```
Browser → WhatsApp BFF → AI Platform
```

**WhatsApp BFF → AI:**

```http
POST /ingest
X-API-Key: sk_...
Content-Type: multipart/form-data

file: <pdf>
kb_scope: support
company_id: <crm_company_id or ai_tenant_id>
```

| Field | Value |
|-------|-------|
| `X-API-Key` | Decrypted `ai_api_key` for this workspace |
| `kb_scope` | `support` (from `chatbot_configs.kb_scope` at runtime) |
| `company_id` | CRM `company_id` or AI `tenant_id` string |

List/delete: `GET/DELETE /knowledge/bases/support/documents/{id}` with same API key.

---

## Phase E — Admin configures chatbot

**WhatsApp BFF proxies** to AI `chatbot/` module:

```http
GET /chatbot/whatsapp/config
PUT /chatbot/whatsapp/config
PATCH /chatbot/whatsapp/config
POST /chatbot/whatsapp/test
X-API-Key: sk_...
```

```json
{
  "version": 1,
  "enabled": true,
  "tone": "friendly",
  "instructions": "Always mention our 14-day trial.",
  "goals": ["support", "convert"],
  "kb_scope": "support",
  "product": "crm"
}
```

On save, AI syncs to `prompt_templates` (`chatbot.whatsapp.system`) and uses the config at `/chat` runtime when `X-Agent: whatsapp`. If `enabled: false`, `/chat` returns **503**.

---

## Phase F — Live WhatsApp message (runtime)

```
Customer → Meta → WhatsApp webhook
              → shouldRouteToAI() == true
              → POST /chat
              → answer
              → Meta Graph API → customer
```

```http
POST /chat
X-API-Key: sk_...
X-Agent: whatsapp
X-Channel: whatsapp
X-Session-Id: wa:PHONE_NUMBER_ID:+15551234567
Content-Type: application/json
```

```json
{
  "message": "What are your prices?",
  "user_number": "+15551234567",
  "company_id": "507f1f77bcf86cd799439012",
  "product": "crm"
}
```

| Field | CRM WhatsApp example |
|-------|----------------------|
| `user_number` | Customer phone or CRM `user_id` |
| `company_id` | CRM `company_id` (ObjectId string) |
| `X-Session-Id` | `wa:{meta_phone_id}:{customer_phone}` |

When `shouldRouteToAI()` is false, WhatsApp handles locally (human queue, rules) —
AI is not called.

---

## What is stored in AI DB (identity)

End users do **not** need rows in AI `users` table. That table is for AI platform
admin login only.

| Data | Stored in AI? | Where |
|------|---------------|-------|
| CRM/LMS user profile (name, email) | No | LMS MySQL / CRM Mongo |
| Org | Yes | `tenants` (+ optional `external_org_id`) |
| API key hash | Yes | `api_keys` |
| Opaque user ref | Yes | `sessions.external_user_id` |
| AI chat turns | Yes | `messages` (only when `/chat` called) |
| Memory insights | Yes | `memories` + Qdrant |
| Full chat archive | No | Product DB; AI reads via connector |

---

## Chat history strategy (active + history collections)

Do **not** sync all chats into AI Postgres on every message.

1. Register both collections in data source: `active_chats`, `history_chats`
2. On each `/chat`, connector pulls last N turns (`history_limit`, default 10)
3. When chat moves to history after 24h, add `session_summary` on archive (WhatsApp)
4. Long-term context via `memory` module (optional)

---

## Workspace mapping (WhatsApp backend)

Suggested columns on WhatsApp `workspaces` table:

| Column | Source |
|--------|--------|
| `crm_company_id` | CRM Mongo ObjectId string |
| `ai_tenant_id` | From `POST /provisioning/tenants` |
| `ai_api_key` | Encrypted `sk_…` from provision |
| `ai_enabled` | Admin toggle |
| `ai_connection_status` | `disconnected` \| `connected` \| `error` |

Meta tokens stay in WhatsApp DB only — never sent to AI.

---

## Integration rollout order

| Phase | WhatsApp project | AI platform |
|-------|------------------|-------------|
| **1** | Store credentials, `POST /chat` client, `shouldRouteToAI`, Meta reply | Use existing `/chat` |
| **2** | KB upload BFF → `/ingest` | Use existing `/ingest` |
| **3** | Superadmin registers Mongo via `/admin/tenants/{id}/data-sources` | Preset at `/admin/data-sources/whatsapp-preset` |
| **4** | Chatbot settings BFF | Proxy `/chatbot/whatsapp/*` |
| **5** | `session_summary` on archive | Optional connector extension |

---

## LMS / CRM help chat (same platform, different product)

```http
POST /chat
X-API-Key: sk_...
X-Product: lms
Content-Type: application/json

{
  "message": "How do I create a course?",
  "user_number": "991",
  "company_id": "inst_42",
  "product": "lms"
}
```

CRM:

```http
X-Product: crm
X-Agent: whatsapp

{
  "user_number": "507f1f77bcf86cd799439011",
  "company_id": "507f1f77bcf86cd799439012",
  "product": "crm"
}
```

---

## Related README sections

- [Authentication](../README.md#authentication) — header reference
- [Provisioning](../README.md#provisioning-provisioning) — endpoint table
- [Data sources](../README.md#data-sources-data-sources) — connector API
- [Environment variables](../README.md#environment-variables) — `PROVISIONING_API_KEY`
