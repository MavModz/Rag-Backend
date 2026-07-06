"""Encryption + redaction for data-source connection strings.

Tenant DB connection strings (which contain passwords) are encrypted at rest in
the ``data_sources.config`` JSON using Fernet, keyed by
``settings.data_source_encryption_key``. If no key is configured (dev), values are
stored in plaintext and a warning is logged. Connection strings are NEVER returned
to clients — the API redacts them.

The secret lives under a per-type key in ``config``: ``uri`` for Mongo, ``dsn`` for
SQL. Everything else in ``config`` (db name, collections, table) is non-secret.
"""
from __future__ import annotations

import re

from cryptography.fernet import Fernet

from app.config import settings
from app.platform.observability.logging import get_logger

logger = get_logger(__name__)

_PREFIX = "enc:"

# Which config key holds the (secret) connection string, per source type.
SECRET_KEY_BY_TYPE = {
    "mongo": "uri",
    "sql": "dsn",
    "mysql": "dsn",
    "postgres": "dsn",
    "postgresql": "dsn",
}


def secret_key_for(source_type: str) -> str:
    return SECRET_KEY_BY_TYPE.get(source_type, "uri")


def _fernet() -> Fernet | None:
    key = settings.data_source_encryption_key
    if not key:
        return None
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(value: str) -> str:
    if not value or value.startswith(_PREFIX):
        return value
    f = _fernet()
    if f is None:
        logger.warning(
            "data_source_encryption_key not set — storing a connection secret in plaintext"
        )
        return value
    return _PREFIX + f.encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    if not value or not value.startswith(_PREFIX):
        return value
    f = _fernet()
    if f is None:
        raise RuntimeError(
            "Encrypted data-source secret found but data_source_encryption_key is not set."
        )
    return f.decrypt(value[len(_PREFIX) :].encode()).decode()


def redact_uri(uri: str) -> str:
    """Hide the password in a connection string for safe display."""
    if not uri:
        return uri
    shown = decrypt_secret(uri) if uri.startswith(_PREFIX) else uri
    return re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:****@", shown)
