"""In-memory abuse controls (CONTRACTS §6; LLD §17): a request-body size cap and per-client-IP
token buckets. Plain module-level dicts — matches the harness's own single-instance, single
-worker design (LLD §3.7); move to Redis if this ever runs with more than one worker (LLD §19.3).

note: a dict with a lazy sweep on every call, not a background task; fine at hackathon
scale (a handful of buckets), revisit if the bucket count ever grows unbounded.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from fastapi import Request

from satark.api.errors import ApiError

MAX_BODY_BYTES = 2_500_000  # CONTRACTS §6 POST /v1/checks; applied to every request, not just that one

_PER_MINUTE = {"checks": 10, "events": 30, "chat": 20, "report": 10, "feedback": 10, "practice": 10}
_IDLE_EVICT_S = 600.0  # CONTRACTS §6: drop buckets idle > 10 min

_413_BODY = json.dumps({"error": {"code": "input_too_large", "message_key": "error.input_too_large", "retryable": False}}).encode()


async def _send_413(send) -> None:
    await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": _413_BODY, "more_body": False})


class BodySizeLimitMiddleware:
    """Caps the request body by actual bytes received, never trusting Content-Length.

    FastAPI's own form-parsing code wraps `request.form()` in a broad try/except and turns
    *any* exception raised while reading into a generic 400 — so raising straight out of a
    wrapped `receive()` never reaches our ApiError handler. Instead we drain (and buffer) the
    body ourselves up front, bailing out and answering 413 directly over the raw ASGI `send`
    the moment the running total passes the cap, or — once fully read within the cap — replay
    the exact same messages to the inner app so it parses normally. Bounded memory: we never
    buffer past max_bytes plus one chunk.
    """

    def __init__(self, app, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        buffered: list[dict] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                buffered.append(message)
                break
            total += len(message.get("body") or b"")
            if total > self.max_bytes:
                await _send_413(send)
                return
            buffered.append(message)
            if not message.get("more_body", False):
                break

        buffered_iter = iter(buffered)

        async def replay_receive():
            for queued in buffered_iter:
                return queued
            return await receive()

        await self.app(scope, replay_receive, send)


def client_ip(request: Request) -> str:
    """The client's address for rate limiting only; never logged (LLD §17)."""
    rt = request.app.state.rt
    if rt is not None and rt.settings.env.get("SATARK_TRUST_PROXY") == "1":
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.rsplit(",", 1)[-1].strip()  # right-most entry; the left can be forged
    return request.client.host if request.client else "unknown"


@dataclass
class _Bucket:
    tokens: float
    updated: float


_buckets: dict[tuple[str, str], _Bucket] = {}


def _scale(request: Request) -> float:
    raw = request.app.state.rt.settings.env.get("SATARK_RATE_LIMIT_SCALE", "1")
    try:
        return float(raw or "1")
    except ValueError:
        return 1.0


def _sweep(now: float) -> None:
    for key in [k for k, b in _buckets.items() if now - b.updated > _IDLE_EVICT_S]:
        del _buckets[key]


def rate_limit(name: str):
    """A FastAPI dependency: raises 429 `rate_limited` once the client's `name` bucket is empty."""
    per_minute = _PER_MINUTE[name]

    def _dep(request: Request) -> None:
        scale = _scale(request)
        if scale <= 0:  # SATARK_RATE_LIMIT_SCALE=0: tests and load runs
            return
        capacity = per_minute * scale
        now = time.monotonic()
        _sweep(now)
        key = (client_ip(request), name)
        bucket = _buckets.get(key)
        if bucket is None:
            bucket = _Bucket(tokens=capacity, updated=now)
            _buckets[key] = bucket
        else:
            elapsed = now - bucket.updated
            bucket.tokens = min(capacity, bucket.tokens + elapsed * (capacity / 60.0))
            bucket.updated = now
        if bucket.tokens < 1:
            raise ApiError("rate_limited", 429, retryable=True, headers={"Retry-After": "5"})
        bucket.tokens -= 1

    return _dep
