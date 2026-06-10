"""Pydantic models for MigratableScript used in backend API layer.

Mirrors the script/schema.py JSON Schema but as typed Python models for
FastAPI request/response validation.
"""

from typing import List, Optional, Literal, Any, Dict
from datetime import datetime
from pydantic import BaseModel, Field


class SourceMaterial(BaseModel):
    """Reference to a source asset file."""

    type: Literal["video", "image", "text", "audio", "effect"] = "video"
    path: str = ""
    start_offset: float = 0.0
    end_offset: float = 0.0


class ModuleParams(BaseModel):
    """Renderer-agnostic module parameters."""

    text_content: Optional[str] = None
    font_size: Optional[int] = None
    font_color: Optional[str] = None
    position: Optional[Dict[str, float]] = None
    animation: Optional[str] = None
    volume: Optional[float] = Field(None, ge=0.0, le=1.0)
    transition_type: Optional[str] = None


class Module(BaseModel):
    """A single module on the timeline."""

    id: str
    type: Literal[
        "title", "video_segment", "subtitle", "transition", "audio", "effect"
    ]
    label: Optional[str] = None
    start_time: float = Field(ge=0.0)
    duration: float = Field(ge=0.0)
    track_index: int = Field(ge=0)
    source: Optional[SourceMaterial] = None
    params: Optional[ModuleParams] = None
    extra_params: Optional[Dict[str, Any]] = None
    children: List["Module"] = []
    detail: Optional[Dict[str, Any]] = None
    contained_transcript: Optional[List[str]] = None
    contained_ocr: Optional[List[str]] = None


class Track(BaseModel):
    """A timeline track definition."""

    index: int = Field(ge=0)
    name: str
    type: Literal["video", "audio", "text", "effect"]
    muted: bool = False
    locked: bool = False


class Resolution(BaseModel):
    """Video resolution dimensions."""

    width: int = Field(ge=1, default=1920)
    height: int = Field(ge=1, default=1080)


class Metadata(BaseModel):
    """Project metadata."""

    title: str = "Untitled Project"
    description: str = ""
    author: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    total_duration: float = Field(ge=0.0, default=0.0)
    source_video_id: str = ""
    fps: float = Field(ge=1.0, default=30.0)
    resolution: Resolution = Resolution()
    tags: List[str] = []


class MigratableScript(BaseModel):
    """Complete MigratableScript model for API request/response."""

    version: str = "1.0.0"
    metadata: Metadata = Metadata()
    modules: List[Module] = []
    tracks: List[Track] = []


# Response models
class UploadResponse(BaseModel):
    """Response from video upload endpoint."""

    video_id: str
    filename: str
    size_bytes: int
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None


class AnalysisResponse(BaseModel):
    """Response from analysis endpoint."""

    video_id: str
    status: Literal["processing", "completed", "failed", "partial"] = "processing"
    script: Optional[MigratableScript] = None
    creative_pattern: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ExportResponse(BaseModel):
    """Response from export endpoint."""

    video_id: str
    status: Literal["queued", "processing", "completed", "failed"] = "queued"
    output_path: Optional[str] = None
    error: Optional[str] = None
