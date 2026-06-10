"""Blueprint templates — preset module sequences per video type.

Each template defines the mandatory module sequence, recommended
duration ratios, and ordering constraints for a video genre.
"""

from typing import Dict, List, Any

# ═══════════════════════════════════════════════════════
#  Template presets
# ═══════════════════════════════════════════════════════

TEMPLATE_PRESETS: Dict[str, Dict[str, Any]] = {
    "product_review": {
        "label": "产品测评",
        "description": "结构化产品评测：开箱 → 展示 → 对比 → CTA",
        "modules": [
            {"name": "片头引语",   "key": "opening_intro",    "min_pct": 0.05, "max_pct": 0.10, "default_dur": 3.0},
            {"name": "开箱展示",   "key": "unboxing",         "min_pct": 0.12, "max_pct": 0.20, "default_dur": 5.0},
            {"name": "产品特写",   "key": "product_closeup",  "min_pct": 0.15, "max_pct": 0.25, "default_dur": 6.0, "required": True},
            {"name": "使用场景",   "key": "usage_scene",      "min_pct": 0.15, "max_pct": 0.25, "default_dur": 6.0},
            {"name": "效果对比",   "key": "comparison",       "min_pct": 0.10, "max_pct": 0.18, "default_dur": 4.0, "required": True},
            {"name": "优缺点总结", "key": "pros_cons",        "min_pct": 0.08, "max_pct": 0.15, "default_dur": 4.0},
            {"name": "CTA",        "key": "cta",              "min_pct": 0.05, "max_pct": 0.10, "default_dur": 3.0},
        ],
        "total_min_dur": 30.0,
        "total_max_dur": 180.0,
    },

    "shopping_live": {
        "label": "带货",
        "description": "直播带货/种草视频：痛点 → 展示 → 卖点 → 福利 → CTA",
        "modules": [
            {"name": "痛点引入",   "key": "pain_point",       "min_pct": 0.08, "max_pct": 0.15, "default_dur": 3.0},
            {"name": "商品特写",   "key": "product_closeup",  "min_pct": 0.15, "max_pct": 0.25, "default_dur": 6.0, "required": True},
            {"name": "卖点口播",   "key": "selling_points",   "min_pct": 0.20, "max_pct": 0.35, "default_dur": 8.0, "required": True},
            {"name": "使用演示",   "key": "demo",             "min_pct": 0.15, "max_pct": 0.25, "default_dur": 6.0},
            {"name": "价格锚点",   "key": "price_anchor",     "min_pct": 0.05, "max_pct": 0.10, "default_dur": 2.0},
            {"name": "限时福利",   "key": "urgency",          "min_pct": 0.05, "max_pct": 0.10, "default_dur": 2.0},
            {"name": "CTA",        "key": "cta",              "min_pct": 0.05, "max_pct": 0.10, "default_dur": 3.0},
        ],
        "constraints": {"product_closeup_plus_selling_points_min_pct": 0.40},
        "total_min_dur": 25.0,
        "total_max_dur": 120.0,
    },

    "talking_head": {
        "label": "口播",
        "description": "知识分享/口播：引入 → 解说 → 观点 → 案例 → 金句 → CTA",
        "modules": [
            {"name": "话题引入",   "key": "topic_intro",      "min_pct": 0.05, "max_pct": 0.10, "default_dur": 3.0},
            {"name": "长时解说",   "key": "long_speech",      "min_pct": 0.40, "max_pct": 0.60, "default_dur": 15.0, "required": True, "unsplittable": True},
            {"name": "观点展开",   "key": "viewpoint",        "min_pct": 0.10, "max_pct": 0.20, "default_dur": 5.0},
            {"name": "案例佐证",   "key": "case_study",       "min_pct": 0.10, "max_pct": 0.20, "default_dur": 5.0},
            {"name": "金句收尾",   "key": "quote_ending",     "min_pct": 0.05, "max_pct": 0.10, "default_dur": 3.0},
            {"name": "CTA",        "key": "cta",              "min_pct": 0.05, "max_pct": 0.10, "default_dur": 3.0},
        ],
        "total_min_dur": 30.0,
        "total_max_dur": 300.0,
    },

    "mashup": {
        "label": "混剪",
        "description": "快节奏混剪：引爆 → 冲击A → 过渡 → 冲击B → 堆叠 → 爆发 → CTA",
        "modules": [
            {"name": "节奏引爆",   "key": "rhythm_opener",    "min_pct": 0.05, "max_pct": 0.08, "default_dur": 2.0},
            {"name": "画面冲击 A", "key": "impact_a",         "min_pct": 0.10, "max_pct": 0.20, "default_dur": 4.0, "required": True},
            {"name": "内容过渡",   "key": "bridge",           "min_pct": 0.05, "max_pct": 0.10, "default_dur": 2.0},
            {"name": "画面冲击 B", "key": "impact_b",         "min_pct": 0.10, "max_pct": 0.20, "default_dur": 4.0, "required": True},
            {"name": "情绪堆叠",   "key": "emotion_build",    "min_pct": 0.10, "max_pct": 0.18, "default_dur": 4.0},
            {"name": "高潮爆发",   "key": "climax",           "min_pct": 0.10, "max_pct": 0.20, "default_dur": 4.0, "required": True},
            {"name": "CTA",        "key": "cta",              "min_pct": 0.05, "max_pct": 0.08, "default_dur": 2.0},
        ],
        "constraints": {"rhythm_segments_min": 3, "rhythm_segment_max_gap": 5.0},
        "total_min_dur": 15.0,
        "total_max_dur": 60.0,
    },

    "none": {
        "label": "无预设（透传拆解）",
        "description": "直接使用拆解视频的模块时间轴，不做模板替换",
        "modules": [],
        "pass_through": True,
    },
}

# ═══════════════════════════════════════════════════════
#  Key → sub_type / scene_tag matching hints
# ═══════════════════════════════════════════════════════

TEMPLATE_KEY_TO_ENDS: Dict[str, List[str]] = {
    "opening_intro":       ["片头", "标题卡", "开场", "引入"],
    "unboxing":            ["开箱", "展示"],
    "product_closeup":     ["产品特写", "商品展示", "产品展示", "特写"],
    "usage_scene":         ["使用场景", "场景", "演示"],
    "comparison":          ["对比", "效果对比"],
    "pros_cons":           ["总结", "优缺点"],
    "cta":                 ["CTA", "行动号召", "购买", "关注", "点赞", "品牌露出"],
    "pain_point":          ["痛点", "问题"],
    "selling_points":      ["卖点", "口播", "台词金句"],
    "demo":                ["演示", "使用"],
    "price_anchor":        ["价格", "优惠", "福利"],
    "urgency":             ["限时", "紧迫", "限量"],
    "topic_intro":         ["话题", "引入"],
    "long_speech":         ["解说", "讲解", "口播", "台词金句"],
    "viewpoint":           ["观点", "论述"],
    "case_study":          ["案例", "举例"],
    "quote_ending":        ["金句", "收尾"],
    "rhythm_opener":       ["节奏", "引爆"],
    "impact_a":            ["动作高燃", "视觉爆发", "冲击"],
    "bridge":              ["过渡", "转场", "硬切"],
    "impact_b":            ["动作高燃", "视觉爆发", "冲击"],
    "emotion_build":       ["情绪", "堆叠", "情绪峰值"],
    "climax":              ["高潮爆发", "情绪峰值"],
}
