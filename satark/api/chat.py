"""POST /v1/chat (CONTRACTS §6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from satark.api.deps import Busy, CaseExpired, get_rt, require_ready
from satark.api.errors import ApiError
from satark.api.limits import rate_limit

router = APIRouter()

MAX_MESSAGE = 1_000
MAX_ACTIVE_RUNS = 50


class ChoiceIn(BaseModel):
    question_id: str
    option_id: str


class ChatIn(BaseModel):
    case_id: str | None = None
    message: str | None = None
    choice: ChoiceIn | None = None
    lang: str
    simple: bool = False


@router.post("/v1/chat", status_code=202)
async def post_chat(body: ChatIn, request: Request, _rl: None = Depends(rate_limit("chat"))):
    rt = get_rt(request)
    require_ready(rt)

    if body.lang not in rt.config.enabled_langs:
        raise ApiError("bad_language", 422, retryable=False)
    if body.message is not None and len(body.message) > MAX_MESSAGE:
        raise ApiError("input_too_large", 413, retryable=False)
    if not body.message and not body.choice:
        raise ApiError("nothing_to_check", 422, retryable=False)

    if rt.orchestrator.active_runs() >= MAX_ACTIVE_RUNS:
        raise ApiError("busy", 503, retryable=True, headers={"Retry-After": "5"})
    try:
        handle = await rt.orchestrator.start_chat(
            case_id=body.case_id,
            message=body.message,
            choice=(body.choice.question_id, body.choice.option_id) if body.choice else None,
            lang=body.lang,
            simple=body.simple,
        )
    except CaseExpired:
        raise ApiError("case_expired", 404, retryable=False) from None
    except Busy:
        raise ApiError("busy", 503, retryable=True, headers={"Retry-After": "5"}) from None

    return JSONResponse(
        {
            "run_id": handle.run_id,
            "case_id": handle.case_id,
            "events_url": f"/v1/runs/{handle.run_id}/events",
            "expires_at": handle.expires_at.isoformat(),
        },
        status_code=202,
    )
