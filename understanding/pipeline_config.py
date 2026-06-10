"""Centralized threshold configuration for the analysis pipeline.

Every magic number used across pipeline stages lives here so it can be
tuned in one place.  Import as ``from understanding.pipeline_config import *``
or reference individual constants.
"""

import os

# ── ETA estimation coefficients ──
ETA_BASE_PER_SEC = 0.3           # OpenCV frame diff + scene detect
ETA_WHISPER_PER_SEC = 0.8        # Whisper small, single-thread
ETA_OCR_PER_FRAME = 0.15         # Tesseract per frame
ETA_YOLO_PER_FRAME = 0.08        # YOLOv8n inference
ETA_API_PER_FRAME = 0.3          # External API network latency
ETA_AUDIO_PER_SEC = 0.1          # librosa BPM + energy

# ── Stage timeout guards (seconds) — prevent ThreadPoolExecutor deadlocks ──
STAGE1_TASK_TIMEOUT = 600        # max per sub-task (diff / scene / audio / vad)
STAGE2_TRANSCRIBE_TIMEOUT = 1200 # Whisper transcription (can be slow)
STAGE3_OCR_TIMEOUT = 600         # OCR on keyframes

# Soft timeout for frame_diff (cv2.VideoCapture can hang on corrupt files)
FRAME_DIFF_SOFT_TIMEOUT = 300    # 5 min
# Soft timeout for scene_detect (PySceneDetect also uses OpenCV)
SCENE_DETECT_SOFT_TIMEOUT = 300  # 5 min

# ── Global timeout for the entire analyze_video() pipeline ──
# Protects against aggregate hangs that per-stage timeouts miss.
# When exceeded, partial results are saved and the job is marked "partial".
ANALYZE_VIDEO_GLOBAL_TIMEOUT = 3600  # 60 min total

# ── Content-based keyframe sampling (second channel) ──
CONTENT_SAMPLE_INTERVAL_SEC = 5.0       # seconds between candidate frames
CONTENT_ENTROPY_THRESHOLD = 4.5         # Shannon entropy (grayscale, 256 bins)
CONTENT_EDGE_DENSITY_MAX = 0.08         # max Canny edge density for "static"

# ── OCR ──
OCR_BATCH_SIZE = 8
OCR_MAX_WORKERS = 4
OCR_FRAME_BLUR_THRESHOLD = 100   # Laplacian variance — frames below this are blurry/empty
OCR_MAX_RETRIES = 3               # retry count per frame on crash

# ── BPM thresholds ──
BPM_HIGH = 120
BPM_MEDIUM = 80
BPM_LOW = 50

# ── BPM estimation from diff_curve (fallback) ──
BPM_FALLBACK_BASE = 80
BPM_FALLBACK_SCALE = 100
DIFF_ACTIVITY_THRESHOLD = 0.1

# ── Energy / emotion thresholds ──
ENERGY_VARIANCE_HIGH = 0.01      # variance above this → "高对比度"
ENERGY_AVG_WARM = 0.05           # mean above this → "暖色调"
EMOTION_PEAK_HIGH = 0.8
EMOTION_PEAK_MEDIUM = 0.5
ENERGY_CURVE_BINS = 20

# ── Brightness / saturation thresholds ──
BRIGHTNESS_DARK = 25
BRIGHTNESS_BRIGHT = 180
SATURATION_HIGH = 100

# ── Face / composition heuristics ──
FACE_CLOSEUP_RATIO = 0.08
FACE_GROUP_RATIO = 0.04
OBJECT_COMPLEX_COUNT = 5
OBJECT_SIMPLE_COUNT = 3
EDGE_COMPLEX = 0.15
EDGE_SIMPLE = 0.08

# ── Motion / optical-flow thresholds ──
FL_STILL = 3
FL_SLIGHT = 8
FL_PUSH = 15
FL_FAST = 25
HD_STILL = 0.2
HD_FAST = 0.3
HD_VIOLENT = 0.5

# ── Spatial position thresholds (normalised 0-1) ──
POS_LEFT = 0.33
POS_RIGHT = 0.66

# ── Watermark detection ──
WATERMARK_SEG_RATIO = 0.4        # text in >= 40% of segments → watermark
WATERMARK_MIN_SEGS = 2

# ── Scene tag fallbacks ──
SCENE_TAG_MAP = {
    "opening": ["引入", "铺垫", "建置"],
    "highlight": ["战斗爆发", "对决", "名场面"],
    "transition": ["场景切换", "时间跳转"],
    "effect": ["慢动作", "粒子", "变速"],
    "closing": ["情感回落", "告别", "谢幕"],
}

# ── High-freq-word fallbacks (when no ASR or OCR) ──
FALLBACK_HIGH_FREQ = {
    "opening": ["#片头"],
    "highlight": ["#高光"],
    "transition": ["#转场"],
    "effect": ["#特效"],
    "closing": ["#片尾"],
}

# ── Sentiment keywords ──
POSITIVE_KW = ["燃", "炸", "绝了", "高能", "神", "帅", "厉害", "精彩", "期待"]
NEGATIVE_KW = ["完结", "再见", "结束"]

# ── Color palette reference (segment-type agnostic) ──
PALETTE_WARM = ["#ff6b35", "#f7c948", "#e8a87c"]
PALETTE_COOL = ["#264653", "#2a9d8f", "#457b9d"]
PALETTE_HIGH_CONTRAST = ["#e63946", "#f1faee", "#1d3557"]
PALETTE_NEUTRAL = ["#6c757d", "#adb5bd", "#ced4da"]

# ── Video type presets (loaded from config/presets.json, fallback to embedded) ──
# Fields: (opening_pct, closing_pct, energy_mult, cut_mult,
#          ocr_w, audio_w, yolo_w, portrait_weight, motion_tolerance)

_EMBEDDED_PRESETS = {
    "commercial":      (0.15, 0.20, 1.2, 1.5, 0.8, 0.7, 0.6, 0.4, 0.7),
    "gaming":          (0.05, 0.10, 2.0, 3.0, 0.4, 0.8, 0.9, 0.4, 3.0),
    "lecture":         (0.20, 0.10, 0.8, 0.3, 1.3, 1.0, 0.6, 0.9, 0.3),
    "film_tv":         (0.12, 0.18, 1.8, 1.0, 0.7, 0.9, 0.8, 0.8, 1.0),
    "music":           (0.10, 0.25, 1.5, 0.5, 0.5, 1.4, 0.4, 0.3, 0.5),
    "anime":           (0.08, 0.12, 2.5, 2.0, 0.5, 0.8, 0.9, 0.5, 2.5),
    "knowledge":       (0.18, 0.12, 0.9, 0.4, 1.2, 0.9, 0.5, 0.6, 0.4),
    "sports":          (0.08, 0.10, 2.2, 2.5, 0.3, 0.9, 1.0, 0.5, 3.0),
    "food":            (0.12, 0.15, 1.0, 0.8, 0.7, 0.8, 0.9, 0.5, 0.8),
    "auto":            (0.10, 0.18, 1.4, 1.2, 0.5, 0.8, 0.8, 0.4, 1.2),
    "short_drama":     (0.08, 0.15, 2.0, 2.0, 0.6, 0.9, 0.8, 0.8, 1.5),
    "vlog":            (0.12, 0.12, 1.5, 1.0, 0.6, 0.9, 0.8, 0.7, 1.0),
    "travel":          (0.12, 0.15, 1.2, 1.0, 0.5, 0.8, 0.7, 0.3, 0.8),
    "agriculture":     (0.15, 0.12, 0.7, 0.5, 1.0, 0.8, 0.8, 0.4, 0.6),
    "parenting":       (0.12, 0.12, 1.0, 0.8, 0.9, 1.0, 0.7, 0.9, 0.7),
    "beauty_fashion":  (0.10, 0.20, 1.2, 1.5, 0.6, 0.7, 0.8, 0.9, 0.8),
}

_EMBEDDED_LABELS = {
    "commercial": "商业广告", "gaming": "游戏集锦", "lecture": "公开课/讲座",
    "film_tv": "影视剧集", "music": "音乐/MV", "anime": "动画/动漫",
    "knowledge": "知识科普", "sports": "体育赛事", "food": "美食",
    "auto": "汽车", "short_drama": "短剧", "vlog": "Vlog（通用）",
    "travel": "旅游", "agriculture": "农业", "parenting": "亲子",
    "beauty_fashion": "美妆时尚",
}


def _load_json_presets():
    """Try to load presets from ``config/presets.json``, falling back to
    the embedded dict if the file is missing or corrupt.

    Users can copy ``config/presets.json``, edit it, and restart — any
    changes to presets, labels, or heuristic rules take effect without
    touching Python code.
    """
    import json
    import os

    path = os.path.join(os.path.dirname(__file__), "..", "config", "presets.json")
    path = os.path.normpath(path)
    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except (json.JSONDecodeError, OSError):
        return None


_JSON_DATA = _load_json_presets()
if _JSON_DATA:
    VIDEO_TYPE_PRESETS = {k: tuple(v) for k, v in _JSON_DATA.get("presets", {}).items()}
    VIDEO_TYPE_LABELS = _JSON_DATA.get("labels", _EMBEDDED_LABELS)
    HEURISTIC_RULES = _JSON_DATA.get("heuristic_rules", {})
else:
    VIDEO_TYPE_PRESETS = _EMBEDDED_PRESETS
    VIDEO_TYPE_LABELS = _EMBEDDED_LABELS
    HEURISTIC_RULES = {}

# ── Sub-type label maps (19 sub-types) ──

SUB_TYPE_OPENING = {
    "brand_intro":       "品牌开场",
    "title_card":        "标题卡",
    "character_intro":   "人物引入",
    "environment_setup": "环境铺垫",
    "suspense_open":     "悬念开场",
}

SUB_TYPE_HIGHLIGHT = {
    "action_pinnacle":   "动作高燃",
    "dialogue_golden":   "台词金句",
    "emotion_peak":      "情绪峰值",
    "visual_explosion":  "视觉爆发",
}

SUB_TYPE_TRANSITION = {
    "hard_cut":          "硬切",
    "fade_in_out":       "淡入淡出",
    "slide_wipe":        "滑动转场",
    "match_cut":         "匹配剪辑",
}

SUB_TYPE_CLOSING = {
    "brand_reveal":      "品牌露出",
    "black_fade":        "黑场淡出",
    "credit_scroll":     "字幕滚动",
    "freeze_frame":      "画面定格",
    "music_fade":        "音乐淡出",
    "sync_fade":         "同步淡出",
}

SUB_TYPE_EFFECT = {
    "visual_fx":         "视觉特效",
    "speed_ramp":        "变速节奏",
    "flash_frame":       "闪切插入",
    "slow_motion":       "慢动作",
}

# ── Module types (6 types, content = unclassified-but-visible segment) ──

MODULE_TYPE_CONTENT = "content"
MODULE_TYPES = ["title", "video_segment", "transition", "effect", "content"]

# ── Video Type Classifier (heuristic rule-engine, zero ML deps) ──
VIDEO_TYPE_FRAME_SAMPLE_COUNT = 8
VIDEO_TYPE_CONFIDENCE_THRESHOLD = 0.4  # below this → fallback "vlog"
VIDEO_TYPE_BLEND_ALPHA = 0.6           # typed_weight × α + generic × (1-α)

# ── Motion analysis thresholds ──
ZOOM_IN_SCALE = 1.08            # scale_factor > this → ZOOM_IN
ZOOM_OUT_SCALE = 0.92           # scale_factor < this → ZOOM_OUT
PAN_DISPLACEMENT = 0.05         # normalized |dx| or |dy| > this → PAN
FADE_BRIGHTNESS_DELTA = 0.15    # |brightness_delta| > this → FADE
ROTATION_DEGREE = 3.0           # |rotation_angle| > this → ROTATE
MOTION_NOISE_FLOOR = 0.005      # max(|dx|,|dy|,|scale-1|) < this → STATIC

# ── Composition grid thresholds ──

# Grid layout
GRID_COLS = 3                         # number of columns
GRID_ROWS = 3                         # number of rows
GRID_COL_BOUNDARY = 0.33              # left/middle boundary (normalised)
GRID_ROW_BOUNDARY = 0.67              # middle/right boundary (normalised)
# (col < 0.33 → left, col > 0.67 → right, else center)
# (row < 0.33 → top,  row > 0.67 → bottom, else middle)

# Center zone definition (normalised coords)
CENTER_ZONE = (0.33, 0.33, 0.67, 0.67)  # (x1, y1, x2, y2) in normalised units

# Center symmetry thresholds
CENTER_SYMMETRY_CENTERED = 0.6        # center_ratio > this → "居中"
CENTER_SYMMETRY_SHIFTED = 0.2         # center_ratio < this → "边缘"
CENTER_SYMMETRY_IMBALANCE = 0.55      # L/R or T/B > this fraction → "偏移"

# Diagonal band
DIAGONAL_BAND_WIDTH = 0.12            # |cx - cy| < this → on main diagonal
DIAGONAL_HIT_THRESHOLD = 0.20         # fraction on diagonal ≥ this → presence

# Subject coverage tiers
SUBJECT_COVERAGE_SPARSE = 0.05        # < this → "点缀"
SUBJECT_COVERAGE_FULL = 0.25          # > this → "饱满", between → "适中"

# Subject weighting
PERSON_WEIGHT_MULTIPLIER = 1.5        # person class area × multiplier

# ── Module-level creative labels (11 tags) ──

# Content labels: sub_type → creative tag
CONTENT_LABEL_MAP = {
    "brand_intro":       "品牌开场",
    "character_entry":   "人物引入",
    "product_demo":      "动作高燃",
    "voice_core":        "台词金句",
    "multi_angle":       "视觉爆发",
    "emotion_climax":    "情绪峰值",
    "scene_setting":     "环境铺垫",
    "dialogue_normal":   "台词推进",
    # Also accept already-Chinese sub_types from _derive_sub_type
    "品牌开场":            "品牌开场",
    "人物引入":            "人物引入",
    "动作高燃":            "动作高燃",
    "台词金句":            "台词金句",
    "视觉爆发":            "视觉爆发",
    "情绪峰值":            "情绪峰值",
    "标题卡":              "标题卡",
    "品牌露出":            "品牌露出",
    "硬切":                "硬切",
    "匹配剪辑":            "匹配剪辑",
    "视觉特效":            "视觉特效",
    "同步淡出":            "同步淡出",
}

# Scene-tag fallback: scene_tags[0] → creative tag
SCENE_TAG_MAP = {
    "人物出镜":  "人物引入",
    "产品展示":  "动作高燃",
    "口播台词":  "台词金句",
    "好评展示":  "情绪峰值",
    "效果对比":  "情绪峰值",
    "多角度":    "视觉爆发",
}

# Motion-based rules: (predicate, label) in priority order
MOTION_LABEL_RULES = [
    (lambda m: "硬切" in m,      "硬切"),
    (lambda m: "匹配剪辑" in m,  "匹配剪辑"),
    (lambda m: "效果" in m or "特效" in m or "包装" in m, "视觉特效"),
    (lambda m: "淡出" in m or "淡入" in m, "同步淡出"),
]
