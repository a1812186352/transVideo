"""FastAPI application entry point for transVideo backend.

Mounts upload, analysis, and export routers with CORS enabled for
the frontend development server.
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path so that `understanding`, `script`,
# `generation`, and `processing` packages are importable.
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import upload, analysis, export

app = FastAPI(
    title="transVideo API",
    description="Video structure analysis, migratable script, and generation API",
    version="0.1.0",
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(upload.router)
app.include_router(analysis.router)
app.include_router(export.router)


@app.get("/")
async def root() -> dict:
    """Health check endpoint."""
    return {
        "service": "transVideo",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health() -> dict:
    """Detailed health check."""
    return {"status": "healthy"}
