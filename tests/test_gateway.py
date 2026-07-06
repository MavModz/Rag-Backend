"""Model Gateway tests: profile resolution, retry, fallback, usage hook.

No real provider is contacted — a FakeProvider stands in, so these run with no
Ollama/network.
"""
from collections.abc import AsyncIterator

import pytest

from app.platform.gateway.base import LLMProvider
from app.platform.gateway.gateway import ModelGateway
from app.platform.gateway.registry import GatewayRegistry
from app.platform.gateway.types import GenerationResult, Message, ModelProfile, StreamChunk
from app.platform.gateway.usage import UsageTracker


class FakeProvider(LLMProvider):
    def __init__(self, name: str, fail_times: int = 0, text: str = "ok") -> None:
        self.name = name
        self.fail_times = fail_times
        self.text = text
        self.calls = 0

    async def generate(self, model, messages, *, temperature=None, max_tokens=None, timeout=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("boom")
        return GenerationResult(
            text=self.text, provider=self.name, model=model,
            prompt_tokens=1, completion_tokens=2, latency_ms=5,
        )

    async def stream(self, model, messages, *, temperature=None, max_tokens=None, timeout=None) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(text=self.text)


class RecordingUsage(UsageTracker):
    def __init__(self) -> None:
        self.records: list[tuple] = []

    async def record(self, tenant_ctx, profile, result) -> None:
        self.records.append((profile, result))


def _gateway(provider, *profiles, usage=None):
    reg = GatewayRegistry()
    reg.register_provider(provider)
    for p in profiles:
        reg.register_profile(p)
    return ModelGateway(reg, usage or UsageTracker())


async def test_generate_resolves_profile_and_records_usage():
    usage = RecordingUsage()
    gw = _gateway(
        FakeProvider("fake", text="hello"),
        ModelProfile(name="p", provider="fake", model="m", retries=0),
        usage=usage,
    )
    result = await gw.generate("p", [Message("user", "hi")])
    assert result.text == "hello"
    assert result.provider == "fake"
    assert usage.records and usage.records[0][0] == "p"


async def test_unknown_profile_raises():
    gw = _gateway(FakeProvider("fake"))
    with pytest.raises(KeyError):
        await gw.generate("missing", [Message("user", "hi")])


async def test_retry_then_success():
    provider = FakeProvider("fake", fail_times=1)
    gw = _gateway(provider, ModelProfile(name="p", provider="fake", model="m", retries=2))
    result = await gw.generate("p", [Message("user", "hi")])
    assert result.text == "ok"
    assert provider.calls == 2  # failed once, retried once


async def test_fallback_to_secondary_profile():
    reg = GatewayRegistry()
    reg.register_provider(FakeProvider("primary", fail_times=99))
    reg.register_provider(FakeProvider("secondary", text="from-fallback"))
    reg.register_profile(
        ModelProfile(name="p", provider="primary", model="m", retries=0, fallback="fb")
    )
    reg.register_profile(ModelProfile(name="fb", provider="secondary", model="m", retries=0))
    gw = ModelGateway(reg, UsageTracker())
    result = await gw.generate("p", [Message("user", "hi")])
    assert result.text == "from-fallback"


async def test_stream_yields_chunks():
    gw = _gateway(
        FakeProvider("fake", text="streamed"),
        ModelProfile(name="p", provider="fake", model="m"),
    )
    chunks = [c.text async for c in gw.stream("p", [Message("user", "hi")])]
    assert chunks == ["streamed"]


def test_registry_defaults_to_ollama():
    from app.platform.gateway.registry import GatewayRegistry

    reg = GatewayRegistry.with_defaults()
    profile = reg.get_profile("conversation.default")
    assert profile.provider == "ollama"
    summarize = reg.get_profile("memory.summarize")
    assert summarize.temperature == 0.1
    assert summarize.max_tokens == 256


def test_registry_uses_openai_when_configured(monkeypatch):
    from app.config import settings
    from app.platform.gateway.registry import GatewayRegistry

    monkeypatch.setattr(settings, "chat_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "nvapi-test")
    monkeypatch.setattr(settings, "openai_chat_model", "meta/llama-3.1-8b-instruct")
    monkeypatch.setattr(settings, "openai_base_url", "https://integrate.api.nvidia.com/v1")

    reg = GatewayRegistry.with_defaults()
    profile = reg.get_profile("conversation.default")
    assert profile.provider == "openai"
    assert profile.model == "meta/llama-3.1-8b-instruct"
    assert profile.fallback == "conversation.ollama"  # falls back to local
    assert reg.get_provider("openai").name == "openai"
