"""Prometheus metrics.

Defines the platform's core metrics and renders them for the /metrics endpoint.
Metric objects are module-level singletons (the Prometheus client registry is
global), so importing this module more than once is safe.
"""
from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

# --- HTTP ---
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests.",
    ["method", "path", "status"],
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "path"],
)

# --- LLM (Model Gateway) ---
llm_tokens_total = Counter(
    "llm_tokens_total",
    "LLM tokens processed.",
    ["provider", "model", "kind"],  # kind = prompt | completion
)
llm_latency_seconds = Histogram(
    "llm_latency_seconds",
    "LLM generation latency in seconds.",
    ["provider", "model"],
)

# --- RAG ---
rag_retrieval_seconds = Histogram(
    "rag_retrieval_seconds",
    "Vector retrieval latency in seconds.",
)


def render() -> tuple[bytes, str]:
    """Return (body, content_type) for the metrics endpoint."""
    return generate_latest(), CONTENT_TYPE_LATEST
