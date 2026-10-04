"""GET /v1/meta, GET /healthz, GET /readyz (CONTRACTS §6)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from satark.api.deps import get_rt

router = APIRouter()


@router.get("/v1/meta")
async def get_meta(request: Request):
    rt = get_rt(request)
    sources: list[dict] = []
    if rt.db is not None:
        cfg_sources = rt.config.sources or {}
        for row in rt.db.sources():
            sid = row["source_id"]
            spec = cfg_sources.get(sid, {})
            sources.append(
                {
                    "id": sid,
                    "name": spec.get("name", sid),
                    "group": spec.get("group", ""),
                    "as_on": row["as_on"],
                    "status": row["status"],
                    "rows": row["row_count"],
                }
            )
    languages = [
        {"code": code, "name": spec.get("name", code), "native": spec.get("native", code), "speech": spec.get("speech", "")}
        for code, spec in rt.config.languages.get("languages", {}).items()
        if spec.get("enabled", True)
    ]
    disabled_checkers = [{"id": cid, "reason": reason} for cid, reason in rt.registry.disabled.items()]
    return {
        "sources": sources,
        "languages": languages,
        "disabled_checkers": disabled_checkers,
        "llm": rt.router.status(),
        "tools": tools.status() if (tools := getattr(rt, "tools", None)) is not None else {},  # agent-loop toolsets
        "scoring_version": rt.config.scoring.get("version", ""),
        "version": "0.1.0",
    }


@router.get("/healthz")
async def get_healthz():
    return {"status": "ok"}


@router.get("/readyz")
async def get_readyz(request: Request):
    rt = get_rt(request)
    if not rt.ready:
        return JSONResponse({"status": "not_ready", "reason": rt.not_ready_reason}, status_code=503)
    return {"status": "ready", "checkers": len(rt.registry.all()), "db_version": rt.db.data_version if rt.db else 0}
