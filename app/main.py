"""FastAPI application factory and wiring.

Mounts module routers and manages the lifespan of shared clients (MongoDB).
Qdrant and Ollama clients are created lazily on first use. As the platform
grows, new services are mounted here as additional module routers.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.modules import health
from app.modules.admin import router as admin_router
from app.modules.chatbot import router as chatbot_router
from app.modules.chatbot.exceptions import ChatbotSchemaNotReadyError
from app.modules.conversation import router as conversation_router
from app.modules.datasources import router as datasources_router
from app.modules.identity import router as identity_router
from app.modules.knowledge import router as knowledge_router
from app.modules.knowledge import platform_router as knowledge_platform_router
from app.modules.memory import router as memory_router
from app.modules.provisioning import router as provisioning_router
from app.modules.knowledge.rag import embeddings, vector_store
from app.platform.cache import redis as redis_cache
from app.platform.connectors import registry as connector_registry
from app.platform.db import postgres
from app.platform.gateway.providers import ollama
from app.platform.middleware import install_middleware
from app.platform.observability.logging import get_logger
from app.platform.ratelimit.limiter import install_rate_limiting

logger = get_logger(__name__)


async def _prewarm() -> None:
    """Load both Ollama models into memory so the first user request is fast."""
    try:
        await asyncio.to_thread(embeddings.embed_query, "warmup")
        await ollama.generate("You are a warmup probe.", "hi")
        logger.info("Model prewarm complete (embed + chat loaded)")
    except Exception as exc:  # noqa: BLE001 - warmup is best-effort
        logger.warning("Model prewarm skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # No global DB connection: each tenant's data source opens its own client
    # lazily on first use (see app.platform.connectors).
    # Warm the models in the background so startup isn't blocked but the first
    # real request doesn't pay the cold-load cost.
    asyncio.create_task(_prewarm())
    logger.info("Application startup complete")
    try:
        yield
    finally:
        vector_store.close()
        await connector_registry.get_connector_registry().close_all()
        await redis_cache.close()
        await postgres.dispose()
        logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(title="Enterprise AI Platform", version="0.2.0", lifespan=lifespan)

    @app.exception_handler(ChatbotSchemaNotReadyError)
    async def chatbot_schema_not_ready(_request, exc: ChatbotSchemaNotReadyError):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    install_rate_limiting(app)
    install_middleware(app)

    # CORS for the separate-origin superadmin SPA (Next.js). The SPA authenticates
    # with Bearer tokens (no cookies), so credentials aren't needed with wildcard.
    origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
    wildcard = not origins or origins == ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if wildcard else origins,
        allow_credentials=not wildcard,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(identity_router.router)
    app.include_router(admin_router.router)
    app.include_router(provisioning_router.router)
    app.include_router(datasources_router.router)
    app.include_router(conversation_router.router)
    app.include_router(chatbot_router.router)
    app.include_router(knowledge_router.router)
    app.include_router(knowledge_platform_router.router)
    app.include_router(memory_router.router)

    return app


app = create_app()
