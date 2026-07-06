"""Gateway registry: model profiles + provider instances.

Holds the ``ModelProfile`` set callers select by name and the concrete
``LLMProvider`` instances. ``with_defaults`` builds the runtime set from config:
local Ollama is always available; if ``chat_provider="openai"`` and an API key is
configured, ``conversation.default`` is bound to the OpenAI-compatible endpoint
(OpenAI / NVIDIA NIM / Groq / ...) with Ollama kept as an automatic fallback.

Adding another vendor later is the same shape: register a provider + a profile.
"""
from __future__ import annotations

from app.config import settings
from app.platform.gateway.base import LLMProvider
from app.platform.gateway.providers.ollama import OllamaProvider
from app.platform.gateway.types import ModelProfile


class GatewayRegistry:
    def __init__(self) -> None:
        self._profiles: dict[str, ModelProfile] = {}
        self._providers: dict[str, LLMProvider] = {}

    # --- providers ---
    def register_provider(self, provider: LLMProvider) -> None:
        self._providers[provider.name] = provider

    def get_provider(self, name: str) -> LLMProvider:
        try:
            return self._providers[name]
        except KeyError:
            raise KeyError(f"No LLM provider registered for {name!r}") from None

    # --- profiles ---
    def register_profile(self, profile: ModelProfile) -> None:
        self._profiles[profile.name] = profile

    def get_profile(self, name: str) -> ModelProfile:
        try:
            return self._profiles[name]
        except KeyError:
            raise KeyError(f"Unknown model profile {name!r}") from None

    def profiles(self) -> dict[str, ModelProfile]:
        return dict(self._profiles)

    @classmethod
    def with_defaults(cls) -> "GatewayRegistry":
        """Build the runtime registry from config (providers + chat profile)."""
        registry = cls()

        # Local Ollama is always registered and serves as the fallback.
        registry.register_provider(OllamaProvider())
        registry.register_profile(
            ModelProfile(
                name="conversation.ollama",
                provider="ollama",
                model=settings.ollama_chat_model,
                temperature=settings.ollama_temperature,
                max_tokens=settings.ollama_num_predict,
            )
        )

        # Register an OpenAI-compatible provider when configured (OpenAI / NVIDIA / …).
        openai_ready = bool(settings.openai_api_key) and bool(settings.openai_chat_model)
        if openai_ready:
            from app.platform.gateway.providers.openai_compatible import (
                OpenAICompatibleProvider,
            )

            registry.register_provider(
                OpenAICompatibleProvider(
                    name="openai",
                    base_url=settings.openai_base_url,
                    api_key=settings.openai_api_key,
                )
            )

        # Bind the chat profile to the selected provider.
        if settings.chat_provider.lower() == "openai" and openai_ready:
            registry.register_profile(
                ModelProfile(
                    name="conversation.default",
                    provider="openai",
                    model=settings.openai_chat_model,
                    temperature=settings.ollama_temperature,
                    max_tokens=settings.ollama_num_predict,
                    fallback="conversation.ollama",  # auto-fallback to local
                )
            )
        else:
            registry.register_profile(
                ModelProfile(
                    name="conversation.default",
                    provider="ollama",
                    model=settings.ollama_chat_model,
                    temperature=settings.ollama_temperature,
                    max_tokens=settings.ollama_num_predict,
                )
            )

        summarize_provider = (
            "openai"
            if settings.chat_provider.lower() == "openai" and openai_ready
            else "ollama"
        )
        summarize_model = (
            settings.openai_chat_model
            if summarize_provider == "openai"
            else settings.ollama_chat_model
        )
        registry.register_profile(
            ModelProfile(
                name="memory.summarize",
                provider=summarize_provider,
                model=summarize_model,
                temperature=0.1,
                max_tokens=256,
                fallback="conversation.ollama" if summarize_provider == "openai" else None,
            )
        )
        return registry
