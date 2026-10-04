"""POST /v1/report-draft (CONTRACTS §6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from satark.api.deps import get_rt
from satark.api.errors import ApiError
from satark.api.limits import rate_limit
from satark.harness.report import draft_report

router = APIRouter()


class ReportAnswers(BaseModel):
    when: str | None = Field(default=None, max_length=200)
    how_paid: str | None = Field(default=None, max_length=200)
    amount_band: str | None = Field(default=None, max_length=200)


class ReportIn(BaseModel):
    case_id: str = Field(max_length=64)
    lang: str = Field(max_length=8)
    answers: ReportAnswers = ReportAnswers()


@router.post("/v1/report-draft")
async def post_report_draft(body: ReportIn, request: Request, _rl: None = Depends(rate_limit("report"))):
    rt = get_rt(request)
    case = rt.cases.get(body.case_id)
    if case is None:
        raise ApiError("case_expired", 404, retryable=False)
    return draft_report(case, rt.config, body.lang, body.answers.model_dump())
