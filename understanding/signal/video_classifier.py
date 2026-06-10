"""Video-type classifier — pure heuristic rule-engine, zero model dependencies.

Uses aggregate signal features (face count, optical flow, edge density, BGM type)
to map a video to one of 16 pre-defined types via rule-based scoring.  No CLIP,
no transformers, no network I/O — ~1ms per classification on CPU.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np

_log = logging.getLogger(__name__)

# ── 16 video-type labels ──

_LABEL_PROMPTS = {
    "commercial":      "商业广告，产品展示，品牌宣传，高对比度画面",
    "gaming":          "游戏画面，电子竞技，快速动作，爆炸特效，界面HUD",
    "lecture":         "讲座课堂，PPT演示，教师讲课，黑板板书，屏幕录制",
    "film_tv":         "电影电视剧，演员表演，剧情场景，胶片质感",
    "music":           "音乐MV，演唱会，乐器演奏，舞蹈表演",
    "anime":           "动画动漫，二次元，手绘风格，卡通渲染",
    "knowledge":       "知识科普，科学图解，纪录片风格，讲解旁白",
    "sports":          "体育赛事，运动竞技，球场跑道，比分牌",
    "food":            "美食展示，烹饪过程，菜品特写，餐厅场景",
    "auto":            "汽车评测，驾驶场景，车辆展示，赛道",
    "short_drama":     "短视频短剧，竖屏拍摄，剧情桥段，快节奏",
    "vlog":            "生活Vlog，日常记录，自拍视角，随手拍",
    "travel":          "旅游风光，自然风景，城市地标，航拍",
    "agriculture":     "农业种植，农田作物，农村生活，机械化作业",
    "parenting":       "亲子互动，育儿教育，儿童玩耍，家庭场景",
    "beauty_fashion":  "美妆时尚，化妆教程，穿搭展示，模特走秀",
}

_LABELS = list(_LABEL_PROMPTS.keys())


# ── Main class ─────────────────────────────────────────────────────────

class VideoTypeClassifier:
    """Classify video type using heuristic rules (zero ML dependencies).

    Attributes:
        labels: List of video-type label strings.
        prompts: Per-label description strings (used for BGM keyword matching).
    """

    def __init__(
        self,
        label_set: Optional[List[str]] = None,
    ) -> None:
        self.labels = label_set or _LABELS
        self.prompts = {
            k: v for k, v in _LABEL_PROMPTS.items()
            if k in self.labels
        }

    # ── Public API ────────────────────────────────────────────────

    def classify(
        self,
        signal_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Classify video type from aggregate signal features.

        Args:
            signal_summary: Dict with any of:
                - face_count_avg
                - optical_flow_avg
                - edge_density_avg
                - bgm_type
                - bpm
                - is_dominantly_neutral

        Returns:
            Dict with: video_type, confidence, top3_candidates, method.
        """
        if signal_summary:
            return self._classify_heuristic(signal_summary)

        return {
            "video_type": "vlog",
            "confidence": 0.3,
            "top3_candidates": [{"label": "vlog", "score": 0.3}],
            "method": "heuristic_fallback",
        }

    # ── Heuristic rules ───────────────────────────────────────────

    def _classify_heuristic(self, sig: Dict[str, Any]) -> Dict[str, Any]:
        """Rule-based mapping from signal summary to video type.

        Scores each label on 5 dimensions and returns the highest.
        """
        fc = sig.get("face_count_avg", 0.0)
        flow = sig.get("optical_flow_avg", 0.0)
        ed = sig.get("edge_density_avg", 0.0)
        bgm = sig.get("bgm_type", "")
        bpm = sig.get("bpm", 0)
        neutral = sig.get("is_dominantly_neutral", False)

        scores: Dict[str, float] = {l: 0.0 for l in self.labels}

        # High motion + high edges → gaming / sports / anime
        if flow > 10 and ed > 0.08:
            scores["gaming"] += 0.35
            scores["sports"] += 0.30
            scores["anime"] += 0.25

        # High face count → vlog / lecture / parenting / beauty_fashion
        if fc > 0.5:
            scores["vlog"] += 0.20
            scores["lecture"] += 0.15
            scores["parenting"] += 0.15
            scores["beauty_fashion"] += 0.15

        # Dominantly neutral → commercial / lecture / knowledge (clean frames)
        if neutral:
            scores["commercial"] += 0.25
            scores["lecture"] += 0.20
            scores["knowledge"] += 0.15

        # BGM clues
        bgm_low = bgm or ""
        if "激昂" in bgm_low or "紧张" in bgm_low:
            scores["gaming"] += 0.15
            scores["sports"] += 0.15
            scores["anime"] += 0.10
        elif "明快" in bgm_low or "活泼" in bgm_low:
            scores["vlog"] += 0.15
            scores["travel"] += 0.15
            scores["food"] += 0.10
        elif "舒缓" in bgm_low or "沉静" in bgm_low:
            scores["lecture"] += 0.20
            scores["travel"] += 0.15
            scores["agriculture"] += 0.10
        elif "低沉" in bgm_low or "空灵" in bgm_low:
            scores["music"] += 0.15
            scores["film_tv"] += 0.10

        # BPM
        if bpm > 120:
            scores["gaming"] += 0.10
            scores["sports"] += 0.10
        elif bpm < 70:
            scores["lecture"] += 0.10
            scores["travel"] += 0.10

        # Low motion + low edges → static content types
        if flow < 3 and ed < 0.04:
            scores["lecture"] += 0.15
            scores["knowledge"] += 0.15
            scores["commercial"] += 0.10

        # ── Select best ──
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top3 = [
            {"label": l, "score": round(s, 4)}
            for l, s in ranked[:3]
        ]

        return {
            "video_type": top3[0]["label"],
            "confidence": top3[0]["score"],
            "top3_candidates": top3,
            "method": "heuristic",
        }


# ── Factory ────────────────────────────────────────────────────────────

def create_classifier(
    label_set: Optional[List[str]] = None,
) -> VideoTypeClassifier:
    """Factory: create a heuristic classifier instance.

    Args:
        label_set: Subset of the 16 labels to use (default: all).

    Returns:
        VideoTypeClassifier instance ready for ``classify()``.
    """
    return VideoTypeClassifier(label_set=label_set)
