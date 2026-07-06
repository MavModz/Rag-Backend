"""ModelGateway — the single chokepoint to every LLM.

Callers request a *profile* and never a provider. The gateway resolves the
profile, selects the provider, applies retry + fallback, and records usage.
Cost/plan/priority-aware routing (from ``tenant_ctx``) slots into ``_select_profile``
later without changing callers.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings
from app.platform.gateway.registry import GatewayRegistry
from app.platform.gateway.types import GenerationResult, Message, ModelProfile, StreamChunk
from app.platform.gateway.usage import UsageTracker
from app.platform.observability.logging import get_logger
from app.platform.tenancy.context import TenantContext

logger = get_logger(__name__)


class ModelGateway:
    def __init__(self, registry: GatewayRegistry, usage: UsageTracker | None = None) -> None:
        self._registry = registry
        self._usage = usage or UsageTracker()

    @property
    def registry(self) -> GatewayRegistry:
        return self._registry

    def _select_profile(self, profile: str, tenant_ctx: TenantContext | None) -> ModelProfile:
        # M1: 1:1 profile -> provider. Future: cost/plan/priority routing using tenant_ctx.
        return self._registry.get_profile(profile)

    async def _generate_once(
        self, prof: ModelProfile, messages: list[Message], overrides: dict
    ) -> GenerationResult:
        provider = self._registry.get_provider(prof.provider)
        return await provider.generate(
            prof.model,
            messages,
            temperature=overrides.get("temperature", prof.temperature),
            max_tokens=overrides.get("max_tokens", prof.max_tokens),
            timeout=prof.timeout or settings.gateway_timeout,
        )

    async def _generate_with_retry(
        self, prof: ModelProfile, messages: list[Message], overrides: dict
    ) -> GenerationResult:
        attempts = (prof.retries if prof.retries is not None else settings.gateway_default_retries) + 1
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(multiplier=0.5, max=8),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        ):
            with attempt:
                return await self._generate_once(prof, messages, overrides)
        raise RuntimeError("unreachable")  # pragma: no cover

    async def generate(
        self,
        profile: str,
        messages: list[Message],
        tenant_ctx: TenantContext | None = None,
        **overrides,
    ) -> GenerationResult:
        prof = self._select_profile(profile, tenant_ctx)
        try:
            result = await self._generate_with_retry(prof, messages, overrides)
        except Exception as exc:  # noqa: BLE001
            if prof.fallback:
                logger.warning(
                    "Profile %s failed (%s); falling back to %s", profile, exc, prof.fallback
                )
                fallback = self._registry.get_profile(prof.fallback)
                result = await self._generate_with_retry(fallback, messages, overrides)
            else:
                raise
        await self._usage.record(tenant_ctx, profile, result)
        return result

    async def stream(
        self,
        profile: str,
        messages: list[Message],
        tenant_ctx: TenantContext | None = None,
        **overrides,
    ) -> AsyncIterator[StreamChunk]:
        prof = self._select_profile(profile, tenant_ctx)
        provider = self._registry.get_provider(prof.provider)
        text_parts: list[str] = []
        async for chunk in provider.stream(
            prof.model,
            messages,
            temperature=overrides.get("temperature", prof.temperature),
            max_tokens=overrides.get("max_tokens", prof.max_tokens),
            timeout=prof.timeout or settings.gateway_timeout,
        ):
            text_parts.append(chunk.text)
            yield chunk
        # Usage at end-of-stream (token counts not exposed mid-stream by Ollama).
        result = GenerationResult(
            text="".join(text_parts),
            provider=prof.provider,
            model=prof.model,
            completion_tokens=0,
        )
        await self._usage.record(tenant_ctx, profile, result)


_gateway: ModelGateway | None = None


def get_gateway() -> ModelGateway:
    """Process-wide gateway singleton (registry seeded with config defaults)."""
    global _gateway
    if _gateway is None:
        _gateway = ModelGateway(GatewayRegistry.with_defaults(), UsageTracker())
        logger.info("Model gateway initialized (providers: ollama)")
    return _gateway
