"""Middleware package for transVideo backend.

Provides unified error handling via ``register_error_handlers``.
"""

from backend.middleware.error_handler import (  # noqa: F401
    AppError,
    UploadError,
    UploadTooLargeError,
    UploadInvalidTypeError,
    UploadInterruptedError,
    AnalysisError,
    AnalysisTimeoutError,
    AnalysisUnavailableError,
    RenderError,
    RenderTimeoutError,
    ValidationError,
    NotFoundError,
    ConflictError,
    register_error_handlers,
)
