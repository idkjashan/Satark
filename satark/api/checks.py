"""POST /v1/checks (CONTRACTS §6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from satark.api.deps import Busy, CheckInput, get_rt, require_ready
from satark.api.errors import ApiError
from satark.api.limits import rate_limit

router = APIRouter()

MAX_TEXT = 4_000
MAX_QR = 1_000
MAX_IMAGE = 2_000_000
MAX_ACTIVE_RUNS = 50  # CONTRACTS §6


def _sniff_image(data: bytes) -> str | None:
    """Magic-byte sniff; never trust the client's declared content-type (LLD §17)."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _has_text_content(text: str | None) -> bool:
    """False for None, "", whitespace-only or emoji/symbol-only text (CONTRACTS §6)."""
    return bool(text) and any(ch.isalnum() for ch in text)


@router.post("/v1/checks", status_code=202)
async def post_checks(
    request: Request,
    text: str | None = Form(None),
    image: UploadFile | None = File(None),  # noqa: B008 - FastAPI's own idiom; evaluated once, immutable marker
    qr: str | None = Form(None),
    lang: str = Form(...),
    simple: bool = Form(False),
    client: str | None = Form(None),
    _rl: None = Depends(rate_limit("checks")),
):
    rt = get_rt(request)
    require_ready(rt)

    if lang not in rt.config.enabled_langs:
        raise ApiError("bad_language", 422, retryable=False)
    if text is not None and len(text) > MAX_TEXT:
        raise ApiError("input_too_large", 413, retryable=False)
    if qr is not None and len(qr) > MAX_QR:
        raise ApiError("input_too_large", 413, retryable=False)

    image_bytes: bytes | None = None
    image_mime: str | None = None
    if image is not None:
        image_bytes = await image.read()
        if image_bytes:
            if len(image_bytes) > MAX_IMAGE:
                raise ApiError("input_too_large", 413, retryable=False)
            image_mime = _sniff_image(image_bytes)
            if image_mime is None:
                raise ApiError("unsupported_media", 415, retryable=False)
        else:
            image_bytes = None

    qr_clean = qr.strip() if qr else ""
    if not _has_text_content(text) and image_bytes is None and not qr_clean:
        raise ApiError("nothing_to_check", 422, retryable=False)

    if rt.orchestrator.active_runs() >= MAX_ACTIVE_RUNS:
        raise ApiError("busy", 503, retryable=True, headers={"Retry-After": "5"})
    try:
        handle = await rt.orchestrator.start_check(
            CheckInput(text=text, image=image_bytes, image_mime=image_mime, qr=qr, lang=lang, simple=simple, client=client)
        )
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
