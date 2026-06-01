"""Config router: read/write global settings (vision provider, etc.).

Persisted as JSON files under job_store/. Runtime readable by Pipeline.
"""

from fastapi import APIRouter
from typing import Any, Dict

from backend.store import load_vision_config, save_vision_config

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/vision")
async def get_vision_config() -> Dict[str, Any]:
    """Return current vision provider config."""
    return load_vision_config()


@router.post("/vision")
async def set_vision_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Update and persist vision provider config.

    Body fields (all optional, missing = keep current):
      provider: "local" | "api"
      api_url: str (endpoint URL for external vision API)
      api_key: str
      model: str (e.g. "qwen-vl-max", "gpt-4o")
    """
    current = load_vision_config()
    current.update(config)
    saved = save_vision_config(current)
    return saved
