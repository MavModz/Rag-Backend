"""Per-tenant API keys.

A key is shown once at creation (``sk_<random>``). Only its SHA-256 hash is
stored; the short ``prefix`` is indexed for O(1) lookup before a constant-time
hash comparison. This is the auth path used by machine clients (WhatsApp
integration, frontend apps, etc.).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

_KEY_PREFIX = "sk_"
_PREFIX_LEN = 11  # "sk_" + 8 chars


def hash_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Return (full_key, prefix, key_hash). Store prefix + hash; show full once."""
    full_key = _KEY_PREFIX + secrets.token_urlsafe(32)
    return full_key, full_key[:_PREFIX_LEN], hash_key(full_key)


def key_prefix(full_key: str) -> str:
    return full_key[:_PREFIX_LEN]


def verify_key(full_key: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_key(full_key), stored_hash)
