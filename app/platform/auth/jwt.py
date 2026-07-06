"""JWT access/refresh token encode/decode (HS256 by default).

Access tokens carry the claims the tenant context is built from: ``sub`` (user
id), ``tid`` (tenant id), ``plan``, ``roles`` and pre-expanded ``scopes``. Refresh
tokens carry only ``sub``/``tid`` and are exchanged for a new access token.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config import settings


class InvalidToken(Exception):
    pass


def _encode(claims: dict, ttl_seconds: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {**claims, "iat": now, "exp": now + timedelta(seconds=ttl_seconds)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(
    *, sub: str, tid: str, plan: str, roles: list[str], scopes: list[str]
) -> str:
    return _encode(
        {
            "sub": sub,
            "tid": tid,
            "plan": plan,
            "roles": roles,
            "scopes": scopes,
            "type": "access",
        },
        settings.access_token_ttl,
    )


def create_refresh_token(*, sub: str, tid: str) -> str:
    return _encode({"sub": sub, "tid": tid, "type": "refresh"}, settings.refresh_token_ttl)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise InvalidToken(str(exc)) from exc
