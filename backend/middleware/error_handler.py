"""FastAPI exception handlers — unified error response format.

Defines application-specific exception classes and registers
handlers that return a consistent JSON envelope::

    {
        "error": {
            "code": "UPLOAD_TOO_LARGE",
            "message": "...",
            "details": {...},
            "recoverable": true
        }
    }

Recoverable errors additionally set ``Retry-After`` and status 503.

Usage in main.py::

    from backend.middleware.error_handler import register_error_handlers
    register_error_handlers(app)
"""

from __future__ import annotations

import traceback
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


# ═══════════════════════════════════════════════════════════════════
#  Custom exception classes
# ═══════════════════════════════════════════════════════════════════

class AppError(Exception):
    """Base application error with recoverable flag."""

    code: str = "INTERNAL_ERROR"
    http_status: int = 500
    recoverable: bool = False
    retry_after: Optional[int] = None  # seconds; if set, emit Retry-After header

    def __init__(
        self,
        message: str = "",
        *,
        details: Optional[Dict[str, Any]] = None,
        recoverable: Optional[bool] = None,
        retry_after: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.message = message or self.__class__.__doc__ or ""
        self.details = details or {}
        if recoverable is not None:
            self.recoverable = recoverable
        if retry_after is not None:
            self.retry_after = retry_after


class UploadError(AppError):
    """File upload failed."""
    code = "UPLOAD_ERROR"
    http_status = 400


class UploadTooLargeError(UploadError):
    """Uploaded file exceeds the size limit."""
    code = "UPLOAD_TOO_LARGE"
    http_status = 413


class UploadInvalidTypeError(UploadError):
    """File type is not a supported video format."""
    code = "UPLOAD_INVALID_TYPE"
    http_status = 400


class UploadInterruptedError(UploadError):
    """Upload was interrupted — partial file cleaned up."""
    code = "UPLOAD_INTERRUPTED"
    http_status = 400


class AnalysisError(AppError):
    """Video analysis pipeline failed."""
    code = "ANALYSIS_ERROR"
    http_status = 500
    recoverable = True   # analysis can be retried with checkpoint resume


class AnalysisTimeoutError(AnalysisError):
    """Analysis timed out."""
    code = "ANALYSIS_TIMEOUT"
    http_status = 503
    retry_after = 30


class AnalysisUnavailableError(AnalysisError):
    """Analysis service temporarily unavailable."""
    code = "ANALYSIS_UNAVAILABLE"
    http_status = 503
    recoverable = True
    retry_after = 60


class RenderError(AppError):
    """Video rendering pipeline failed."""
    code = "RENDER_ERROR"
    http_status = 500
    recoverable = True


class RenderTimeoutError(RenderError):
    """Rendering timed out."""
    code = "RENDER_TIMEOUT"
    http_status = 503
    retry_after = 30


class ValidationError(AppError):
    """Request validation failed."""
    code = "VALIDATION_ERROR"
    http_status = 422
    recoverable = False


class NotFoundError(AppError):
    """Resource not found."""
    code = "NOT_FOUND"
    http_status = 404
    recoverable = False


class ConflictError(AppError):
    """Resource conflict (e.g. job already in progress)."""
    code = "CONFLICT"
    http_status = 409
    recoverable = False


# ═══════════════════════════════════════════════════════════════════
#  Error response builder
# ═══════════════════════════════════════════════════════════════════

def _build_error_response(err: AppError, *, include_traceback: bool = False) -> JSONResponse:
    """Build a unified JSON error response from an AppError."""
    body: Dict[str, Any] = {
        "error": {
            "code": err.code,
            "message": err.message,
            "details": err.details,
            "recoverable": err.recoverable,
        }
    }

    headers: Dict[str, str] = {}

    # Recoverable errors → 503 + Retry-After
    status = err.http_status
    if err.recoverable and status < 500:
        status = 503
    if err.retry_after is not None:
        headers["Retry-After"] = str(err.retry_after)
    elif err.recoverable:
        headers["Retry-After"] = "120"

    if include_traceback:
        body["error"]["traceback"] = traceback.format_exc()

    return JSONResponse(status_code=status, content=body, headers=headers)


# ═══════════════════════════════════════════════════════════════════
#  Exception handlers
# ═══════════════════════════════════════════════════════════════════

async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Handle all AppError subclasses."""
    import logging
    _log = logging.getLogger(__name__)
    _log.warning(
        "AppError code=%s status=%d recoverable=%s: %s",
        exc.code, exc.http_status, exc.recoverable, exc.message,
    )
    return _build_error_response(exc)


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Convert Starlette HTTPException to unified error format."""
    # Map HTTP status to error code
    code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        413: "PAYLOAD_TOO_LARGE",
        422: "VALIDATION_ERROR",
        429: "TOO_MANY_REQUESTS",
        500: "INTERNAL_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }
    code = code_map.get(exc.status_code, "HTTP_ERROR")
    recoverable = exc.status_code in (429, 503, 500)

    headers: Dict[str, str] = {}
    if recoverable:
        headers["Retry-After"] = "120"

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": str(exc.detail),
                "details": {},
                "recoverable": recoverable,
            }
        },
        headers=headers,
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions."""
    import logging
    _log = logging.getLogger(__name__)
    _log.exception("Unhandled exception: %s", exc)

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. The error has been logged.",
                "details": {"type": type(exc).__name__},
                "recoverable": False,
            }
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI app.

    Must be called **after** all routers are mounted so that
    application handlers take precedence over defaults.

    Usage::

        from fastapi import FastAPI
        from backend.middleware.error_handler import register_error_handlers

        app = FastAPI()
        # ... mount routers ...
        register_error_handlers(app)
    """
    # AppError and subclasses
    app.add_exception_handler(AppError, _app_error_handler)
    # Starlette HTTPException (validation errors, 404, etc.)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    # Catch-all for truly unhandled Python exceptions
    app.add_exception_handler(Exception, _unhandled_exception_handler)
