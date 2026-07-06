"""RequestContext — tenant + product + agent + session carried per HTTP request."""
from __future__ import annotations

from dataclasses import dataclass, field

from starlette.requests import Request

from app.modules.knowledge.constants import DEFAULT_KB_SCOPE
from app.platform.auth import rbac
from app.platform.tenancy.constants import (
    AGENT_KB_SCOPE,
    AuthMode,
    KNOWN_AGENTS,
    KNOWN_PRODUCTS,
)
from app.platform.tenancy.context import TenantContext


def _normalize_slug(value: str | None, allowed: frozenset[str]) -> str | None:
    if not value:
        return None
    slug = value.strip().lower()
    return slug if slug in allowed else None


def agent_to_kb_scope(agent: str | None) -> str:
    if not agent:
        return DEFAULT_KB_SCOPE
    return AGENT_KB_SCOPE.get(agent, DEFAULT_KB_SCOPE)


@dataclass
class RequestContext(TenantContext):
    """Full request identity: platform tenant + product surface + agent + session.

    Subclasses ``TenantContext`` so existing permission checks and ``tenant_uuid()``
    keep working on routes that only need tenant scope.
    """

    auth_mode: str = AuthMode.ANONYMOUS
    product: str | None = None
    agent: str | None = None
    kb_scope: str = DEFAULT_KB_SCOPE
    session_id: str | None = None
    external_user_id: str | None = None
    acting_user_id: str | None = None
    channel: str | None = None
    product_roles: list[str] = field(default_factory=list)
    org_id: str | None = None

    def effective_kb_scope(self) -> str:
        """KB scope for retrieval: explicit ``kb_scope`` or derived from ``agent``."""
        if self.agent:
            return agent_to_kb_scope(self.agent)
        return self.kb_scope or DEFAULT_KB_SCOPE

    def conversation_key(self) -> str | None:
        """Stable key for history/memory: session_id preferred, else external_user_id."""
        return self.session_id or self.external_user_id

    def apply_headers(self, request: Request) -> None:
        """Merge optional routing headers (product, agent, session, acting user)."""
        product = _normalize_slug(request.headers.get("X-Product"), KNOWN_PRODUCTS)
        agent = _normalize_slug(request.headers.get("X-Agent"), KNOWN_AGENTS)
        if product:
            self.product = product
        if agent:
            self.agent = agent
            self.kb_scope = agent_to_kb_scope(agent)
        session_id = (request.headers.get("X-Session-Id") or "").strip()
        if session_id:
            self.session_id = session_id
        acting = (request.headers.get("X-Acting-User-Id") or "").strip()
        if acting:
            self.acting_user_id = acting
        channel = (request.headers.get("X-Channel") or "").strip().lower()
        if channel:
            self.channel = channel

    @classmethod
    def from_tenant(cls, tenant: TenantContext, *, auth_mode: str) -> RequestContext:
        return cls(
            tenant_id=tenant.tenant_id,
            plan=tenant.plan,
            budget=tenant.budget,
            priority=tenant.priority,
            user_id=tenant.user_id,
            roles=list(tenant.roles),
            scopes=list(tenant.scopes),
            is_authenticated=tenant.is_authenticated,
            auth_mode=auth_mode,
        )

    def enrich_product_user(
        self,
        *,
        product: str,
        external_user_id: str,
        product_roles: list[str],
        org_id: str | None,
    ) -> None:
        self.product = product
        self.external_user_id = external_user_id
        self.product_roles = product_roles
        self.org_id = org_id
        if self.auth_mode == AuthMode.API_KEY:
            self.auth_mode = AuthMode.API_KEY_PRODUCT_USER
        elif self.auth_mode == AuthMode.ANONYMOUS:
            self.auth_mode = AuthMode.PRODUCT_USER_JWT

    @classmethod
    def anonymous(cls) -> RequestContext:
        return cls(
            tenant_id="anonymous",
            plan="dev",
            scopes=[rbac.WILDCARD],
            is_authenticated=False,
            auth_mode=AuthMode.ANONYMOUS,
        )
