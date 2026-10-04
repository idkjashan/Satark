"""Shared request-time helpers.

Also the one place that reaches into `satark.harness.orchestrator` (owned by D, built in
parallel — CONTRACTS §1, §5). Importing it defensively means this whole package works
today against a fake runtime (`tests/api/fakes.py`) and transparently picks up the real
module the moment D lands it: no code change needed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Request

from satark.api.errors import ApiError

try:
    import satark.harness.orchestrator as _orch
except ImportError:  # pragma: no cover - D's module lands independently (CONTRACTS §1)
    _orch = None


class _NeverRaised(Exception):
    """Stands in for an Orchestrator exception D has not added yet; nothing ever raises it."""


if _orch is not None and hasattr(_orch, "CheckInput"):
    CheckInput = _orch.CheckInput
else:

    @dataclass
    class CheckInput:  # shadow of CONTRACTS §5 until satark.harness.orchestrator exists
        text: str | None = None
        image: bytes | None = None
        image_mime: str | None = None
        qr: str | None = None
        lang: str = "en"
        simple: bool = False
        client: str | None = None


# Exceptions we must be able to `except`, even before D adds them.
CaseExpired: type[Exception] = getattr(_orch, "CaseExpired", None) or type("CaseExpired", (Exception,), {})
Busy: type[Exception] = getattr(_orch, "Busy", None) or _NeverRaised


def get_rt(request: Request) -> Any:
    """The Runtime built at startup (`satark.harness.runtime.Runtime`), or a test fake."""
    return request.app.state.rt


def require_ready(rt: Any) -> None:
    if not rt.ready:
        raise ApiError("not_ready", 503, retryable=True)
