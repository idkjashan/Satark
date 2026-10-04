"""POST /share (CONTRACTS §6; LLD §22.2): fallback for when the PWA's service worker, which
normally intercepts the Web Share Target POST, is not active yet. Files are ignored — the
PWA re-shares images once installed; this path only has to get the text in front of the user.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Form
from fastapi.responses import RedirectResponse

router = APIRouter()

MAX_CHARS = 4_000


@router.post("/share")
async def post_share(title: str = Form(""), text: str = Form(""), url: str = Form("")):
    combined = " ".join(part for part in (text.strip(), url.strip()) if part)[:MAX_CHARS]
    return RedirectResponse(f"/check?text={quote(combined)}", status_code=303)
