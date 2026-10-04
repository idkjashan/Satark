"""The error envelope every non-2xx response uses (CONTRACTS §6).

    {"error": {"code": "...", "message_key": "error.<code>", "retryable": bool}}

Raise `ApiError` anywhere under `satark/api/` or `satark/harness/report.py`; the handlers
registered by `install()` turn it, and FastAPI's own exceptions, into that one shape.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Fallback codes for HTTPExceptions we did not raise ourselves (e.g. Starlette's own
# 404 for an unmatched route, or 405 for a wrong method). ApiError call sites set their
# own precise code instead of going through this table.
_STATUS_CODES: dict[int, str] = {
    400: "bad_request",
    404: "not_found",
    405: "method_not_allowed",
    422: "invalid_request",
    500: "internal_error",
}


class ApiError(Exception):
    """code: the `error.<code>` i18n suffix. status: the HTTP status. headers: e.g. Retry-After."""

    def __init__(self, code: str, status: int, retryable: bool = False, headers: dict[str, str] | None = None) -> None:
        self.code = code
        self.status = status
        self.retryable = retryable
        self.headers = headers
        super().__init__(code)


def _body(code: str, retryable: bool) -> dict[str, Any]:
    return {"error": {"code": code, "message_key": f"error.{code}", "retryable": retryable}}


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.retryable), status_code=exc.status, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(_body("invalid_request", False), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, "error")
        return JSONResponse(
            _body(code, exc.status_code >= 500), status_code=exc.status_code, headers=getattr(exc, "headers", None)
        )
