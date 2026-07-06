"""Usage tracking hook.

Called by the gateway after every generation. Records metrics + a structured log
line, and writes a per-tenant ``ai_usage`` ledger row off the response path
(fire-and-forget) for a real UUID-keyed tenant. Never raises into the caller.
Phase 8 routes the DB write through the event bus; the fire-and-forget task here
already keeps it off the response latency path.
"""
from __future__ import annotations

import asyncio
import uuid

from app.platform.gateway.types import GenerationResult
from app.platform.observability import metrics
from app.platform.observability.logging import get_logger
from app.platform.tenancy.context import TenantContext

logger = get_logger(__name__)


class UsageTracker:
    async def record(
        self,
        tenant_ctx: TenantContext | None,
        profile: str,
        result: GenerationResult,
    ) -> None:
        try:
            metrics.llm_tokens_total.labels(
                result.provider, result.model, "prompt"
            ).inc(result.prompt_tokens)
            metrics.llm_tokens_total.labels(
                result.provider, result.model, "completion"
            ).inc(result.completion_tokens)
            metrics.llm_latency_seconds.labels(result.provider, result.model).observe(
                result.latency_ms / 1000.0
            )
            logger.info(
                "llm usage profile=%s provider=%s model=%s prompt=%d completion=%d "
                "latency_ms=%d tenant=%s",
                profile, result.provider, result.model, result.prompt_tokens,
                result.completion_tokens, result.latency_ms,
                tenant_ctx.tenant_id if tenant_ctx else "-",
            )
            tenant_id = tenant_ctx.tenant_uuid() if tenant_ctx else None
            if tenant_id is not None:
                asyncio.create_task(self._persist(tenant_id, profile, result))
        except Exception as exc:  # noqa: BLE001 - usage tracking must not break generation
            logger.warning("Usage tracking failed: %s", exc)

    async def _persist(self, tenant_id: uuid.UUID, profile: str, result: GenerationResult) -> None:
        # Imported lazily so the gateway has no hard import-time dependency on the DB.
        from app.modules.model_gateway.models import AiUsage
        from app.platform.db.postgres import get_sessionmaker

        try:
            sessionmaker = get_sessionmaker()
            async with sessionmaker() as session:
                session.add(
                    AiUsage(
                        tenant_id=tenant_id,
                        profile=profile,
                        provider=result.provider,
                        model=result.model,
                        prompt_tokens=result.prompt_tokens,
                        completion_tokens=result.completion_tokens,
                        cost=None,
                        latency_ms=result.latency_ms,
                    )
                )
                await session.commit()
        except Exception as exc:  # noqa: BLE001 - best-effort ledger write
            logger.warning("Failed to persist ai_usage: %s", exc)
