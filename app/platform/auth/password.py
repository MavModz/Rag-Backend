"""Password hashing (bcrypt).

Uses the ``bcrypt`` library directly (rather than passlib) to avoid the
passlib/bcrypt-5 compatibility warning and keep a single small dependency.
"""
from __future__ import annotations

import bcrypt

# bcrypt truncates at 72 bytes; we guard explicitly for clarity.
_MAX_BYTES = 72


def hash_password(password: str) -> str:
    pw = password.encode("utf-8")[:_MAX_BYTES]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8")[:_MAX_BYTES], password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False
