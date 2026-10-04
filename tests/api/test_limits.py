"""satark/api/limits.py: the body-size ASGI guard and the per-IP token buckets (CONTRACTS §6)."""

from __future__ import annotations

import dataclasses
import json

import httpx

from satark.api.limits import BodySizeLimitMiddleware
from satark.app import create_app


async def test_body_size_middleware_rejects_mid_stream_ignoring_content_length():
    """Content-Length lies (says 10 bytes) but the actual streamed chunks exceed the cap; the
    middleware must reject based on bytes actually seen, and must answer 413 directly (it
    cannot rely on an exception surviving FastAPI's own try/except around form parsing)."""
    app_should_not_run = False

    async def app(scope, receive, send):  # pragma: no cover - must not run once over the cap
        nonlocal app_should_not_run
        app_should_not_run = True

    middleware = BodySizeLimitMiddleware(app, max_bytes=10)
    chunks = [b"x" * 6, b"x" * 6]  # 12 bytes total > 10, even though Content-Length below says 10

    async def receive():
        if chunks:
            body = chunks.pop(0)
            return {"type": "http.request", "body": body, "more_body": bool(chunks)}
        return {"type": "http.disconnect"}

    sent = []

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "headers": [(b"content-length", b"10")]}
    await middleware(scope, receive, send)

    assert app_should_not_run is False
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413
    assert json.loads(sent[1]["body"])["error"]["code"] == "input_too_large"


async def test_body_size_middleware_passes_small_body_through():
    seen = []

    async def app(scope, receive, send):
        seen.append(await receive())

    middleware = BodySizeLimitMiddleware(app, max_bytes=1000)

    async def receive():
        return {"type": "http.request", "body": b"ok", "more_body": False}

    async def send(message):
        pass

    await middleware({"type": "http", "headers": []}, receive, send)
    assert seen == [{"type": "http.request", "body": b"ok", "more_body": False}]


async def test_rate_limit_enforced_when_scaled_on(settings, config):
    from satark.api import limits as limits_mod
    from tests.api.fakes import build_fake_runtime

    limits_mod._buckets.clear()  # isolate from any other test's buckets (module-global state)
    # The rate limiter reads SATARK_RATE_LIMIT_SCALE off rt.settings, so the fake runtime
    # itself must be built with the scaled settings, not just `create_app`'s `settings=` arg
    # (which is only used when `runtime` is None — see satark/app.py's lifespan).
    scaled = dataclasses.replace(settings, env={**settings.env, "SATARK_RATE_LIMIT_SCALE": "1"})
    rt = build_fake_runtime(scaled, config)
    app = create_app(settings=scaled, runtime=rt)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        statuses = []
        for _ in range(12):  # feedback bucket: 10/min
            resp = await client.post("/v1/feedback", json={"kind": "helpful"})
            statuses.append(resp.status_code)
        assert statuses.count(204) == 10
        assert statuses[10:] == [429, 429]
        last = await client.post("/v1/feedback", json={"kind": "helpful"})
        assert last.status_code == 429
        assert last.json()["error"]["code"] == "rate_limited"
        assert last.headers["retry-after"] == "5"


async def test_rate_limit_off_when_scale_zero(client):
    """The `settings` fixture already sets SATARK_RATE_LIMIT_SCALE=0 (tests/conftest.py)."""
    for _ in range(25):  # well over the feedback bucket's 10/min
        resp = await client.post("/v1/feedback", json={"kind": "helpful"})
        assert resp.status_code == 204
