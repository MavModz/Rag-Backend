"""Logging setup. Import `get_logger(__name__)` anywhere.

Supports two formats (config ``log_format``):
  - "text" (default, dev): human-readable single line, with correlation ids when present
  - "json" (prod): one JSON object per line via orjson, easy to ship to Loki/ELK

Every record is enriched with the current request_id / tenant_id / user_id from
``app.platform.observability.tracing`` so logs are correlatable across layers.
The public ``get_logger`` interface never changes for callers.
"""
from __future__ import annotations

import logging
import sys

import orjson

from app.config import settings
from app.platform.observability import tracing

_CONFIGURED = False


class _ContextFilter(logging.Filter):
    """Attach correlation ids from contextvars onto each record."""

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = tracing.current_context()
        record.request_id = ctx["request_id"] or "-"
        record.tenant_id = ctx["tenant_id"] or "-"
        record.user_id = ctx["user_id"] or "-"
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "tenant_id": getattr(record, "tenant_id", "-"),
            "user_id": getattr(record, "user_id", "-"),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return orjson.dumps(payload).decode("utf-8")


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_ContextFilter())
    if settings.log_format.lower() == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-7s | %(name)s | "
                "req=%(request_id)s tenant=%(tenant_id)s | %(message)s"
            )
        )
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    root.handlers.clear()
    root.addHandler(handler)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    _configure()
    return logging.getLogger(name)
