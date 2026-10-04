"""POST /v1/practice: an on-demand 3-question quiz (satark/harness/practice.py)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from satark.api.deps import get_rt, require_ready
from satark.api.errors import ApiError
from satark.api.limits import rate_limit
from satark.harness.practice import make_quiz

router = APIRouter()


class PracticeIn(BaseModel):
    topic: str | None = None
    scam_type: str | None = None
    lang: str


@router.post("/v1/practice")
async def post_practice(body: PracticeIn, request: Request, _rl: None = Depends(rate_limit("practice"))):
    rt = get_rt(request)
    require_ready(rt)
    if body.lang not in rt.config.enabled_langs:
        raise ApiError("bad_language", 422, retryable=False)
    if (body.topic and len(body.topic) > 200) or (body.scam_type and len(body.scam_type) > 20):
        raise ApiError("input_too_large", 413, retryable=False)
    knowledge = getattr(getattr(rt.orchestrator, "responder", None), "knowledge", None)
    return await make_quiz(rt.router, knowledge, rt.config, body.topic, body.scam_type, body.lang)
