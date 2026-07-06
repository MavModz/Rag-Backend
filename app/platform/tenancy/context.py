"""TenantContext — the identity + entitlements carried with every request.

Built by the auth dependency (Phase 6) from a JWT or API key and passed
explicitly into the gateway, connectors, and vector search (and mirrored into the
tracing contextvars for logging/metrics). Every tenant-scoped operation reads
``tenant_id`` from here; ``plan`` / ``budget`` / ``priority`` feed cost-aware model
routing in the gateway.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class TenantContext:
    tenant_id: str
    plan: str = "free"
    budget: float = 0.0
    priority: int = 0
    user_id: str | None = None
    roles: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    is_authenticated: bool = True

    def has(self, permission: str) -> bool:
        """True if the context grants ``permission`` (``*`` is a wildcard)."""
        return "*" in self.scopes or permission in self.scopes

    def tenant_uuid(self) -> uuid.UUID | None:
        """The platform tenant id as a UUID, or None for the anonymous/dev context.

        Persistence is gated on this: rows are only written for a real, UUID-keyed
        tenant — never for the dev anonymous context.
        """
        try:
            return uuid.UUID(self.tenant_id)
        except (ValueError, TypeError, AttributeError):
            return None
