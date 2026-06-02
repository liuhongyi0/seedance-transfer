"""
模型目录 —— 所有可用模型的单一数据源。
每个模型定义：provider、API 名称、显示名、credit 消耗点数。"""
from typing import Optional

IMAGE = "image"
VIDEO_DRAFT = "video_draft"
MUSIC = "music"
FINAL_VIDEO = "final_video"

# ── 点数：每个操作消耗的 credit 点数 ────────────────────────────────────────
# 定价逻辑：API 成本 × 2~3 倍 = 客户点数 × $0.066/pt（Standard 基准）
# 贵模型多吃点数，便宜模型少吃。毛利率 30-71%。

IMAGE_MODELS = {
    "seedream-4.5": {
        "evolink": "doubao-seedream-4.5", "credits": 1,
        "display_cn": "Seedream 4.5", "display_en": "Seedream 4.5",
        "tags": ["default", "balanced"], "default": True,
    },
    "seedream-4.0": {
        "evolink": "doubao-seedream-4.0", "credits": 1,
        "display_cn": "Seedream 4.0", "display_en": "Seedream 4.0",
        "tags": ["value"],
    },
    "seedream-5.0-lite": {
        "evolink": "doubao-seedream-5.0-lite", "credits": 1,
        "display_cn": "Seedream 5.0 Lite", "display_en": "Seedream 5.0 Lite",
        "tags": ["new"],
    },
    "gpt-image-2": {
        "evolink": "gpt-image-2", "credits": 1,
        "display_cn": "GPT Image 2 (写实)", "display_en": "GPT Image 2 (Photo)",
        "tags": ["photorealistic"],
    },
    "gpt-image-1.5": {
        "evolink": "gpt-image-1.5", "credits": 1,
        "display_cn": "GPT Image 1.5", "display_en": "GPT Image 1.5",
        "tags": ["openai"],
    },
    "nano-banana": {
        "evolink": "nano-banana-2-lite", "credits": 1,
        "display_cn": "Nano Banana 2 (极速)", "display_en": "Nano Banana 2 (Fast)",
        "tags": ["fast", "cheap"],
    },
    "mj-v7": {
        "evolink": "mj-v7", "credits": 3,
        "display_cn": "Midjourney V7 (艺术)", "display_en": "Midjourney V7 (Artistic)",
        "tags": ["artistic"],
    },
}

IMAGE_CREDITS = {k: v["credits"] for k, v in IMAGE_MODELS.items()}

VIDEO_DRAFT_MODELS = {
    "seedance-1.5": {
        "provider": "evolink", "evolink": "seedance-1.5-pro",
        "credits_per_sec": 1,
        "display_cn": "Seedance 1.5 Pro (性价比)", "display_en": "Seedance 1.5 Pro (Best Value)",
        "tags": ["default", "fast", "value"], "default": True,
    },
    "seedance-2.0": {
        "provider": "evolink", "evolink": "seedance-2.0-fast-text-to-video",
        "volc_model": {"720p": "doubao-seedance-2-0-fast-260128", "1080p": "doubao-seedance-2-0-260128"},
        "credits_per_sec": 4,
        "display_cn": "Seedance 2.0 (旗舰)", "display_en": "Seedance 2.0 (Flagship)",
        "tags": ["premium", "best"],
    },
    "veo3.1-fast": {
        "provider": "evolink", "evolink": "veo3.1-fast",
        "credits_per_sec": 1,
        "display_cn": "Veo 3.1 Fast (Google)", "display_en": "Veo 3.1 Fast (Google)",
        "tags": ["google", "value"],
    },
    "veo3-fast": {
        "provider": "evolink", "evolink": "veo3-fast",
        "credits_per_sec": 1,
        "display_cn": "Veo 3 Fast (Google)", "display_en": "Veo 3 Fast (Google)",
        "tags": ["google"],
    },
    "veo3.1-pro": {
        "provider": "evolink", "evolink": "veo3.1-pro",
        "credits_per_sec": 3,
        "display_cn": "Veo 3.1 Pro (Google)", "display_en": "Veo 3.1 Pro (Google)",
        "tags": ["google", "premium"],
    },
    "sora-2": {
        "provider": "evolink", "evolink": "sora-2",
        "credits_per_sec": 3,
        "display_cn": "Sora 2 (OpenAI)", "display_en": "Sora 2 (OpenAI)",
        "tags": ["openai"],
    },
    "kling-v3": {
        "provider": "evolink", "evolink": "kling-v3-text-to-video",
        "credits_per_sec": 2,
        "display_cn": "Kling V3 (快手)", "display_en": "Kling V3 (Kuaishou)",
        "tags": ["value", "kling"],
    },
    "kling-o3": {
        "provider": "evolink", "evolink": "kling-o3-text-to-video",
        "credits_per_sec": 2,
        "display_cn": "Kling O3 (电影级)", "display_en": "Kling O3 (Cinematic)",
        "tags": ["cinematic", "kling"],
    },
    "wan-2.6": {
        "provider": "evolink", "evolink": "wan2.6-text-to-video",
        "credits_per_sec": 2,
        "display_cn": "Wan 2.6 (阿里)", "display_en": "Wan 2.6 (Alibaba)",
        "tags": ["balanced"],
    },
    "wan-2.7": {
        "provider": "evolink", "evolink": "wan2.7-text-to-video",
        "credits_per_sec": 2,
        "display_cn": "Wan 2.7 (阿里·新)", "display_en": "Wan 2.7 (Alibaba·New)",
        "tags": ["new"],
    },
    "hailuo-2.3": {
        "provider": "evolink", "evolink": "MiniMax-Hailuo-2.3",
        "credits_per_sec": 2,
        "display_cn": "Hailuo 2.3 (海螺)", "display_en": "Hailuo 2.3 (MiniMax)",
        "tags": ["cinematic"],
    },
}

VIDEO_DRAFT_CREDITS = {k: v["credits_per_sec"] for k, v in VIDEO_DRAFT_MODELS.items()}

MUSIC_MODELS = {
    "suno-v4": {
        "evolink": "suno-v4", "credits": 2,
        "display_cn": "Suno V4", "display_en": "Suno V4",
        "tags": ["default", "reliable"], "default": True,
    },
    "suno-v4.5": {
        "evolink": "suno-v4.5", "credits": 2,
        "display_cn": "Suno V4.5 (增强)", "display_en": "Suno V4.5 (Enhanced)",
        "tags": ["enhanced"],
    },
    "suno-v5": {
        "evolink": "suno-v5", "credits": 2,
        "display_cn": "Suno V5 (最新)", "display_en": "Suno V5 (Latest)",
        "tags": ["best"],
    },
}

MUSIC_CREDITS = {k: v["credits"] for k, v in MUSIC_MODELS.items()}

FINAL_VIDEO_MODELS = {
    "seedance-2.0": {
        "evolink": None,
        "credits_per_sec": {"720p": 2, "1080p": 3},
        "display_cn": "Seedance 2.0 (火山引擎)", "display_en": "Seedance 2.0 (Volcengine)",
        "tags": ["default"], "default": True,
    },
}

_CATALOGS = {IMAGE: IMAGE_MODELS, VIDEO_DRAFT: VIDEO_DRAFT_MODELS,
             MUSIC: MUSIC_MODELS, FINAL_VIDEO: FINAL_VIDEO_MODELS}

_CREDITS = {**{("image", k): v for k, v in IMAGE_CREDITS.items()},
            **{("video_draft", k): v for k, v in VIDEO_DRAFT_CREDITS.items()},
            **{("music", k): v for k, v in MUSIC_CREDITS.items()}}

# ── Public API ──────────────────────────────────────────────────────────────

def get_models(step: str) -> list[dict]:
    catalog = _CATALOGS.get(step, {})
    return [{**info, "key": key} for key, info in catalog.items()]

def get_model(step: str, key: str) -> Optional[dict]:
    catalog = _CATALOGS.get(step, {})
    info = catalog.get(key)
    return {**info, "key": key} if info else None

def get_default(step: str) -> dict:
    catalog = _CATALOGS.get(step, {})
    for key, info in catalog.items():
        if info.get("default"):
            return {**info, "key": key}
    first = next(iter(catalog.items()), None)
    if first:
        key, info = first
        return {**info, "key": key}
    return {"key": "unknown", "evolink": "unknown"}

def get_evolink_name(step: str, key: Optional[str] = None) -> str:
    if not key:
        return get_default(step)["evolink"]
    model = get_model(step, key)
    return model["evolink"] if model else get_default(step)["evolink"]

def get_provider(step: str, key: Optional[str] = None) -> str:
    model = get_model(step, key) if key else get_default(step)
    return model.get("provider", "evolink") if model else "evolink"

def get_volc_model(step: str, key: Optional[str], resolution: str = "720p") -> str:
    model = get_model(step, key) if key else get_default(step)
    if not model:
        return ""
    volc = model.get("volc_model", "")
    if isinstance(volc, dict):
        return volc.get(resolution, volc.get("720p", ""))
    return volc

def get_credits(step: str, key: Optional[str] = None, resolution: str = "720p") -> int:
    """返回某模型某操作的信用点数。整数。"""
    if step == IMAGE:
        model = get_model(step, key) if key else get_default(step)
        return model.get("credits", 1) if model else 1
    elif step == MUSIC:
        model = get_model(step, key) if key else get_default(step)
        return model.get("credits", 2) if model else 2
    elif step == VIDEO_DRAFT:
        model = get_model(step, key) if key else get_default(step)
        return model.get("credits_per_sec", 1) if model else 1
    elif step == FINAL_VIDEO:
        model = get_model(step, key) if key else get_default(step)
        if not model:
            return 2
        cps = model.get("credits_per_sec", {"720p": 2, "1080p": 3})
        if isinstance(cps, dict):
            return cps.get(resolution, cps.get("720p", 2))
        return cps
    return 1

def get_credits_per_sec(key: Optional[str], resolution: str = "720p") -> int:
    model = get_model(VIDEO_DRAFT, key) if key else get_default(VIDEO_DRAFT)
    if not model:
        return 1
    return model.get("credits_per_sec", 1)

def get_final_credits_per_sec(resolution: str = "720p") -> int:
    model = get_default(FINAL_VIDEO)
    cps = model.get("credits_per_sec", {"720p": 2, "1080p": 3})
    if isinstance(cps, dict):
        return cps.get(resolution, 2)
    return cps
