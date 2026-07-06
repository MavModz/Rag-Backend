"""RBAC: permission catalog and role->scope expansion.

Permissions are flat strings (``"chat:write"``). A role carries a list of them;
``"*"`` is the admin wildcard. Scopes embedded in a JWT (or attached to an API
key) are the expanded permission set the tenant context checks against.
"""
from __future__ import annotations


class Permission:
    CHAT_WRITE = "chat:write"
    KB_READ = "kb:read"
    KB_WRITE = "kb:write"
    USAGE_READ = "usage:read"
    # Manage the tenant's own external data-source connections (self-service).
    DATASOURCES_MANAGE = "datasources:manage"
    ADMIN_TENANTS = "admin:tenants"
    ADMIN_USERS = "admin:users"
    ADMIN_KEYS = "admin:keys"


WILDCARD = "*"

# Default scopes for an API key created without an explicit scope list.
DEFAULT_API_KEY_SCOPES = [Permission.CHAT_WRITE, Permission.KB_READ, Permission.KB_WRITE]


def expand_scopes(role_permission_lists: list[list[str]]) -> list[str]:
    """Union the permission lists of all of a user's roles into a scope list."""
    scopes: set[str] = set()
    for perms in role_permission_lists:
        scopes.update(perms)
    if WILDCARD in scopes:
        return [WILDCARD]
    return sorted(scopes)
