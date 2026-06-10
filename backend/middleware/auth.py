"""Optional API Key authentication middleware.

Enabled by setting the ``TRANVIDEO_API_KEY`` environment variable.
When set, every API request must include an ``X-API-Key`` header
matching this value.  Requests without a valid key receive a 403
response.

When ``TRANVIDEO_API_KEY`` is not set, the middleware is a no-op
and all requests pass through unauthenticated.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


def _api_key() -> str:
    """Return the configured API key, or empty string if auth is disabled."""
    return os.environ.get("TRANVIDEO_API_KEY", "")


def install_auth_middleware(app: FastAPI) -> None:
    """Register the API Key middleware.

    Only activates when the ``TRANVIDEO_API_KEY`` env var is set.
    Usage::

        from backend.middleware.auth import install_auth_middleware
        install_auth_middleware(app)
    """
    key = _api_key()
    if not key:
        return  # auth disabled — no-op

    class APIKeyMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Allow health/root/metrics without auth
            path = request.url.path
            if path in ("/", "/health", "/metrics", "/docs", "/openapi.json", "/recovery/status"):
                return await call_next(request)

            # Check X-API-Key header
            header_key = request.headers.get("X-API-Key", "")
            if header_key != key:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "code": "FORBIDDEN",
                            "message": "Invalid or missing API key. "
                                       "Provide via X-API-Key header.",
                            "details": {},
                            "recoverable": False,
                        }
                    },
                )

            return await call_next(request)

    app.add_middleware(APIKeyMiddleware)
