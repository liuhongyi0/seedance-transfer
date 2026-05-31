"""
模型目录 —— 所有可用模型的单一数据源。
每个模型定义：provider（volcengine | evolink）、API 名称、显示名、定价。
"""
from typing import Optional

# ── Pipeline steps ──────────────────────────────────────────────────────────
IMAGE = "image"
VIDEO_DRAFT = "video_draft"
MUSIC = "music"
FINAL_VIDEO = "final_video"

# ── Model catalogs per step ─────────────────────────────────────────────────

IMAGE_MODELS = {
    "seedream-4.5": {
        "evolink": "doubao-seedream-4.5",
        "display_cn": "Seedream 4.5",
        "display_en": "Seedream 4.5",
        "price_cn": 22,
        "price_intl": 3,
        "tags": ["default", "balanced"],
        "default": True,
    },
    "seedream-4.0": {
        "evolink": "doubao-seedream-4.0",
        "display_cn": "Seedream 4.0",
        "display_en": "Seedream 4.0",
        "price_cn": 18,
        "price_intl": 2,
        "tags": ["value"],
    },
    "gpt-image-2": {
        "evolink": "gpt-image-2",
        "display_cn": "GPT Image 2 (写实)",
        "display_en": "GPT Image 2 (Photo)",
        "price_cn": 30,
        "price_intl": 4,
        "tags": ["photorealistic"],
    },
    "gpt-image-1.5": {
        "evolink": "gpt-image-1.5",
        "display_cn": "GPT Image 1.5",
        "display_en": "GPT Image 1.5",
        "price_cn": 20,
        "price_intl": 3,
        "tags": ["openai"],
    },
    "nano-banana": {
        "evolink": "nano-banana-2-lite",
        "display_cn": "Nano Banana 2 (极速)",
        "display_en": "Nano Banana 2 (Fast)",
        "price_cn": 10,
        "price_intl": 1,
        "tags": ["fast", "cheap"],
    },
    "mj-v7": {
        "evolink": "mj-v7",
        "display_cn": "Midjourney V7 (艺术风格)",
        "display_en": "Midjourney V7 (Artistic)",
        "price_cn": 40,
        "price_intl": 5,
        "tags": ["artistic"],
    },
}

VIDEO_DRAFT_MODELS = {
    "seedance-1.5": {
        "provider": "evolink",
        "evolink": "seedance-1.5-pro",
        "display_cn": "Seedance 1.5 Pro (高性价比)",
        "display_en": "Seedance 1.5 Pro (Best Value)",
        "price_per_sec_cn": {"720p": 90, "1080p": 200},
        "price_per_sec_intl": {"720p": 12, "1080p": 28},
        "tags": ["default", "fast", "value"],
        "tier": "standard",
        "default": True,
    },
    "seedance-2.0": {
        "provider": "evolink",
        "volc_model": {
            "720p": "doubao-seedance-2-0-fast-260128",
            "1080p": "doubao-seedance-2-0-260128",
        },
        "evolink": "seedance-2.0-fast-text-to-video",
        "display_cn": "Seedance 2.0 (旗舰)",
        "display_en": "Seedance 2.0 (Flagship)",
        "price_per_sec_cn": {"720p": 80, "1080p": 130},
        "price_per_sec_intl": {"720p": 12, "1080p": 18},
        "tags": ["premium", "best"],
        "tier": "premium",
    },
    "kling-o3": {
        "provider": "evolink",
        "evolink": "kling-o3-text-to-video",
        "display_cn": "Kling O3 (电影级)",
        "display_en": "Kling O3 (Cinematic)",
        "price_per_sec_cn": {"720p": 180, "1080p": 400},
        "price_per_sec_intl": {"720p": 25, "1080p": 55},
        "tags": ["cinematic", "quality"],
        "tier": "premium",
    },
}

MUSIC_MODELS = {
    "suno-v4": {
        "evolink": "suno-v4",
        "display_cn": "Suno V4",
        "display_en": "Suno V4",
        "price_cn": 10,
        "price_intl": 1,
        "tags": ["default", "reliable"],
        "default": True,
    },
    "suno-v4.5": {
        "evolink": "suno-v4.5",
        "display_cn": "Suno V4.5 (增强)",
        "display_en": "Suno V4.5 (Enhanced)",
        "price_cn": 20,
        "price_intl": 2,
        "tags": ["enhanced", "quality"],
    },
    "suno-v5": {
        "evolink": "suno-v5",
        "display_cn": "Suno V5 (最新)",
        "display_en": "Suno V5 (Latest)",
        "price_cn": 30,
        "price_intl": 3,
        "tags": ["new", "best"],
    },
}

# Final video: only one model available (Volcengine direct, not EvoLink)
FINAL_VIDEO_MODELS = {
    "seedance-2.0": {
        "evolink": None,  # not through EvoLink
        "display_cn": "Seedance 2.0 (火山引擎)",
        "display_en": "Seedance 2.0 (Volcengine)",
        "price_cn": 0,   # dynamic: resolution × duration
        "price_intl": 0,
        "tags": ["default"],
        "default": True,
    },
}

_CATALOGS = {
    IMAGE: IMAGE_MODELS,
    VIDEO_DRAFT: VIDEO_DRAFT_MODELS,
    MUSIC: MUSIC_MODELS,
    FINAL_VIDEO: FINAL_VIDEO_MODELS,
}

# ── Public API ──────────────────────────────────────────────────────────────

def get_models(step: str) -> list[dict]:
    """返回某步骤的所有可用模型（含 key 注入）"""
    catalog = _CATALOGS.get(step, {})
    return [{**info, "key": key} for key, info in catalog.items()]


def get_model(step: str, key: str) -> Optional[dict]:
    """按 key 查找单个模型，不存在返回 None"""
    catalog = _CATALOGS.get(step, {})
    info = catalog.get(key)
    if info:
        return {**info, "key": key}
    return None


def get_default(step: str) -> dict:
    """返回默认模型，不存在则返回第一个"""
    catalog = _CATALOGS.get(step, {})
    for key, info in catalog.items():
        if info.get("default"):
            return {**info, "key": key}
    first = next(iter(catalog.items()), None)
    if first:
        key, info = first
        return {**info, "key": key}
    return {"key": "unknown", "evolink": "unknown", "price_cn": 0, "price_intl": 0}


def get_evolink_name(step: str, key: Optional[str] = None) -> str:
    """获取 EvoLink API 模型名，未指定 key 则返回默认"""
    if not key:
        return get_default(step)["evolink"]
    model = get_model(step, key)
    if not model:
        return get_default(step)["evolink"]
    return model["evolink"]


def get_price(step: str, key: Optional[str], is_intl: bool) -> int:
    """获取模型定价（subunit）"""
    model = get_model(step, key) if key else get_default(step)
    if not model:
        return 0
    return model["price_intl"] if is_intl else model["price_cn"]


def get_provider(step: str, key: Optional[str] = None) -> str:
    """返回模型的 API provider（volcengine | evolink），默认 evolink"""
    model = get_model(step, key) if key else get_default(step)
    return model.get("provider", "evolink") if model else "evolink"


def get_volc_model(step: str, key: Optional[str], resolution: str = "720p") -> str:
    """获取 Volcengine 模型名，支持按分辨率选择不同模型"""
    model = get_model(step, key) if key else get_default(step)
    if not model:
        return ""
    volc = model.get("volc_model", "")
    if isinstance(volc, dict):
        return volc.get(resolution, volc.get("720p", ""))
    return volc


def get_video_price_per_sec(key: Optional[str], resolution: str, is_intl: bool) -> float:
    """获取视频模型每秒定价（subunit/sec），未知分辨率默认回退 720p"""
    model = get_model(VIDEO_DRAFT, key) if key else get_default(VIDEO_DRAFT)
    if not model:
        return 0.0
    per_sec_map = model.get("price_per_sec_intl" if is_intl else "price_per_sec_cn", {})
    if resolution in per_sec_map:
        return float(per_sec_map[resolution])
    return float(per_sec_map.get("720p", 0))
