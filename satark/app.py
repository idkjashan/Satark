"""FastAPI app factory (CONTRACTS §6; LLD §11, §12, §17, §19).

Run with `uvicorn satark.app:create_app --factory` (or `python -m satark`, see __main__.py).
"""

from __future__ import annotations

import json
import logging
import time
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.datastructures import MutableHeaders
from starlette.middleware.gzip import GZipMiddleware

from satark.api import chat, checks, feedback, meta, practice, report, runs, share, static
from satark.api.errors import install as install_error_handlers
from satark.api.limits import BodySizeLimitMiddleware
from satark.config import Settings

try:
    from satark.harness.runtime import build_runtime, close_runtime
except ImportError:  # pragma: no cover - D's module lands independently (CONTRACTS §1)

    async def build_runtime(settings):  # type: ignore[misc]
        raise RuntimeError("satark.harness.runtime is not available yet")

    async def close_runtime(rt) -> None:  # type: ignore[misc]
        pass


# CONTRACTS §6: identical on every response. No CORS middleware anywhere (LLD §17: same origin only).
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; connect-src 'self'; img-src 'self' blob: data:; "
        "media-src 'self' blob:; style-src 'self' 'unsafe-inline'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(self), microphone=(self), geolocation=()",
}

# LLD §17/§18: only these keys ever reach a log line. Never bodies, IPs or identifiers.
_ALLOWED_LOG_KEYS = {
    "run_id",
    "stage",
    "checker",
    "status",
    "codes",
    "latency_ms",
    "level",
    "path",
    "status_code",
    "kind",
}


class _AllowListFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "severity": record.levelname,
            "msg": record.getMessage(),
        }
        for key in _ALLOWED_LOG_KEYS:
            if key in record.__dict__:
                payload[key] = record.__dict__[key]
        if record.exc_info and record.exc_info[0]:
            # exception type + code locations only: the message and local values could carry identifiers
            payload["error"] = record.exc_info[0].__name__
            payload["where"] = [
                f"{f.filename.rsplit('/', 1)[-1]}:{f.lineno} {f.name}" for f in traceback.extract_tb(record.exc_info[2])
            ][-6:]
        return json.dumps(payload, default=str)


def _configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(_AllowListFormatter())
    root = logging.getLogger("satark")
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    root.propagate = False


class SecurityHeadersMiddleware:
    """Pure ASGI (not BaseHTTPMiddleware) so it never buffers the SSE stream."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for key, value in SECURITY_HEADERS.items():
                    headers[key] = value
            await send(message)

        await self.app(scope, receive, send_wrapper)


class AccessLogMiddleware:
    """Path template + status + latency only (LLD §18) — never the run id or client IP."""

    def __init__(self, app) -> None:
        self.app = app
        self.log = logging.getLogger("satark.access")

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.monotonic()
        status_code = 0

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = scope.get("route")
            path = getattr(route, "path", None) or scope.get("path", "")
            latency_ms = int((time.monotonic() - start) * 1000)
            self.log.info("request", extra={"path": path, "status_code": status_code, "latency_ms": latency_ms})


class _NoGzipForSSE:
    """GZip everywhere except the event stream, which must reach the client unbuffered (CONTRACTS §6)."""

    def __init__(self, app) -> None:
        self.app = app
        self.gzip = GZipMiddleware(app)

    async def __call__(self, scope, receive, send) -> None:
        path = scope.get("path", "")
        if scope["type"] == "http" and path.startswith("/v1/runs/") and path.endswith("/events"):
            await self.app(scope, receive, send)
        else:
            await self.gzip(scope, receive, send)


def create_app(settings: Settings | None = None, runtime=None) -> FastAPI:
    _configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        built_here = app.state.rt is None
        if built_here:
            app.state.rt = await build_runtime(settings or Settings.from_env())  # ConfigError -> startup fails
        try:
            yield
        finally:
            if built_here:
                await close_runtime(app.state.rt)

    app = FastAPI(lifespan=lifespan, title="Satark API", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.rt = runtime  # tests pass a fake/real runtime directly; production builds it in lifespan

    install_error_handlers(app)

    # add_middleware stacks LIFO (last added = outermost); order written outer-to-inner below.
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(_NoGzipForSSE)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(AccessLogMiddleware)

    for module in (checks, runs, chat, practice, report, meta, feedback, share):
        app.include_router(module.router)
    app.include_router(static.router)  # last: catch-all SPA fallback / no-dist landing page

    return app
