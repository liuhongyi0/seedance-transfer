"""
图片生成Prompt构建器
将用户的中文选择拼合为高质量英文Prompt
"""

from services.translate import THEME_MAP, STYLE_MAP, LIGHTING_MAP, MOOD_MAP, translate_keyword


def build_image_prompt(
    theme: str = "",
    style: str = "",
    lighting: str = "",
    mood: str = "",
    keywords_cn: str = ""
) -> str:
    """
    构建 Seedream 4.5 图片生成Prompt

    格式：[主题], [风格], [光线], [情绪], [补充关键词], high quality, detailed
    """
    parts = []

    if theme:
        parts.append(THEME_MAP.get(theme, theme))

    if keywords_cn:
        kw_en = translate_keyword(keywords_cn)
        if kw_en:
            parts.append(kw_en)

    if style:
        parts.append(STYLE_MAP.get(style, style))

    if lighting:
        parts.append(LIGHTING_MAP.get(lighting, lighting))

    if mood:
        parts.append(MOOD_MAP.get(mood, mood))

    # 质量后缀
    parts.append("high quality, sharp details, professional photography")

    return ", ".join(filter(None, parts))


def build_video_prompt_from_selections(
    subject: dict = {},
    action: list = [],
    environment: dict = {},
    camera: dict = {},
    style: dict = {},
    constraints: list = []
) -> str:
    """
    构建 Seedance 2.0 视频Prompt（六步公式）
    前端Prompt Builder完成后，也可由前端直接拼合，此函数供后端备用
    """
    parts = []

    # 1. 主体
    if subject:
        subj_parts = []
        if subject.get("type") == "person":
            age = subject.get("age", "young adult")
            gender = subject.get("gender", "")
            clothing = subject.get("clothing", "")
            subj_parts.append(f"a {age} {gender}".strip())
            if clothing:
                subj_parts.append(f"wearing {clothing}")
        elif subject.get("type") == "product":
            subj_parts.append(subject.get("description", "a product"))
        if subj_parts:
            parts.append(", ".join(subj_parts))

    # 2. 动作
    if action:
        parts.append(", ".join(action))

    # 3. 环境
    if environment:
        env_parts = []
        if environment.get("location"):
            env_parts.append(environment["location"])
        if environment.get("time"):
            env_parts.append(environment["time"])
        if environment.get("material"):
            env_parts.append(environment["material"])
        if env_parts:
            parts.append(", ".join(env_parts))

    # 4. 镜头
    if camera:
        cam_parts = []
        if camera.get("movement"):
            cam_parts.append(camera["movement"])
        if camera.get("speed"):
            cam_parts.append(camera["speed"])
        if camera.get("shot_size"):
            cam_parts.append(camera["shot_size"])
        if cam_parts:
            parts.append(", ".join(cam_parts))

    # 5. 风格
    if style:
        style_parts = []
        if style.get("overall"):
            style_parts.append(style["overall"])
        if style.get("color_tone"):
            style_parts.append(style["color_tone"])
        if style.get("lighting"):
            style_parts.append(style["lighting"])
        if style_parts:
            parts.append(", ".join(style_parts))

    # 6. 负面约束
    if constraints:
        constraint_str = ", ".join([f"avoid {c}" for c in constraints])
        parts.append(constraint_str)

    return ". ".join(parts)
