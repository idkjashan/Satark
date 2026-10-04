"""Static PWA serving and SPA fallback (CONTRACTS §6; LLD §19.1, §21). Registered last in
app.py so every other route wins first; this only catches what nothing else matched.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response

from satark.api.deps import get_rt
from satark.api.errors import ApiError

router = APIRouter()

# Top-level path segments the SPA must never shadow (CONTRACTS §6): an unknown path under
# any of these is a JSON 404, not index.html.
_RESERVED = {"v1", "healthz", "readyz", "share"}
_NO_DIST_MESSAGE = "Satark API is running; the PWA is not built (npm --prefix web run build)"


def _cache_headers(rel_path: str) -> dict[str, str]:
    name = rel_path.rsplit("/", 1)[-1]
    if rel_path.startswith("assets/"):
        return {"Cache-Control": "public, max-age=31536000, immutable"}
    if name == "sw.js" or name.startswith("manifest"):
        return {"Cache-Control": "no-cache"}
    return {}


async def _serve(full_path: str, request: Request) -> Response:
    # ponytail: sync local-disk stat()/resolve() calls inline on the event loop, same trade-off
    # satark/infra/db.py makes for SQLite; move to asyncio.to_thread if p99 ever shows it mattering.
    rt = get_rt(request)
    web_dist: Path = rt.settings.web_dist
    if full_path.split("/", 1)[0] in _RESERVED:
        raise ApiError("not_found", 404, retryable=False)
    if not web_dist.is_dir():  # noqa: ASYNC240
        return PlainTextResponse(_NO_DIST_MESSAGE)

    if full_path:
        target = (web_dist / full_path).resolve()  # noqa: ASYNC240
        try:
            target.relative_to(web_dist.resolve())  # noqa: ASYNC240
        except ValueError:
            raise ApiError("not_found", 404, retryable=False) from None
        if target.is_file():  # noqa: ASYNC240
            return FileResponse(target, headers=_cache_headers(full_path))

    index = web_dist / "index.html"
    if index.is_file():
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    raise ApiError("not_found", 404, retryable=False)


@router.get("/")
async def spa_root(request: Request) -> Response:
    return await _serve("", request)


@router.get("/{full_path:path}")
async def spa_fallback(full_path: str, request: Request) -> Response:
    return await _serve(full_path, request)
