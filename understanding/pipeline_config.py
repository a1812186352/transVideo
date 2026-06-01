"""Centralized threshold configuration for the analysis pipeline.

Every magic number used across pipeline stages lives here so it can be
tuned in one place.  Import as ``from understanding.pipeline_config import *``
or reference individual constants.
"""

# ── ETA estimation coefficients ──
ETA_BASE_PER_SEC = 0.3           # OpenCV frame diff + scene detect
ETA_WHISPER_PER_SEC = 0.8        # Whisper small, single-thread
ETA_OCR_PER_FRAME = 0.15         # Tesseract per frame
ETA_YOLO_PER_FRAME = 0.08        # YOLOv8n inference
ETA_API_PER_FRAME = 0.3          # External API network latency
ETA_AUDIO_PER_SEC = 0.1          # librosa BPM + energy

# ── Content-based keyframe sampling (second channel) ──
CONTENT_SAMPLE_INTERVAL_SEC = 5.0       # seconds between candidate frames
CONTENT_ENTROPY_THRESHOLD = 4.5         # Shannon entropy (grayscale, 256 bins)
CONTENT_EDGE_DENSITY_MAX = 0.08         # max Canny edge density for "static"

# ── OCR ──
OCR_BATCH_SIZE = 8
OCR_MAX_WORKERS = 4

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

# ── Video type presets (16 types, 7 params each) ──

VIDEO_TYPE_PRESETS = {
    # (opening_pct, closing_pct, energy_mult, cut_mult, ocr_w, audio_w, yolo_w)
    "commercial":      (0.15, 0.20, 1.2, 1.5, 0.8, 0.7, 0.6),   # 品牌露出多
    "gaming":          (0.05, 0.10, 2.0, 3.0, 0.4, 0.8, 0.9),   # 快节奏高能量
    "lecture":         (0.20, 0.10, 0.8, 0.3, 1.3, 1.0, 0.6),   # 低活动OCR重
    "film_tv":         (0.12, 0.18, 1.8, 1.0, 0.7, 0.9, 0.8),   # 标准影视
    "music":           (0.10, 0.25, 1.5, 0.5, 0.5, 1.4, 0.4),   # 音频为主
    "anime":           (0.08, 0.12, 2.5, 2.0, 0.5, 0.8, 0.9),   # 高视觉对比
    "knowledge":       (0.18, 0.12, 0.9, 0.4, 1.2, 0.9, 0.5),   # 科普/教程
    "sports":          (0.08, 0.10, 2.2, 2.5, 0.3, 0.9, 1.0),   # 高能量快切
    "food":            (0.12, 0.15, 1.0, 0.8, 0.7, 0.8, 0.9),   # 美食展示
    "auto":            (0.10, 0.18, 1.4, 1.2, 0.5, 0.8, 0.8),   # 汽车评测
    "short_drama":     (0.08, 0.15, 2.0, 2.0, 0.6, 0.9, 0.8),   # 短剧
    "vlog":            (0.12, 0.12, 1.5, 1.0, 0.6, 0.9, 0.8),   # 通用兜底
    "travel":          (0.12, 0.15, 1.2, 1.0, 0.5, 0.8, 0.7),   # 旅游风光
    "agriculture":     (0.15, 0.12, 0.7, 0.5, 1.0, 0.8, 0.8),   # 农业/慢节奏
    "parenting":       (0.12, 0.12, 1.0, 0.8, 0.9, 1.0, 0.7),   # 亲子教育
    "beauty_fashion":  (0.10, 0.20, 1.2, 1.5, 0.6, 0.7, 0.8),   # 美妆时尚
}

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

# Labels for frontend display
VIDEO_TYPE_LABELS = {
    "commercial": "商业广告", "gaming": "游戏集锦", "lecture": "公开课/讲座",
    "film_tv": "影视剧集", "music": "音乐/MV", "anime": "动画/动漫",
    "knowledge": "知识科普", "sports": "体育赛事", "food": "美食",
    "auto": "汽车", "short_drama": "短剧", "vlog": "Vlog（通用）",
    "travel": "旅游", "agriculture": "农业", "parenting": "亲子",
    "beauty_fashion": "美妆时尚",
}
