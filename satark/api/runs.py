"""GET /v1/runs/{run_id}/events — Server-Sent Events (CONTRACTS §6.1)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from satark.api.deps import get_rt
from satark.api.errors import ApiError
from satark.api.limits import rate_limit

router = APIRouter()

PING_SECONDS = 10.0
TERMINAL_EVENTS = {"done", "error"}


def _after_id(request: Request) -> int:
    raw = request.headers.get("last-event-id") or request.query_params.get("last_event_id")
    try:
        return int(raw) if raw is not None else 0
    except ValueError:
        return 0


async def _stream(rt, run_id: str, after_id: int) -> AsyncIterator[str]:
    yield "retry: 2000\n\n"
    agen = rt.bus.subscribe(run_id, after_id=after_id).__aiter__()
    pending: asyncio.Task | None = None
    try:
        while True:
            # Keep ONE pending read alive across pings. asyncio.wait_for would cancel it on timeout, and
            # cancelling a generator's __anext__ closes the generator: the stream would end after one ping.
            if pending is None:
                pending = asyncio.ensure_future(agen.__anext__())
            done, _ = await asyncio.wait({pending}, timeout=PING_SECONDS)
            if not done:
                yield ": ping\n\n"
                continue
            try:
                event = pending.result()
            except StopAsyncIteration:
                return
            finally:
                pending = None
            data = json.dumps(event.data, separators=(",", ":"), default=str)
            yield f"id: {event.id}\nevent: {event.type}\ndata: {data}\n\n"
            if event.type in TERMINAL_EVENTS:
                return
    finally:
        if pending is not None:  # the client went away mid-wait
            pending.cancel()


@router.get("/v1/runs/{run_id}/events")
async def get_run_events(run_id: str, request: Request, _rl: None = Depends(rate_limit("events"))):
    rt = get_rt(request)
    if not rt.bus.exists(run_id):
        raise ApiError("run_not_found", 404, retryable=False)
    return StreamingResponse(
        _stream(rt, run_id, _after_id(request)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
