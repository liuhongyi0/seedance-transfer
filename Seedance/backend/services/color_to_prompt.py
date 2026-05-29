"""
调色参数→Prompt描述词映射
将步骤二的CSS滑块参数转换为 Seedance 可理解的光线/色调描述
"""


def color_params_to_prompt(params: dict) -> str:
    """
    将调色参数映射为英文风格描述词，追加到视频Prompt末尾

    参数范围均为 -100 ~ +100，默认值0表示无调整
    """
    descriptions = []

    brightness = params.get("brightness", 0)
    contrast = params.get("contrast", 0)
    shadows = params.get("shadows", 0)
    highlights = params.get("highlights", 0)
    saturation = params.get("saturation", 0)
    color_temp = params.get("color_temp", 0)

    # 亮度
    if brightness > 50:
        descriptions.append("bright, high-key lighting")
    elif brightness > 20:
        descriptions.append("well-lit, bright atmosphere")
    elif brightness < -50:
        descriptions.append("dark, low-key, moody lighting")
    elif brightness < -20:
        descriptions.append("dim, understated lighting")

    # 对比度
    if contrast > 50:
        descriptions.append("high contrast, dramatic shadows")
    elif contrast > 20:
        descriptions.append("contrasty, defined shadows")
    elif contrast < -30:
        descriptions.append("soft contrast, flat lighting")

    # 高光
    if highlights > 40:
        descriptions.append("blown highlights, overexposed")
    elif highlights < -40:
        descriptions.append("recovered highlights, controlled exposure")

    # 阴影
    if shadows > 40:
        descriptions.append("lifted shadows, bright fill light")
    elif shadows < -40:
        descriptions.append("deep shadows, crushed blacks")

    # 饱和度
    if saturation > 50:
        descriptions.append("vivid, saturated colors")
    elif saturation > 20:
        descriptions.append("vibrant colors")
    elif saturation < -50:
        descriptions.append("desaturated, black and white")
    elif saturation < -20:
        descriptions.append("muted, desaturated tones")

    # 色温
    if color_temp > 50:
        descriptions.append("warm orange-golden palette")
    elif color_temp > 20:
        descriptions.append("warm color temperature")
    elif color_temp < -50:
        descriptions.append("cool blue palette, cold atmosphere")
    elif color_temp < -20:
        descriptions.append("cool color temperature, blue tones")

    return ", ".join(descriptions)
