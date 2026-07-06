"""EventBus interface + in-process implementation.

The in-process bus invokes subscribed handlers as background asyncio tasks so
publishing never blocks the caller. Swap in a Celery/queue-backed bus later
without changing publishers.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from app.platform.observability.logging import get_logger

logger = get_logger(__name__)

Handler = Callable[[dict], Awaitable[None]]


class EventBus(ABC):
    @abstractmethod
    def subscribe(self, event: str, handler: Handler) -> None:
        ...

    @abstractmethod
    async def publish(self, event: str, payload: dict) -> None:
        ...


class InProcessBus(EventBus):
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = {}

    def subscribe(self, event: str, handler: Handler) -> None:
        self._handlers.setdefault(event, []).append(handler)

    async def publish(self, event: str, payload: dict) -> None:
        for handler in self._handlers.get(event, []):
            asyncio.create_task(self._run(event, handler, payload))

    async def _run(self, event: str, handler: Handler, payload: dict) -> None:
        try:
            await handler(payload)
        except Exception as exc:  # noqa: BLE001 - one handler must not break others
            logger.warning("Event handler for %s failed: %s", event, exc)


_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = InProcessBus()
    return _bus
