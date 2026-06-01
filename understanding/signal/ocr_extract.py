"""OCR text extraction using Tesseract for detecting on-screen text regions.

Extracts text from keyframes to identify titles, subtitles, and overlay elements.
"""

import shutil
from typing import List, Optional

# Lazy imports — pytesseract needs tesseract binary on PATH or configured
_pytesseract = None
_Image = None


def _ensure_deps():
    """Lazy-import pytesseract and PIL; configure tesseract path if needed."""
    global _pytesseract, _Image
    if _pytesseract is None:
        import pytesseract as _pt
        from PIL import Image as _Img
        _pytesseract = _pt
        _Image = _Img

        # Auto-detect tesseract binary
        tesseract_bin = shutil.which("tesseract")
        if tesseract_bin:
            _pytesseract.pytesseract.tesseract_cmd = tesseract_bin


class OCRExtractor:
    """Extracts text regions from frames using Tesseract OCR.

    Attributes:
        lang: Language model for OCR (default 'chi_sim+eng' for Chinese + English).
    """

    def __init__(self, lang: str = "chi_sim+eng") -> None:
        self.lang = lang

    def extract(self, frame_paths: List[str]) -> List[dict]:
        """Run OCR on a batch of frame images.

        Args:
            frame_paths: List of absolute paths to frame images.

        Returns:
            List of dicts per frame, each with:
                - frame_path: str
                - text_regions: List of {text, confidence, bbox}
        """
        _ensure_deps()
        results: List[dict] = []
        frames_with_text = 0
        total_regions = 0

        for frame_path in frame_paths:
            regions = self._ocr_frame(frame_path)
            if regions:
                frames_with_text += 1
                total_regions += len(regions)
            results.append({
                "frame_path": frame_path,
                "text_regions": regions,
                "timestamp": 0.0,  # filled by caller if needed
            })

        import logging
        _log = logging.getLogger(__name__)
        if frames_with_text == 0 and frame_paths:
            _log.warning("OCR: 0/%d frames have text — may indicate OCR engine issue or text-free frames",
                         len(frame_paths))
        return results

    def extract_single(self, frame_path: str) -> List[dict]:
        """Run OCR on a single frame image.

        Args:
            frame_path: Absolute path to a frame image.

        Returns:
            List of text region dicts for this frame.
        """
        _ensure_deps()
        return self._ocr_frame(frame_path)

    # ── Text size rank thresholds (bbox height / image height) ──

    _SIZE_LARGE_RATIO = 0.20
    _SIZE_MEDIUM_RATIO = 0.05
    _LOW_CONFIDENCE = 0.4

    def _ocr_frame(self, frame_path: str) -> List[dict]:
        """Run Tesseract on a single image and return structured regions.

        Full-frame OCR (no region cropping).  Results are sorted by
        bounding-box area (largest first) so LOGO / title text takes
        priority over subtitles / edge text.

        Each region includes:
            - text, confidence, bbox (existing)
            - text_size_rank:  "large" | "medium" | "small"
            - low_confidence:  bool  (True when confidence < 0.4)
        """
        try:
            img = _Image.open(frame_path)
        except Exception:
            return []

        img_w, img_h = img.size

        # Use image_to_data for detailed output (word-level bbox + confidence).
        # Default PSM 3 is used — full-page auto); no region cropping applied.
        try:
            data = _pytesseract.image_to_data(
                img, lang=self.lang,
                output_type=_pytesseract.Output.DICT,
            )
        except Exception:
            return []

        regions: List[dict] = []
        n = len(data["text"])

        for i in range(n):
            text = (data["text"][i] or "").strip()
            if not text:
                continue

            conf_str = data["conf"][i]
            try:
                confidence = float(conf_str) / 100.0 if conf_str != "-1" else 0.6
            except (ValueError, TypeError):
                confidence = 0.6

            x = int(data["left"][i])
            y = int(data["top"][i])
            w = int(data["width"][i])
            h = int(data["height"][i])

            # Size rank
            height_ratio = h / img_h if img_h > 0 else 0.0
            if height_ratio >= self._SIZE_LARGE_RATIO:
                size_rank = "large"
            elif height_ratio >= self._SIZE_MEDIUM_RATIO:
                size_rank = "medium"
            else:
                size_rank = "small"

            regions.append({
                "text": text,
                "confidence": confidence,
                "bbox": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]],
                "text_size_rank": size_rank,
                "low_confidence": confidence < self._LOW_CONFIDENCE,
            })

        # Sort by bounding-box area descending — large LOGO text first
        regions.sort(key=lambda r: (r["bbox"][2][0] - r["bbox"][0][0]) * (r["bbox"][2][1] - r["bbox"][0][1]), reverse=True)

        return regions
