"""Video upload router: receives video files and returns video_id."""

import base64
import os
import uuid
import cv2
import aiofiles
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from typing import List

from backend.models.script import UploadResponse

router = APIRouter(prefix="/upload", tags=["upload"])

# Maximum upload size: 2 GB
MAX_UPLOAD_SIZE = 2 * 1024 * 1024 * 1024

# Temporary storage directory
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "instances")


@router.post("/", response_model=UploadResponse)
async def upload_video(file: UploadFile = File(...)) -> UploadResponse:
    """Upload a video file for analysis.

    The file is saved to the instances directory with a UUID-based
    filename to prevent collisions. The original filename and size
    are recorded in the response.

    Args:
        file: Multipart uploaded file (video/mp4, video/quicktime, etc.).

    Returns:
        UploadResponse with video_id, filename, and size.

    Raises:
        HTTPException 413: If file exceeds MAX_UPLOAD_SIZE.
        HTTPException 400: If file is not a recognized video format.
    """
    # Validate file presence
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # Read file content
    content = await file.read()
    file_size = len(content)

    # Check size
    if file_size > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {file_size} bytes (max {MAX_UPLOAD_SIZE})",
        )

    # Generate unique video_id
    video_id = uuid.uuid4().hex[:16]

    # Determine extension
    ext = os.path.splitext(file.filename)[1] or ".mp4"

    # Ensure upload directory exists
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # Save file
    save_path = os.path.join(UPLOAD_DIR, f"{video_id}{ext}")
    async with aiofiles.open(save_path, "wb") as f:
        await f.write(content)

    # Extract video metadata (duration, resolution, fps) via ffprobe
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None

    try:
        import subprocess, json, shutil
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
        raise HTTPException(status_code=404, detail="Video not found")

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
        raise HTTPException(status_code=404, detail="Video not found")

    cap = cv2.VideoCapture(found)
    if not cap.isOpened():
        raise HTTPException(status_code=500, detail="Cannot open video file")

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
