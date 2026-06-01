"""Visual feature extraction with optional YOLO object detection.

Extracts多路 orthogonal features from video keyframes:
  OpenCV (always on):
    - face_count / face_area_ratio (Haar cascade)
    - brightness_mean / brightness_std
    - saturation_mean
    - edge_density (Canny)
    - gray_entropy
    - optical_flow_magnitude (Farneback, pair feature)
    - histogram_distance (Chi-squared HSV, pair feature)
  YOLO (auto-loaded on first frame, falls back gracefully):
    - yolo_objects: [{class_name, confidence, bbox}]
    - yolo_person_count / yolo_vehicle_count / yolo_animal_count
    - yolo_dominant_class
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import cv2
import httpx
import numpy as np

logger = logging.getLogger(__name__)

_FACE_CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"

# ── YOLO class groups ──
_VEHICLE_CLASSES = {
    "car", "truck", "bus", "motorcycle", "bicycle", "train", "boat",
    "aeroplane", "airplane",
}
_ANIMAL_CLASSES = {
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear",
    "zebra", "giraffe",
}
_ELECTRONICS_CLASSES = {
    "tvmonitor", "laptop", "cell phone", "remote", "keyboard", "mouse",
}
_INDOOR_CLASSES = {
    "chair", "couch", "bed", "dining table", "toilet", "refrigerator",
    "oven", "microwave", "sink", "tvmonitor", "laptop", "book", "clock",
    "vase", "potted plant",
}
_OUTDOOR_CLASSES = {
    "car", "truck", "bus", "motorcycle", "bicycle", "traffic light",
    "fire hydrant", "stop sign", "parking meter", "bench", "train",
    "aeroplane", "boat",
}


class VisualFeatureExtractor:
    """Extract多路 visual features from video keyframes.

    OpenCV features run on all frames. YOLO object detection is lazy-loaded
    on first frame and falls back gracefully if unavailable.

    Attributes:
        face_min_size: Min face size (w, h) for Haar detector.
    """

    def __init__(self, face_min_size: Tuple[int, int] = (30, 30)) -> None:
        self.face_min_size = face_min_size
        self._cascade: Optional[cv2.CascadeClassifier] = None
        self._cascade_failed = False

        # YOLO state
        self._yolo_model = None
        self._yolo_device: str = ""
        self._yolo_failed = False

        # Provider config (set by set_provider before analysis)
        self._provider: str = "local"  # "local" | "api"
        self._api_url: str = ""
        self._api_key: str = ""
        self._api_model: str = "qwen-vl-max"

    def set_provider(
        self, provider: str = "local",
        api_url: str = "", api_key: str = "", model: str = "qwen-vl-max",
    ) -> None:
        """Configure which provider to use for frame understanding.

        Args:
            provider: "local" (YOLO + OpenCV) or "api" (external multimodal LLM).
            api_url: Endpoint URL for external vision API.
            api_key: Authentication key.
            model: Model name (e.g. "qwen-vl-max", "gpt-4o").
        """
        self._provider = provider
        self._api_url = api_url
        self._api_key = api_key
        self._api_model = model or "qwen-vl-max"

    def analyze_frames(
        self, frame_paths: List[str]
    ) -> Dict[str, Any]:
        """Run the full degradation chain: API → YOLO → OpenCV-only.

        Returns:
            dict with keys:
              - source: "api" | "yolo" | "opencv"
              - descriptions: List[dict] (per-frame, only for API)
              - features: List[dict] (visual_features format, always)
              - api_time: float or 0
        """
        result: Dict[str, Any] = {
            "source": "opencv",
            "descriptions": [],
            "features": [],
            "api_time": 0.0,
        }

        # Level 1: External API
        if self._provider == "api" and self._api_url:
            try:
                t0 = time.time()
                descriptions, api_features = self._analyze_with_api(frame_paths)
                api_elapsed = time.time() - t0
                if descriptions:
                    result["source"] = "api"
                    result["descriptions"] = descriptions
                    result["features"] = api_features
                    result["api_time"] = round(api_elapsed, 2)
                    return result
            except Exception as exc:
                logger.warning("External vision API failed (%s), falling back to YOLO…", exc)

        # Level 2: YOLO + OpenCV
        try:
            yolo_ok = self._load_yolo() is not None
            if yolo_ok:
                features = self.extract_batch(frame_paths)
                non_zero = sum(1 for f in features if f.get("yolo_total_objects", 0) > 0 or f.get("face_count", 0) > 0)
                if non_zero > 0:
                    result["source"] = "yolo"
                    result["features"] = features
                    return result
        except Exception as exc:
            logger.warning("YOLO inference failed (%s), falling back to OpenCV…", exc)

        # Level 3: OpenCV-only (zero-model)
        try:
            features = self.extract_batch(frame_paths)
            result["source"] = "opencv"
            result["features"] = features
        except Exception as exc:
            logger.warning("OpenCV feature extraction failed: %s", exc)

        return result

    def _analyze_with_api(self, frame_paths: List[str]) -> Tuple[List[dict], List[dict]]:
        """Call external multimodal LLM API for frame descriptions.

        Returns (descriptions, features_with_api_tags).
        """
        descriptions: List[dict] = []
        api_features: List[dict] = []

        batch_size = 5
        for i in range(0, len(frame_paths), batch_size):
            batch = frame_paths[i:i + batch_size]
            batch_desc, batch_feat = self._call_vision_api(batch)
            descriptions.extend(batch_desc)
            api_features.extend(batch_feat)

        return descriptions, api_features

    def _call_vision_api(self, frame_paths: List[str]) -> Tuple[List[dict], List[dict]]:
        """Single batch call to multimodal LLM API.

        Uses OpenAI-compatible chat completions endpoint.
        """
        import os as _os

        # Encode frames as base64 data URIs
        content_parts = [{"type": "text", "text": (
            "Describe this video frame briefly in Chinese: "
            "what is shown, who is present, visible text, camera framing. "
            "Output as JSON: {\"description\":\"…\",\"objects\":[\"…\"],\"scene_type\":\"…\"}"
        )}]

        for path in frame_paths:
            mime = mimetypes.guess_type(path)[0] or "image/jpeg"
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            })

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {
            "model": self._api_model,
            "messages": [{"role": "user", "content": content_parts}],
            "max_tokens": 1024,
        }

        # 5s timeout per batch
        resp = httpx.post(
            self._api_url, json=payload, headers=headers,
            timeout=httpx.Timeout(5.0, connect=3.0),
        )
        resp.raise_for_status()
        data = resp.json()

        desc_text = ""
        try:
            desc_text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            desc_text = str(data)

        # One description per frame
        result_descriptions: List[dict] = []
        result_features: List[dict] = []
        for path in frame_paths:
            fidx = int(_os.path.basename(path).replace("frame_", "").replace(".png", ""))
            result_descriptions.append({
                "frame_path": path,
                "description": desc_text[:200],
                "detected_objects": [],
                "scene_type": "api_analyzed",
            })
            result_features.append({
                "frame_path": path, "frame_index": fidx,
                "face_count": 0, "face_area_ratio": 0.0,
                "brightness_mean": 0.0, "brightness_std": 0.0,
                "saturation_mean": 0.0, "edge_density": 0.0,
                "gray_entropy": 0.0,
                "optical_flow_magnitude": 0.0, "histogram_distance": 0.0,
                "_api_description": desc_text[:120],
            })

        return result_descriptions, result_features

    # ── Public API ──

    def extract_single(self, frame_path: str) -> dict:
        """Extract all single-frame features from one keyframe."""
        img = cv2.imread(frame_path)
        if img is None:
            return _zero_features(frame_path, -1)

        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # Face detection
        fc, far, face_rects = self._detect_faces(gray, w, h)

        # Brightness
        bm = float(gray.mean())
        bs = float(gray.std())

        # Saturation (global mean — kept for backward compatibility)
        sm = float(hsv[:, :, 1].mean())

        # HSV partition-based color analysis (replaces naive global mean)
        color_stats = self._analyze_color_hsv(hsv)

        # Edge density
        edges = cv2.Canny(gray, 50, 150)
        ed = float(np.count_nonzero(edges)) / (w * h)

        # Gray entropy
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
        hist_norm = hist / hist.sum()
        ge = float(-sum(p * np.log2(p + 1e-10) for p in hist_norm.flatten() if p > 0))

        # YOLO object detection
        yolo_result = self._detect_yolo(img)

        # Post-process: false-positive filtering (tiny-bbox, minimal-frame, face corroboration)
        yolo_result = self._validate_yolo(
            yolo_result, h, w, hsv, edges, gray, face_rects,
        )

        # Composition analysis (content-agnostic, based on bbox + edge stats)
        comp_type, comp_conf = self._analyze_composition(
            img, gray, edges, yolo_result["objects"],
        )

        return {
            "frame_path": frame_path, "frame_index": -1,
            "face_count": fc, "face_area_ratio": far,
            "brightness_mean": bm, "brightness_std": bs,
            "saturation_mean": sm, "edge_density": ed,
            "gray_entropy": ge,
            "optical_flow_magnitude": 0.0, "histogram_distance": 0.0,
            "yolo_objects": yolo_result["objects"],
            "yolo_person_count": yolo_result["person_count"],
            "yolo_vehicle_count": yolo_result["vehicle_count"],
            "yolo_animal_count": yolo_result["animal_count"],
            "yolo_dominant_class": yolo_result["dominant_class"],
            "yolo_total_objects": yolo_result["total"],
            "yolo_quality_flag": yolo_result["quality_flag"],
            "composition_type": comp_type,
            "composition_confidence": comp_conf,
            # HSV partition-based color analysis
            "color_zone_pcts": color_stats["zone_pcts"],
            "dominant_color_zone": color_stats["dominant"],
            "is_dominantly_neutral": color_stats["is_neutral"],
            "avg_hue": color_stats["avg_hue"],
        }

    def extract_pair(self, prev_path: str, curr_path: str) -> dict:
        """Extract pair features between two adjacent keyframes."""
        prev = cv2.imread(prev_path, cv2.IMREAD_GRAYSCALE)
        curr = cv2.imread(curr_path, cv2.IMREAD_GRAYSCALE)

        result: dict = {"optical_flow_magnitude": 0.0, "histogram_distance": 0.0}

        if prev is None or curr is None:
            return result

        if prev.shape != curr.shape:
            curr = cv2.resize(curr, (prev.shape[1], prev.shape[0]))

        # Optical flow
        try:
            flow = cv2.calcOpticalFlowFarneback(
                prev, curr, None, 0.5, 3, 15, 3, 5, 1.2, 0
            )
            mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
            result["optical_flow_magnitude"] = float(np.mean(mag))
        except Exception as e:
            logger.debug("Optical flow failed: %s", e)

        # Histogram distance (need color images)
        prev_color = cv2.imread(prev_path)
        curr_color = cv2.imread(curr_path)
        if prev_color is not None and curr_color is not None:
            if prev_color.shape != curr_color.shape:
                curr_color = cv2.resize(curr_color, (prev_color.shape[1], prev_color.shape[0]))
            try:
                h1 = _hsv_histogram(prev_color)
                h2 = _hsv_histogram(curr_color)
                result["histogram_distance"] = float(cv2.compareHist(h1, h2, cv2.HISTCMP_CHISQR))
            except Exception:
                pass

        return result

    def extract_batch(self, frame_paths: List[str]) -> List[dict]:
        """Run extract_single on all frames + extract_pair on adjacent pairs."""
        results: List[dict] = []
        ok_count = 0
        for i, path in enumerate(frame_paths):
            feat = self.extract_single(path)
            feat["frame_index"] = i
            if i > 0:
                pair = self.extract_pair(frame_paths[i - 1], path)
                feat["optical_flow_magnitude"] = pair["optical_flow_magnitude"]
                feat["histogram_distance"] = pair["histogram_distance"]
            if feat.get("brightness_mean", 0) > 1.0:
                ok_count += 1
            results.append(feat)
        total = len(frame_paths)
        if ok_count < total:
            logger.warning("Visual features: %d/%d frames OK%s",
                           ok_count, total,
                           " — all zero, possible image path error" if ok_count == 0 else "")
        return results

    # ── YOLO object detection ──

    def _detect_yolo(self, img: np.ndarray) -> dict:
        """Run YOLO inference on a BGR image. Returns empty dict if YOLO unavailable."""
        model = self._load_yolo()
        if model is None:
            return _empty_yolo_result()

        try:
            results = model(img, verbose=False, conf=0.25, device=self._yolo_device)
        except Exception as e:
            logger.warning("YOLO inference failed: %s", e)
            self._yolo_failed = True
            self._yolo_model = None
            return _empty_yolo_result()

        if not results or len(results) == 0:
            return _empty_yolo_result()

        r = results[0]
        names = model.names if hasattr(model, "names") else {}

        objects: List[dict] = []
        class_counter: Dict[str, int] = {}
        person_count = 0
        vehicle_count = 0
        animal_count = 0

        boxes = r.boxes
        if boxes is not None:
            for box in boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                bbox = box.xyxy[0].tolist()
                class_name = names.get(cls_id, str(cls_id))

                objects.append({
                    "class_name": class_name,
                    "confidence": round(conf, 3),
                    "bbox": [round(v, 1) for v in bbox],
                })
                class_counter[class_name] = class_counter.get(class_name, 0) + 1

                if class_name == "person":
                    person_count += 1
                if class_name in _VEHICLE_CLASSES:
                    vehicle_count += 1
                if class_name in _ANIMAL_CLASSES:
                    animal_count += 1

        dominant_class = ""
        if class_counter:
            dominant_class = max(class_counter, key=class_counter.get)

        return {
            "objects": objects,
            "person_count": person_count,
            "vehicle_count": vehicle_count,
            "animal_count": animal_count,
            "dominant_class": dominant_class,
            "total": len(objects),
            "quality_flag": "reliable",
        }

    # ── YOLO false-positive validation ──

    # Thresholds
    _MIN_BBOX_AREA_RATIO = 0.015       # bbox area < 1.5% of frame
    _LOW_CONFIDENCE = 0.6
    _MINIMAL_EDGE_DENSITY = 0.03      # edge_density below this → "minimal" frame
    _MINIMAL_HSV_VAR = 0.02           # HSV variance below this → uniform background
    _BATCH_FP_COUNT = 5               # ≥5 same-class → potential batch false positive
    _FACE_OVERLAP_MIN = 0.15           # bbox–face IoU ≥ 15% to corroborate "person"

    def _validate_yolo(
        self,
        yolo: dict,
        h: int, w: int,
        hsv: np.ndarray,
        edges: np.ndarray,
        gray: np.ndarray,
        face_rects: List[Tuple[int, int, int, int]],
    ) -> dict:
        """Post-process YOLO results with three false-positive filters.

        Filter 1 — tiny low-confidence discard:
            bbox_area / frame_area < 1.5% AND confidence < 0.6 → remove.

        Filter 2 — minimal-frame batch suppression:
            ≥5 same-class detections AND frame is "minimal" (edge_density
            low + HSV variance low) → mark all objects
            ``likely_false_positive: true``.

        Filter 3 — person face corroboration:
            "person" bboxes that do NOT overlap any Haar face detection
            are marked ``likely_false_positive: true``.

        After all filters, sets ``quality_flag``:
            - "rejected"   — all objects filtered / flagged
            - "suspicious" — at least one likely_false_positive
            - "reliable"   — no issues
        """
        objs = yolo.get("objects", [])
        frame_area = h * w

        # ── Minimal-frame check (runs first — shared across filters) ──
        h_n = hsv[:, :, 0].astype(np.float32) / 179.0
        s_n = hsv[:, :, 1].astype(np.float32) / 255.0
        v_n = hsv[:, :, 2].astype(np.float32) / 255.0
        hsv_var = float(np.var(h_n) + np.var(s_n) + np.var(v_n))
        ed = float(np.count_nonzero(edges)) / frame_area if frame_area > 0 else 0.0
        is_minimal_frame = ed < self._MINIMAL_EDGE_DENSITY and hsv_var < self._MINIMAL_HSV_VAR

        # ── Count same-class for batch detection ──
        class_counts: Dict[str, int] = {}
        for obj in objs:
            class_counts[obj.get("class_name", "")] = class_counts.get(obj.get("class_name", ""), 0) + 1

        # ── IoU helper ──
        def _iou(a: Tuple[int, int, int, int], b: list) -> float:
            """IoU between Haar rect (x,y,w,h) and YOLO bbox [x1,y1,x2,y2]."""
            ax, ay, aw, ah = a
            bx1, by1, bx2, by2 = b[0], b[1], b[2], b[3]
            ix = max(ax, bx1); iy = max(ay, by1)
            ix2 = min(ax + aw, bx2); iy2 = min(ay + ah, by2)
            if ix >= ix2 or iy >= iy2:
                return 0.0
            inter = (ix2 - ix) * (iy2 - iy)
            a_area = aw * ah
            b_area = max((bx2 - bx1) * (by2 - by1), 1)
            return inter / min(a_area, b_area) if min(a_area, b_area) > 0 else 0.0

        filtered: list = []
        any_fp = False

        for obj in objs:
            cls = obj.get("class_name", "")
            conf = obj.get("confidence", 0.0)
            bbox = obj.get("bbox", [0, 0, 0, 0])

            # ── Filter 1: tiny low-confidence → skip ──
            bbox_area = ((bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) if len(bbox) >= 4 else 0
            area_ratio = bbox_area / frame_area if frame_area > 0 else 0.0
            if area_ratio < self._MIN_BBOX_AREA_RATIO and conf < self._LOW_CONFIDENCE:
                continue  # discard

            likely_fp = False

            # ── Filter 2: minimal-frame batch suppression ──
            if is_minimal_frame and class_counts.get(cls, 0) >= self._BATCH_FP_COUNT:
                likely_fp = True

            # ── Filter 3: person face corroboration ──
            if cls == "person" and face_rects:
                has_face = any(
                    _iou(face_rect, bbox) > self._FACE_OVERLAP_MIN
                    for face_rect in face_rects
                )
                if not has_face:
                    likely_fp = True
                    # Reduce confidence weight for unverified person
                    obj["confidence"] = round(conf * 0.5, 3)

            obj["likely_false_positive"] = likely_fp
            if likely_fp:
                any_fp = True
            filtered.append(obj)

        # ── Determine quality flag ──
        if not filtered:
            quality = "rejected"
        elif any_fp:
            quality = "suspicious"
        else:
            quality = "reliable"

        # Re-count after filtering
        person_cnt = sum(1 for o in filtered if o.get("class_name") == "person")
        vehicle_cnt = sum(1 for o in filtered if o.get("class_name") in _VEHICLE_CLASSES)
        animal_cnt = sum(1 for o in filtered if o.get("class_name") in _ANIMAL_CLASSES)
        cls_counts = Counter(o.get("class_name", "") for o in filtered)
        dom = max(cls_counts, key=cls_counts.get) if cls_counts else ""

        return {
            "objects": filtered,
            "person_count": person_cnt,
            "vehicle_count": vehicle_cnt,
            "animal_count": animal_cnt,
            "dominant_class": dom,
            "total": len(filtered),
            "quality_flag": quality,
        }

    def _load_yolo(self):
        """Lazy-load YOLO model. Returns model or None on failure."""
        if self._yolo_failed:
            return None
        if self._yolo_model is not None:
            return self._yolo_model

        try:
            import torch
            from ultralytics import YOLO
        except ImportError:
            logger.warning(
                "ultralytics/torch not installed. YOLO disabled. "
                "Install: pip install ultralytics torch"
            )
            self._yolo_failed = True
            return None

        try:
            self._yolo_device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info("Loading YOLOv8n on %s ...", self._yolo_device)
            self._yolo_model = YOLO("yolov8n.pt")
            logger.info("YOLOv8n loaded on %s", self._yolo_device)
        except Exception as e:
            logger.warning("YOLO load failed: %s. Object detection disabled.", e)
            self._yolo_failed = True
            self._yolo_model = None
        return self._yolo_model

    # ── Internal ──

    def _load_cascade(self) -> Optional[cv2.CascadeClassifier]:
        if self._cascade_failed:
            return None
        if self._cascade is None:
            try:
                self._cascade = cv2.CascadeClassifier(_FACE_CASCADE_PATH)
                if self._cascade.empty():
                    logger.warning("Haar cascade loaded but empty, face detection disabled")
                    self._cascade_failed = True
                    self._cascade = None
            except Exception:
                logger.warning("Failed to load Haar cascade, face detection disabled")
                self._cascade_failed = True
        return self._cascade

    def _detect_faces(self, gray: np.ndarray, w: int, h: int) -> Tuple[int, float, List[Tuple[int, int, int, int]]]:
        cascade = self._load_cascade()
        if cascade is None:
            return 0, 0.0, []
        faces = cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=self.face_min_size
        )
        face_rects = [(int(x), int(y), int(fw), int(fh)) for (x, y, fw, fh) in faces]
        area = sum(fw * fh for _, _, fw, fh in face_rects) / (w * h) if w * h > 0 else 0.0
        return len(faces), area, face_rects

    # ── Composition analysis ──

    def _analyze_composition(
        self,
        img: np.ndarray,
        gray: np.ndarray,
        edges: np.ndarray,
        yolo_objects: List[dict],
    ) -> Tuple[str, float]:
        """Analyze photo composition type based on bbox positions + edge distribution.

        Composition dimensions (content-agnostic, transferable):

          - 三分法构图 (rule_of_thirds)  — subject at 1/3 or 2/3 lines
          - 中心构图 (center)             — subject centered, area 15-40%
          - 对称构图 (symmetry)           — L/R edge density diff < 15%
          - 引导线构图 (leading_line)     — diagonal lines (30°-60°) > 20%
          - 对角线构图 (diagonal)         — objects aligned along image diagonal
          - 框架构图 (frame)             — enclosed edges near 4 borders

        Returns:
            (composition_type, confidence) — confidence in [0, 1].
        """
        h, w = img.shape[:2]
        if h == 0 or w == 0:
            return "unknown", 0.0

        scores = {
            "rule_of_thirds": 0.0,
            "center": 0.0,
            "symmetry": 0.0,
            "leading_line": 0.0,
            "diagonal": 0.0,
            "frame": 0.0,
        }

        # ── Main subject: largest bbox ──
        main_bbox = None
        main_area = 0
        for obj in yolo_objects:
            bbox = obj.get("bbox", [])
            if len(bbox) >= 4:
                area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
                if area > main_area:
                    main_area = area
                    main_bbox = bbox

        frame_area = w * h

        # ── Rule of Thirds ──
        if main_bbox is not None:
            cx = (main_bbox[0] + main_bbox[2]) / 2.0
            cy = (main_bbox[1] + main_bbox[3]) / 2.0
            third_x = w / 3.0
            third_y = h / 3.0
            mx = w * 0.08
            my = h * 0.08

            near_v1 = abs(cx - third_x) < mx
            near_v2 = abs(cx - 2.0 * third_x) < mx
            near_h1 = abs(cy - third_y) < my
            near_h2 = abs(cy - 2.0 * third_y) < my

            if (near_v1 or near_v2) and (near_h1 or near_h2):
                scores["rule_of_thirds"] = 0.90   # intersection point
            elif near_v1 or near_v2 or near_h1 or near_h2:
                scores["rule_of_thirds"] = 0.60   # along one third-line

        # ── Center Composition ──
        if main_bbox is not None:
            cx = (main_bbox[0] + main_bbox[2]) / 2.0
            cy = (main_bbox[1] + main_bbox[3]) / 2.0
            center_dist = np.sqrt((cx - w / 2.0) ** 2 + (cy - h / 2.0) ** 2)
            center_dist /= np.sqrt((w / 2.0) ** 2 + (h / 2.0) ** 2)
            subject_ratio = main_area / frame_area

            if center_dist < 0.10 and 0.15 <= subject_ratio <= 0.40:
                scores["center"] = 0.85
            elif center_dist < 0.15 and 0.10 <= subject_ratio <= 0.50:
                scores["center"] = 0.50

        # ── Symmetry (left / right edge density) ──
        mid = w // 2
        left = edges[:, :mid]
        right = edges[:, mid:]
        left_d = float(np.count_nonzero(left)) / left.size if left.size > 0 else 0.0
        right_d = float(np.count_nonzero(right)) / right.size if right.size > 0 else 0.0
        density_diff = abs(left_d - right_d)

        subject_on_center_axis = True
        if main_bbox is not None:
            cx = (main_bbox[0] + main_bbox[2]) / 2.0
            subject_on_center_axis = (w / 3.0) < cx < (2.0 * w / 3.0)

        if density_diff < 0.15 and subject_on_center_axis:
            scores["symmetry"] = min(1.0 - density_diff * 5.0, 0.95)

        # ── Leading Lines (Hough line angle distribution) ──
        try:
            min_len = max(30, min(w, h) // 10)
            lines = cv2.HoughLinesP(
                edges, 1, np.pi / 180.0,
                threshold=50,
                minLineLength=min_len,
                maxLineGap=10,
            )
            if lines is not None and len(lines) > 5:
                diag_count = 0
                for ln in lines:
                    x1, y1, x2, y2 = ln[0]
                    if x2 != x1:
                        angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
                        if 30 <= angle <= 60 or 120 <= angle <= 150:
                            diag_count += 1
                ratio = diag_count / len(lines)
                if ratio > 0.20:
                    scores["leading_line"] = min(ratio, 0.95)
        except Exception:
            pass

        # ── Diagonal Composition ──
        if len(yolo_objects) >= 2:
            sorted_objs = sorted(
                yolo_objects,
                key=lambda o: (
                    (o["bbox"][2] - o["bbox"][0]) * (o["bbox"][3] - o["bbox"][1])
                    if len(o.get("bbox", [])) >= 4 else 0
                ),
                reverse=True,
            )
            if len(sorted_objs) >= 2:
                b1 = sorted_objs[0]["bbox"]
                b2 = sorted_objs[1]["bbox"]
                ax = (b1[0] + b1[2]) / 2.0
                ay = (b1[1] + b1[3]) / 2.0
                bx = (b2[0] + b2[2]) / 2.0
                by = (b2[1] + b2[3]) / 2.0
                if bx != ax:
                    slope = (by - ay) / (bx - ax)
                    aspect = h / w
                    expected_pos = aspect
                    expected_neg = -aspect
                    if abs(abs(slope) - abs(expected_pos)) < 0.5 or abs(abs(slope) - abs(expected_neg)) < 0.5:
                        scores["diagonal"] = 0.75
        elif main_bbox is not None:
            bbox_w = main_bbox[2] - main_bbox[0]
            bbox_h = main_bbox[3] - main_bbox[1]
            subject_ratio = main_area / frame_area
            if subject_ratio > 0.3:
                bbox_aspect = bbox_h / bbox_w if bbox_w > 0 else 0.0
                img_aspect = h / w
                if abs(bbox_aspect - img_aspect) < 0.5:
                    scores["diagonal"] = 0.50

        # ── Frame Composition ──
        try:
            margin = int(min(w, h) * 0.10)
            top = edges[:margin, :]
            bottom = edges[-margin:, :]
            left_strip = edges[:, :margin]
            right_strip = edges[:, -margin:]

            def _strip_density(strip: np.ndarray) -> float:
                return float(np.count_nonzero(strip)) / strip.size if strip.size > 0 else 0.0

            t_d = _strip_density(top)
            b_d = _strip_density(bottom)
            l_d = _strip_density(left_strip)
            r_d = _strip_density(right_strip)

            border_count = sum(1 for d in [t_d, b_d, l_d, r_d] if d > 0.08)

            if border_count >= 4:
                scores["frame"] = 0.80
            elif border_count >= 3:
                scores["frame"] = 0.50

            # Bonus: subject lies interior to the frame
            if main_bbox is not None and border_count >= 3:
                cx = (main_bbox[0] + main_bbox[2]) / 2.0
                cy = (main_bbox[1] + main_bbox[3]) / 2.0
                inner = int(min(w, h) * 0.15)
                if inner < cx < w - inner and inner < cy < h - inner:
                    scores["frame"] = min(scores["frame"] + 0.15, 0.95)
        except Exception:
            pass

        # ── Select best ──
        best_type: str = "unknown"
        best_score = 0.0
        type_label = {
            "rule_of_thirds": "三分法构图",
            "center": "中心构图",
            "symmetry": "对称构图",
            "leading_line": "引导线构图",
            "diagonal": "对角线构图",
            "frame": "框架构图",
        }

        for key, score in scores.items():
            if score > best_score:
                best_score = score
                best_type = key

        if best_score < 0.30:
            return "unknown", round(best_score, 3)

        return type_label.get(best_type, "unknown"), round(best_score, 3)

    # ── HSV partition-based color analysis ──

    def _analyze_color_hsv(self, hsv: np.ndarray) -> dict:
        """Partition pixels into HSV zones for robust color dominance detection.

        Replaces the naive global HSV mean which gets biased by small warm
        regions on mostly-white backgrounds.

        Zones (mutually exclusive, checked in order):
          1. 白色/浅灰  — S < 0.1  and  V > 0.8
          2. 暗色       — V < 0.2
          3. 暖色       — H in [0°,30°] ∪ [330°,360°]  and  S > 0.15
          4. 冷色       — H in [180°,270°]              and  S > 0.15
          5. 中性       — everything else

        Returns:
            dict with keys:
                zone_pcts:  {zone_label: percentage}  (5 zones, sum ≈ 100)
                dominant:    zone_label with highest percentage
                is_neutral:  True if dominant zone is 白色/浅灰 / 暗色 / 中性
                avg_hue:     global H mean (reference, 0-179 OpenCV range)
        """
        h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
        total = h.size
        shape = h.shape
        if total == 0:
            return {
                "zone_pcts": {"白色/浅灰": 0.0, "暗色": 0.0, "暖色": 0.0, "冷色": 0.0, "中性": 0.0},
                "dominant": "中性",
                "is_neutral": True,
                "avg_hue": 0.0,
            }

        # Normalise to [0, 1] for threshold clarity
        s_norm = s.astype(np.float32) / 255.0
        v_norm = v.astype(np.float32) / 255.0
        # H stays in OpenCV 0-179 (divide by 179 ≈ normalised hue)

        # Exclusive zone mask (neutral = 4 default) — keep 2D shape
        zones = np.full(shape, 4, dtype=np.uint8)

        # 1) 白色/浅灰: S < 0.1  and  V > 0.8
        mask = (s_norm < 0.1) & (v_norm > 0.8)
        zones[mask] = 0

        # 2) 暗色: V < 0.2 (overrides everything except white)
        mask = (v_norm < 0.2) & (zones == 4)
        zones[mask] = 1

        # 3) 暖色: H in [0°,30°] or [330°,360°] in true hue
        #    OpenCV H 0-179 → true_hue = H × 2
        #    so 0-30 true → H 0-15;  330-360 true → H 165-179
        warm_mask = ((h <= 15) | (h >= 165)) & (s_norm > 0.15)
        mask = warm_mask & (zones == 4)
        zones[mask] = 2

        # 4) 冷色: H in [180°,270°] true → H 90-135
        cool_mask = (h >= 90) & (h <= 135) & (s_norm > 0.15)
        mask = cool_mask & (zones == 4)
        zones[mask] = 3

        # 5) 中性: everything still at 4

        # ── Percentages ──
        counts = np.bincount(zones.ravel(), minlength=5).astype(np.float64)
        pcts = (counts / total * 100.0).tolist()
        zone_labels = ["白色/浅灰", "暗色", "暖色", "冷色", "中性"]
        zone_pcts = dict(zip(zone_labels, [round(p, 2) for p in pcts]))

        # ── Dominant ──
        dominant_idx = int(np.argmax(counts))
        dominant = zone_labels[dominant_idx]

        # ── Neutral flag: white / dark / neutral backgrounds ──
        is_neutral = dominant_idx in (0, 1, 4)

        # ── Reference: global H mean ──
        avg_hue = float(np.mean(h))

        return {
            "zone_pcts": zone_pcts,
            "dominant": dominant,
            "is_neutral": is_neutral,
            "avg_hue": avg_hue,
        }


# ── Helpers ──

def _hsv_histogram(img: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hist_h = cv2.calcHist([hsv], [0], None, [50], [0, 180])
    hist_s = cv2.calcHist([hsv], [1], None, [60], [0, 256])
    hist = np.concatenate([hist_h, hist_s])
    cv2.normalize(hist, hist, 0, 1, cv2.NORM_L2)
    return hist


def _empty_yolo_result() -> dict:
    return {
        "objects": [],
        "person_count": 0,
        "vehicle_count": 0,
        "animal_count": 0,
        "dominant_class": "",
        "total": 0,
        "quality_flag": "reliable",
    }


def _zero_features(frame_path: str, index: int) -> dict:
    return {
        "frame_path": frame_path, "frame_index": index,
        "face_count": 0, "face_area_ratio": 0.0,
        "brightness_mean": 0.0, "brightness_std": 0.0,
        "saturation_mean": 0.0, "edge_density": 0.0,
        "gray_entropy": 0.0,
        "optical_flow_magnitude": 0.0, "histogram_distance": 0.0,
        "yolo_objects": [],
        "yolo_person_count": 0,
        "yolo_vehicle_count": 0,
        "yolo_animal_count": 0,
        "yolo_dominant_class": "",
        "yolo_total_objects": 0,
        "yolo_quality_flag": "reliable",
        "composition_type": "unknown",
        "composition_confidence": 0.0,
        "color_zone_pcts": {"白色/浅灰": 0.0, "暗色": 0.0, "暖色": 0.0, "冷色": 0.0, "中性": 0.0},
        "dominant_color_zone": "中性",
        "is_dominantly_neutral": True,
        "avg_hue": 0.0,
    }