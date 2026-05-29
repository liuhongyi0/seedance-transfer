"""
中文→英文翻译辅助（基于预设词典，无需调用翻译API）
高频词汇直接映射，降低延迟和成本
"""

# 主题映射
THEME_MAP = {
    "人物": "person",
    "产品": "product",
    "建筑": "architecture",
    "自然风景": "natural landscape",
    "街景": "street scene",
    "动物": "animal",
    "美食": "food",
    "抽象艺术": "abstract art",
    "机械/科技": "mechanical, technology",
    "时尚": "fashion",
    "运动": "sports",
    "奇幻": "fantasy",
}

# 风格映射
STYLE_MAP = {
    "电影质感": "cinematic, film photography",
    "真实摄影": "realistic photography, photorealistic",
    "动漫插画": "anime illustration, japanese animation style",
    "3D渲染": "3D rendering, CGI",
    "水墨国画": "Chinese ink painting, traditional brush art",
    "赛博朋克": "cyberpunk, neon-lit dystopian",
    "复古胶片": "vintage film, 35mm grain, retro",
}

# 光线映射
LIGHTING_MAP = {
    "黄金时刻": "golden hour lighting, warm sunlight",
    "自然柔光": "soft natural light, diffused daylight",
    "霓虹灯光": "neon lighting, colorful artificial light",
    "逆光剪影": "backlight silhouette, contre-jour",
    "阴天漫反射": "overcast sky, soft diffused light",
    "聚光灯": "spotlight, dramatic stage lighting",
}

# 情绪氛围映射
MOOD_MAP = {
    "温暖治愈": "warm, healing, comforting atmosphere",
    "神秘黑暗": "mysterious, dark, moody",
    "清新明亮": "fresh, bright, uplifting",
    "史诗壮阔": "epic, grand, sweeping",
    "梦幻飘渺": "dreamy, ethereal, misty",
    "写实纪录": "documentary, realistic, raw",
}


def translate_keyword(keyword: str) -> str:
    """
    简单中文关键词翻译
    先查词典，再做基本处理
    """
    keyword = keyword.strip()
    if not keyword:
        return ""

    # 查主题词典
    combined = {**THEME_MAP, **STYLE_MAP, **LIGHTING_MAP, **MOOD_MAP}
    if keyword in combined:
        return combined[keyword]

    # 常见场景词
    scene_map = {
        "樱花树下": "under cherry blossom trees",
        "未来城市": "futuristic city",
        "海边": "seaside, beach",
        "森林": "forest",
        "咖啡馆": "coffee shop",
        "雨中": "in the rain",
        "夜晚": "at night",
        "日落": "sunset",
        "雪景": "snowy scene",
    }
    if keyword in scene_map:
        return scene_map[keyword]

    # 无法翻译时，原样返回（EvoLink支持中英混合Prompt）
    return keyword


async def translate_to_english(text_cn: str) -> str:
    """异步翻译（目前用词典，后续可接入翻译API）"""
    if not text_cn:
        return ""
    return translate_keyword(text_cn)
