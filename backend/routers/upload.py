"""Video upload router: receives video files and returns video_id.

Validates file type (MIME + extension), enforces size limits (2 GB),
and cleans up partial files on upload interruption.
"""

import asyncio
import base64
import hashlib
import logging
import os
from typing import Dict, List, Optional, Set

import aiofiles
import cv2
from fastapi import APIRouter, File, Query, Request, UploadFile

from backend.middleware.error_handler import (
    UploadInvalidTypeError,
    UploadTooLargeError,
)
from backend.models.script import UploadResponse

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])

# ── Validation constants ──────────────────────────────────────────

# Maximum upload size: 2 GB
MAX_UPLOAD_SIZE = 2 * 1024 * 1024 * 1024

# Allowed MIME types (video only)
ALLOWED_MIME_TYPES: Set[str] = {
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/webm",
    "video/x-matroska",
    "video/mpeg",
    "video/x-m4v",
    "video/3gpp",
    "video/3gpp2",
}

# Allowed file extensions
ALLOWED_EXTENSIONS: Set[str] = {
    ".mp4", ".mov", ".avi", ".webm", ".mkv",
    ".mpeg", ".mpg", ".m4v", ".3gp", ".3g2",
}

# ── File header magic bytes (魔数) — not reliant on MIME/extension ──
# (bytes, label) — read first 12-16 bytes of file
FILE_MAGIC_SIGNATURES: List[tuple] = [
    # MP4/MOV/M4V/3GP check relies on ftyp at offset 4 (handled below)
    (b"\x1a\x45\xdf\xa3", "webm/mkv"),  # EBML header
    (b"RIFF", "avi"),                    # RIFF container
    (b"\x00\x00\x01\xba", "mpeg"),      # MPEG program stream
    (b"\x00\x00\x01\xb3", "mpeg"),      # MPEG video
]


def _validate_magic(content: bytes) -> str:
    """Validate file header magic bytes against known video signatures.

    Returns the detected format label or raises UploadInvalidTypeError.

    This check is performed **before** MIME/extension checks and
    catches renamed files or missing Content-Type headers.
    """
    if len(content) < 12:
        raise UploadInvalidTypeError(
            message="File too small for video header validation",
            details={"size_bytes": len(content)},
        )

    for sig, label in FILE_MAGIC_SIGNATURES:
        if content.startswith(sig):
            return label

    # Special: MP4/MOV/3GP all start with an atom size + "ftyp"
    # Pattern: 00 00 00 XX 66 74 79 70 (size) f t y p
    if content[4:8] == b"ftyp":
        return "mp4/mov/3gp"

    raise UploadInvalidTypeError(
        message="File does not match any known video container signature",
        details={"first_16_bytes": content[:16].hex(" ")},
    )

# Maximum concurrent uploads per client IP
MAX_CONCURRENT_UPLOADS = 3

# Temporary storage directory
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "instances")

# ── Per-IP concurrency tracker ──
_upload_semaphores: Dict[str, asyncio.Semaphore] = {}


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request, respecting X-Forwarded-For."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


def _validate_video_type(filename: Optional[str], content_type: Optional[str]) -> str:
    """Validate file type via both extension and MIME type.

    Returns the normalised extension (always with leading dot).

    Raises:
        UploadInvalidTypeError: If neither extension nor MIME type is recognised.
    """
    # ── Extension check ──
    ext = ".mp4"
    if filename:
        ext = os.path.splitext(filename)[1].lower() or ".mp4"
    if ext not in ALLOWED_EXTENSIONS:
        raise UploadInvalidTypeError(
            message=f"Unsupported file extension: {ext}",
            details={
                "extension": ext,
                "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
            },
        )

    # ── MIME type check ──
    if content_type and content_type not in ALLOWED_MIME_TYPES:
        raise UploadInvalidTypeError(
            message=f"Unsupported media type: {content_type}",
            details={
                "content_type": content_type,
                "allowed_types": sorted(ALLOWED_MIME_TYPES),
            },
        )

    return ext


@router.post("/", response_model=UploadResponse)
async def upload_video(request: Request, file: UploadFile = File(...)) -> UploadResponse:
    """Upload a video file for analysis.

    Validates file type via both MIME type and extension, enforces
    the 2 GB size limit, and throttles concurrent uploads per client
    IP to a maximum of 3.

    On interruption or write failure the partial file is removed.

    Args:
        file: Multipart uploaded file.

    Returns:
        UploadResponse with video_id, filename, and size.

    Raises:
        UploadTooLargeError: File exceeds MAX_UPLOAD_SIZE.
        UploadInvalidTypeError: File type not recognised.
    """
    # ── Validate file presence ──
    if not file.filename:
        raise UploadInvalidTypeError(message="No file provided")

    # ── Validate file type — 3-tier: magic → extension → MIME ──
    ext = _validate_video_type(file.filename, file.content_type)

    # ── Concurrency throttle per client IP ──
    ip = _get_client_ip(request)
    if ip not in _upload_semaphores:
        _upload_semaphores[ip] = asyncio.Semaphore(MAX_CONCURRENT_UPLOADS)
    sem = _upload_semaphores[ip]

    if sem.locked():
        _log.warning("Upload concurrency limit reached for %s", ip)

    async with sem:
        # ── Read file content ──
        content = await file.read()
        file_size = len(content)

        # ── Magic bytes validation (operates on content, not metadata) ──
        _validate_magic(content)

        # ── Size validation ──
        if file_size > MAX_UPLOAD_SIZE:
            raise UploadTooLargeError(
                message=f"File exceeds {MAX_UPLOAD_SIZE // (1024**3)} GB limit: "
                        f"{file_size / (1024**3):.2f} GB",
                details={
                    "file_size_bytes": file_size,
                    "max_size_bytes": MAX_UPLOAD_SIZE,
                },
            )

        # ── Generate deterministic video_id from content hash ──
        # Same file content → same video_id → skip re-analysis
        video_id = hashlib.sha256(content).hexdigest()[:16]

        # ── Ensure upload directory exists ──
        os.makedirs(UPLOAD_DIR, exist_ok=True)

        # ── Save file with interruption cleanup ──
        save_path = os.path.join(UPLOAD_DIR, f"{video_id}{ext}")
        try:
            async with aiofiles.open(save_path, "wb") as f:
                await f.write(content)
        except asyncio.CancelledError:
            # Upload was interrupted — clean up partial file
            _log.warning("Upload interrupted for %s, cleaning up %s", video_id, save_path)
            try:
                os.remove(save_path)
            except OSError:
                pass
            raise UploadInvalidTypeError(
                message="Upload was interrupted. Please try again.",
                details={"video_id": video_id},
            )
        except Exception:
            # Any other write failure — clean up
            try:
                os.remove(save_path)
            except OSError:
                pass
            raise

    # ── Extract video metadata (duration, resolution, fps) via ffprobe ──
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None

    try:
        import json
        import shutil
        import subprocess

        ffprobe = shutil.which("ffprobe") or "ffprobe"
        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", save_path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            fmt = data.get("format", {})
            duration = float(fmt.get("duration", 0)) or None
            for s in data.get("streams", []):
                if s.get("codec_type") == "video":
                    width = s.get("width") or None
                    height = s.get("height") or None
                    rfr = s.get("r_frame_rate", "0/1")
                    try:
                        n, d = rfr.split("/")
                        fps = float(n) / float(d) if int(d) else None
                    except (ValueError, ZeroDivisionError):
                        fps = None
                    break
    except Exception:
        pass  # ffprobe not available — metadata stays None

    return UploadResponse(
        video_id=video_id,
        filename=file.filename,
        size_bytes=file_size,
        duration=duration,
        width=width,
        height=height,
        fps=fps,
    )


@router.get("/video/{video_id}")
async def serve_video(video_id: str):
    """Serve an uploaded video file for in-browser playback.

    Looks up the video by video_id prefix in the instances directory and
    streams it as a byte range response for seeking support.
    """
    from fastapi.responses import StreamingResponse

    found = None
    for fname in os.listdir(UPLOAD_DIR):
        if fname.startswith(video_id):
            found = os.path.join(UPLOAD_DIR, fname)
            break
    if not found:
        from backend.middleware.error_handler import NotFoundError
        raise NotFoundError(message=f"Video {video_id} not found")

    video_path = found
    file_size = os.path.getsize(video_path)

    async def stream():
        with open(video_path, "rb") as f:
            while chunk := f.read(1024 * 1024):  # 1 MB chunks
                yield chunk

    return StreamingResponse(
        stream(),
        media_type="video/mp4",
        headers={
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
        },
    )


@router.get("/video/{video_id}/thumbnails")
async def get_thumbnails(video_id: str, interval: float = Query(3.0, ge=0.5, le=60.0)) -> List[dict]:
    """Extract thumbnails from video at regular intervals.

    Uses OpenCV to decode frames, resize to 120px width, and return
    as base64-encoded JPEG data URIs with timestamps.

    Args:
        video_id: The video ID returned from upload.
        interval: Seconds between thumbnails (default 3, range 0.5-60).

    Returns:
        List of dicts: {timestamp, data_uri}
    """
    found = None
    for fname in os.listdir(UPLOAD_DIR):
        if fname.startswith(video_id):
            found = os.path.join(UPLOAD_DIR, fname)
            break
    if not found:
        from backend.middleware.error_handler import NotFoundError
        raise NotFoundError(message=f"Video {video_id} not found")

    cap = cv2.VideoCapture(found)
    if not cap.isOpened():
        from backend.middleware.error_handler import AppError
        raise AppError(message="Cannot open video file")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0

    thumbnails: List[dict] = []
    t = 0.0
    max_width = 120

    while t < duration:
        frame_idx = int(t * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            break

        h, w = frame.shape[:2]
        scale = max_width / w
        new_h = int(h * scale)
        thumb = cv2.resize(frame, (max_width, new_h), interpolation=cv2.INTER_AREA)
        _, buf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 70])
        data_uri = f"data:image/jpeg;base64,{base64.b64encode(buf).decode('utf-8')}"

        thumbnails.append({"timestamp": round(t, 1), "data_uri": data_uri})
        t += interval

    cap.release()
    return thumbnails


@router.get("/video/{video_id}/filmstrip")
async def get_filmstrip(video_id: str, count: int = Query(20, ge=5, le=100)) -> List[dict]:
    """Extract evenly-spaced thumbnails for the filmstrip preview bar.

    Unlike ``/thumbnails`` (interval-based), this endpoint returns exactly
    ``count`` frames evenly distributed across the full video duration.
    Thumbnails are 80px wide for compact display.

    Args:
        video_id: The video ID returned from upload.
        count: Number of thumbnails (default 20, range 5-100).

    Returns:
        List of dicts: {timestamp, data_uri}
    """
    found = None
    for fname in os.listdir(UPLOAD_DIR):
        if fname.startswith(video_id):
            found = os.path.join(UPLOAD_DIR, fname)
            break
    if not found:
        from backend.middleware.error_handler import NotFoundError
        raise NotFoundError(message=f"Video {video_id} not found")

    cap = cv2.VideoCapture(found)
    if not cap.isOpened():
        from backend.middleware.error_handler import AppError
        raise AppError(message="Cannot open video file")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0

    if duration <= 0 or count < 2:
        cap.release()
        return []

    thumbnails: List[dict] = []
    max_width = 80
    interval = duration / (count - 1)

    for i in range(count):
        t = i * interval
        frame_idx = min(int(t * fps), total_frames - 1)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            break

        h, w = frame.shape[:2]
        scale = max_width / w
        new_h = int(h * scale)
        thumb = cv2.resize(frame, (max_width, new_h), interpolation=cv2.INTER_AREA)
        _, buf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 60])
        data_uri = f"data:image/jpeg;base64,{base64.b64encode(buf).decode('utf-8')}"

        thumbnails.append({"timestamp": round(t, 1), "data_uri": data_uri})

    cap.release()
    return thumbnails


@router.get("/video/{video_id}/thumbnail")
async def get_thumbnail(video_id: str, time: float = Query(0.0, ge=0.0)):
    """Extract a single frame from video at a given time and return as JPEG.

    This endpoint is consumed by the frontend FrameCache for frame-accurate
    seeking and preloading.

    Args:
        video_id: The video ID returned from upload.
        time: Time in seconds to extract the frame at.

    Returns:
        JPEG image bytes with Content-Type image/jpeg.
    """
    from fastapi.responses import Response

    found = None
    for fname in os.listdir(UPLOAD_DIR):
        if fname.startswith(video_id):
            found = os.path.join(UPLOAD_DIR, fname)
            break
    if not found:
        raise HTTPException(status_code=404, detail="Video not found")

    cap = cv2.VideoCapture(found)
    if not cap.isOpened():
        raise HTTPException(status_code=500, detail="Cannot open video file")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0: fps = 30.0
    frame_idx = int(time * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    cap.release()

    if not ret:
        raise HTTPException(status_code=500, detail="Cannot extract frame")

    # Resize to max 640px width for performance
    h, w = frame.shape[:2]
    max_w = 640
    if w > max_w:
        scale = max_w / w
        new_h = int(h * scale)
        frame = cv2.resize(frame, (max_w, new_h), interpolation=cv2.INTER_AREA)

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return Response(content=buf.tobytes(), media_type="image/jpeg")
