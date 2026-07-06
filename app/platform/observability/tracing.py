"""Request tracing context.

Holds per-request correlation ids in contextvars so logging, metrics, and rate
limits can read them without threading through every signature. Extended fields
(product, agent, session) are set by the auth dependency after credentials resolve.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_tenant_id: ContextVar[str | None] = ContextVar("tenant_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)
_product: ContextVar[str | None] = ContextVar("product", default=None)
_agent: ContextVar[str | None] = ContextVar("agent", default=None)
_session_id: ContextVar[str | None] = ContextVar("session_id", default=None)
_acting_user_id: ContextVar[str | None] = ContextVar("acting_user_id", default=None)
_auth_mode: ContextVar[str | None] = ContextVar("auth_mode", default=None)


def new_request_id() -> str:
    return uuid.uuid4().hex


def _set(var: ContextVar[str | None], value: str | None) -> object:
    return var.set(value)


def _reset(var: ContextVar[str | None], token: object) -> None:
    var.reset(token)  # type: ignore[arg-type]


# --- request_id ---
def set_request_id(value: str | None) -> object:
    return _set(_request_id, value)


def get_request_id() -> str | None:
    return _request_id.get()


# --- tenant_id ---
def set_tenant_id(value: str | None) -> object:
    return _set(_tenant_id, value)


def get_tenant_id() -> str | None:
    return _tenant_id.get()


# --- user_id (platform user or end-user key for logs) ---
def set_user_id(value: str | None) -> object:
    return _set(_user_id, value)


def get_user_id() -> str | None:
    return _user_id.get()


# --- product / agent / session / acting user / auth mode ---
def set_product(value: str | None) -> object:
    return _set(_product, value)


def get_product() -> str | None:
    return _product.get()


def set_agent(value: str | None) -> object:
    return _set(_agent, value)


def get_agent() -> str | None:
    return _agent.get()


def set_session_id(value: str | None) -> object:
    return _set(_session_id, value)


def get_session_id() -> str | None:
    return _session_id.get()


def set_acting_user_id(value: str | None) -> object:
    return _set(_acting_user_id, value)


def get_acting_user_id() -> str | None:
    return _acting_user_id.get()


def set_auth_mode(value: str | None) -> object:
    return _set(_auth_mode, value)


def get_auth_mode() -> str | None:
    return _auth_mode.get()


def bind_request_context(
    *,
    tenant_id: str | None,
    user_id: str | None,
    product: str | None = None,
    agent: str | None = None,
    session_id: str | None = None,
    acting_user_id: str | None = None,
    auth_mode: str | None = None,
) -> None:
    set_tenant_id(tenant_id)
    set_user_id(user_id)
    set_product(product)
    set_agent(agent)
    set_session_id(session_id)
    set_acting_user_id(acting_user_id)
    set_auth_mode(auth_mode)


def reset_request_context() -> dict[str, object]:
    """Clear tenant/product/session correlation fields (not request_id)."""
    return {
        "tenant_id": set_tenant_id(None),
        "user_id": set_user_id(None),
        "product": set_product(None),
        "agent": set_agent(None),
        "session_id": set_session_id(None),
        "acting_user_id": set_acting_user_id(None),
        "auth_mode": set_auth_mode(None),
    }


def restore_request_context(tokens: dict[str, object]) -> None:
    for name, var in (
        ("tenant_id", _tenant_id),
        ("user_id", _user_id),
        ("product", _product),
        ("agent", _agent),
        ("session_id", _session_id),
        ("acting_user_id", _acting_user_id),
        ("auth_mode", _auth_mode),
    ):
        if name in tokens:
            _reset(var, tokens[name])


def begin_http_request(request_id: str) -> dict[str, object]:
    """Initialize correlation context for an HTTP request. Returns tokens for ``end_http_request``."""
    return {
        "request_id": set_request_id(request_id),
        **reset_request_context(),
    }


def end_http_request(tokens: dict[str, object]) -> None:
    restore_request_context({k: v for k, v in tokens.items() if k != "request_id"})
    _reset(_request_id, tokens["request_id"])



def current_context() -> dict[str, str | None]:
    """Snapshot of correlation ids (for logging/metrics)."""
    return {
        "request_id": _request_id.get(),
        "tenant_id": _tenant_id.get(),
        "user_id": _user_id.get(),
        "product": _product.get(),
        "agent": _agent.get(),
        "session_id": _session_id.get(),
        "acting_user_id": _acting_user_id.get(),
        "auth_mode": _auth_mode.get(),
    }
