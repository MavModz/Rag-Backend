"""Central application configuration — the single source of truth for settings.

Config is layered (12-factor):
  1. The defaults below are the canonical, safe DEV values and the catalog of
     every setting that exists. This file is committed.
  2. `.env` overrides any of these per machine — put ONLY secrets and values that
     differ from the defaults there. `.env` is NOT committed.
  3. `.env.example` is the committed, secret-free template documenting (2).

`pydantic-settings` merges them: default -> `.env` override. Env var names are the
upper-cased field names (e.g. `ollama_chat_model` <- `OLLAMA_CHAT_MODEL`).
Nothing else in the codebase should read os.environ directly — import `settings`.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Ollama ---
    ollama_base_url: str = "http://localhost:11434"
    # Embedding model (vectors only) — mxbai-embed-large -> 1024-dim. This is
    # load-bearing: it must match the dimension the Qdrant collection was built
    # with. Changing it requires `python -m scripts.reset_vectors --yes` + re-ingest.
    ollama_embed_model: str = "bge-m3:latest"
    # Chat/generation model — pull one with `ollama pull <model>` and set here.
    # Embedding models (like qwen3-embedding) CANNOT generate chat; this must be
    # a generative/instruct model such as qwen3:8b or qwen2.5:7b-instruct.
    ollama_chat_model: str = "qcwind/qwen3-8b-instruct-Q4-K-M:latest"
    ollama_request_timeout: float = 120.0
    ollama_temperature: float = 0.2
    # Keep models resident in Ollama so they don't reload between requests.
    # Seconds of idle to keep loaded; -1 = never unload (1800 = 30 min).
    ollama_keep_alive: int = 1800
    # Cap generated tokens so the model doesn't ramble (faster responses).
    ollama_num_predict: int = 512
    # Disable "thinking" for reasoning models (Qwen3): huge latency win, the model
    # answers directly instead of emitting a hidden reasoning trace first.
    ollama_reasoning: bool = False

    # NOTE: There is no global database here. Conversation history is read from
    # each TENANT's own data source (registered via /data-sources and stored in
    # Postgres) — see app.platform.connectors. The platform is DB-independent.

    # --- Qdrant (embedded/local path OR http(s):// server URL) ---
    qdrant_path: str = "./data/qdrant"
    qdrant_collection: str = "kb_documents"

    # --- Retrieval / chunking ---
    top_k: int = 5
    # Fewer chunks for how-to questions — less noise, crisper answers.
    chat_procedural_top_k: int = 3
    chunk_size: int = 800
    chunk_overlap: int = 120
    history_limit: int = 10

    # --- RAG quality (context-aware chunking, hybrid retrieval, reranking) ---
    # "structure" = sentence/paragraph-aware chunking; "fixed" = legacy splitter.
    chunk_strategy: str = "structure"
    # Over-fetch this many candidates, then rerank down to top_k.
    retrieval_candidates: int = 20
    # Cross-encoder reranking (fastembed ONNX; no GPU needed).
    retrieval_rerank: bool = True
    rerank_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    # Hybrid dense+sparse (BM25) fusion in Qdrant. Enabling it changes the
    # collection schema -> run `scripts.reset_vectors --yes` and re-ingest.
    retrieval_hybrid: bool = False
    sparse_model: str = "Qdrant/bm25"

    # --- Uploads (legacy local staging; Phase 7 routes through object storage) ---
    upload_dir: str = "./data/uploads"

    # =====================================================================
    # Platform foundation (M1)
    # =====================================================================

    # --- PostgreSQL (primary platform DB, async) ---
    postgres_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_platform"
    postgres_pool_size: int = 10
    postgres_echo: bool = False

    # --- Redis (sessions, caches, rate-limit counters) ---
    redis_url: str = "redis://3.108.3.175:6379/0"

    # --- Auth / JWT ---
    jwt_secret: str = "dev-insecure-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl: int = 900        # 15 minutes
    refresh_token_ttl: int = 604800    # 7 days
    # LMS/CRM end-user JWT secrets (separate from platform jwt_secret).
    lms_jwt_secret: str = ""
    crm_jwt_secret: str = ""
    # Dev convenience: when true, requests without credentials get a full-access
    # anonymous context (preserves the pre-auth local workflow). Set false in prod.
    auth_allow_anonymous: bool = True
    # Seed bootstrap admin (scripts/seed.py). Change before any real deployment.
    # Must be a deliverable-domain email — EmailStr rejects reserved TLDs like
    # ".local", which would make the admin unable to log in.
    seed_admin_email: str = "admin@example.com"
    seed_admin_password: str = "admin12345"

    # Default product for help chat when LMS/CRM does not send X-Product yet.
    default_chat_product: str = "lms"

    # NRICH Knowledge Base (open-blogs API) — platform content sync.
    nrich_kb_api_base_url: str = "https://knowledgebasebackend.nrichlearning.com"
    nrich_kb_api_timeout: float = 60.0

    # --- Onboarding ---
    # Public self-serve signup (standalone purchasers). Set false for a
    # parent-provisioned-only deployment.
    allow_public_registration: bool = True
    default_signup_plan: str = "free"
    # Shared secret for the purchase-time provisioning endpoint (/provisioning/*),
    # sent as the X-Provisioning-Key header. Empty disables those endpoints.
    provisioning_api_key: str = ""

    # --- Object storage (MinIO / S3) ---
    object_store_backend: str = "local"   # "local" | "s3"
    storage_root: str = "./data/storage"  # local backend root
    s3_endpoint: str = "http://localhost:9000"
    s3_region: str = "us-east-1"
    s3_bucket: str = "ai-platform"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"

    # --- Model Gateway ---
    gateway_default_retries: int = 2
    gateway_timeout: float = 120.0

    # Which provider backs the chat profile ("conversation.default").
    #   "ollama"  -> local Ollama (default)
    #   "openai"  -> any OpenAI-compatible endpoint (OpenAI, NVIDIA NIM, Groq,
    #                Together, ...). Requires openai_api_key + openai_chat_model.
    chat_provider: str = "ollama"
    # OpenAI-compatible endpoint settings. For NVIDIA's free API:
    #   openai_base_url = https://integrate.api.nvidia.com/v1
    #   openai_api_key  = nvapi-...
    #   openai_chat_model = meta/llama-3.1-8b-instruct  (or any NIM model id)
    openai_base_url: str = ""        # empty -> the SDK default (api.openai.com)
    openai_api_key: str = ""
    openai_chat_model: str = ""

    # --- Memory (learn from past chats via Qdrant + summaries) ---
    memory_enabled: bool = True
    qdrant_memory_collection: str = "memory"
    memory_top_k: int = 3
    memory_reflect_min_answer_chars: int = 40
    memory_min_score: float = 0.55

    # --- Rate limiting ---
    rate_limit_enabled: bool = True
    rate_limit_default: str = "60/minute"
    rate_limit_chat: str = "30/minute"
    rate_limit_ingest: str = "10/minute"
    # "memory://" keeps dev runnable without Redis; set to the redis URL in prod
    # (e.g. redis://redis:6379/1) for shared, multi-process counters.
    rate_limit_storage_uri: str = "memory://"

    # --- Observability ---
    log_level: str = "INFO"
    log_format: str = "text"   # "text" (dev) | "json" (prod)
    metrics_enabled: bool = True

    # --- CORS (admin SPA is a separate origin) ---
    # Comma-separated origins, or "*" for any (dev). Set to the admin app origin
    # (e.g. http://localhost:3000) in production.
    cors_allow_origins: str = "*"

    # --- Data-source connection secrets ---
    # Fernet key used to encrypt tenant DB connection strings at rest in the
    # data_sources table. Generate one with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Empty in dev -> connection strings are stored in plaintext (a warning is logged).
    data_source_encryption_key: str = ""

    # --- Worker / events ---
    # Empty broker URL -> in-process event bus (no Celery worker required).
    celery_broker_url: str = ""
    celery_result_backend: str = ""


@lru_cache
def get_settings() -> Settings:
    """Cached singleton accessor."""
    return Settings()


settings = get_settings()
