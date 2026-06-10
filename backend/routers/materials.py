"""Materials router: upload / list / delete reference images and clips."""

import os
import uuid
import base64
import aiofiles
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from typing import List, Optional

router = APIRouter(prefix="/materials", tags=["materials"])

MATERIALS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "instances", "materials")
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".webm", ".mov"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


@router.post("/upload")
async def upload_material(file: UploadFile = File(...)) -> dict:
    """Upload a reference image or clip. Returns material_id + thumbnail."""
    if not file.filename:
        raise HTTPException(400, "No file provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported format {ext}, allowed: {', '.join(ALLOWED_EXT)}")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, f"File too large ({len(content)} bytes), max 50MB")

    material_id = uuid.uuid4().hex[:12]
    os.makedirs(MATERIALS_DIR, exist_ok=True)

    save_path = os.path.join(MATERIALS_DIR, f"{material_id}{ext}")
    async with aiofiles.open(save_path, "wb") as f:
        await f.write(content)

    # Generate thumbnail (base64 for images, placeholder for video)
    thumbnail = ""
    if ext in {".jpg", ".jpeg", ".png", ".webp"}:
        import cv2
        img = cv2.imread(save_path)
        if img is not None:
            h, w = img.shape[:2]
            scale = 120 / w
            thumb = cv2.resize(img, (120, int(h * scale)), interpolation=cv2.INTER_AREA)
            _, buf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 60])
            thumbnail = f"data:image/jpeg;base64,{base64.b64encode(buf).decode('utf-8')}"
    elif ext in {".mp4", ".webm", ".mov"}:
        import cv2
        cap = cv2.VideoCapture(save_path)
        ret, frame = cap.read()
        if ret:
            h, w = frame.shape[:2]
            scale = 120 / w
            thumb = cv2.resize(frame, (120, int(h * scale)), interpolation=cv2.INTER_AREA)
            _, buf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 60])
            thumbnail = f"data:image/jpeg;base64,{base64.b64encode(buf).decode('utf-8')}"
        cap.release()

    return {
        "material_id": material_id,
        "filename": file.filename,
        "ext": ext,
        "size_bytes": len(content),
        "thumbnail": thumbnail,
    }


@router.get("/list")
async def list_materials() -> List[dict]:
    """List all uploaded materials with thumbnails."""
    if not os.path.isdir(MATERIALS_DIR):
        return []
    results: List[dict] = []
    for fname in sorted(os.listdir(MATERIALS_DIR), reverse=True):
        path = os.path.join(MATERIALS_DIR, fname)
        if not os.path.isfile(path):
            continue
        material_id, ext = os.path.splitext(fname)
        sz = os.path.getsize(path)
        # Build thumbnail on the fly
        thumbnail = ""
        if ext.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            import cv2
            img = cv2.imread(path)
            if img is not None:
                h, w = img.shape[:2]
                scale = 120 / w
                thumb = cv2.resize(img, (120, int(h * scale)), interpolation=cv2.INTER_AREA)
                _, buf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 60])
                thumbnail = f"data:image/jpeg;base64,{base64.b64encode(buf).decode('utf-8')}"
        elif ext.lower() in {".mp4", ".webm", ".mov"}:
            import cv2
            cap = cv2.VideoCapture(path)
            ret, frame = cap.read()
            if ret:
                h, w = frame.shape[:2]
                scale = 120 / w
                thumb = cv2.resize(frame, (120, int(h * scale)), interpolation=cv2.INTER_AREA)
                _, buf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 60])
                thumbnail = f"data:image/jpeg;base64,{base64.b64encode(buf).decode('utf-8')}"
            cap.release()
        results.append({
            "material_id": material_id,
            "filename": fname,
            "ext": ext,
            "size_bytes": sz,
            "thumbnail": thumbnail,
        })
    return results


@router.delete("/{material_id}")
async def delete_material(material_id: str) -> dict:
    """Delete a material by ID."""
    for fname in os.listdir(MATERIALS_DIR):
        if fname.startswith(material_id):
            os.remove(os.path.join(MATERIALS_DIR, fname))
            return {"deleted": material_id}
    raise HTTPException(404, "Material not found")



