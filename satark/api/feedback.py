"""POST /v1/feedback (CONTRACTS §6): an anonymous counter, nothing stored."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from satark.api.limits import rate_limit

router = APIRouter()
log = logging.getLogger("satark.counters")


class FeedbackIn(BaseModel):
    case_id: str | None = None
    kind: Literal["helpful", "mistake"]
    level: str | None = None
    reason_codes: list[str] | None = None


@router.post("/v1/feedback", status_code=204)
async def post_feedback(body: FeedbackIn, _rl: None = Depends(rate_limit("feedback"))):
    # Allow-listed keys only (LLD §17): kind, level, codes. No case_id, no body text.
    log.info("feedback", extra={"kind": body.kind, "level": body.level, "codes": body.reason_codes})
    return Response(status_code=204)
