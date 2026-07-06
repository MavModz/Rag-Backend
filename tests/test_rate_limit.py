"""Rate limiting: a limited route returns 429 once the window is exhausted.

Uses a self-contained in-memory Limiter so the test never depends on the
configured (possibly remote) Redis.
"""
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address


def _app() -> FastAPI:
    app = FastAPI()
    limiter = Limiter(key_func=get_remote_address, storage_uri="memory://", headers_enabled=False)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.get("/ping")
    @limiter.limit("2/minute")
    async def ping(request: Request):  # slowapi needs the Request param
        return {"ok": True}

    return app


def test_rate_limit_trips_after_threshold():
    client = TestClient(_app())
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    # third call within the window is rejected
    assert client.get("/ping").status_code == 429
