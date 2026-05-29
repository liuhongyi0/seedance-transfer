"""
音乐Prompt构建器（Suno v4格式）
"""


def build_music_prompt(mood: str, genre: str, instruments: list,
                       tempo: str, duration: int) -> str:
    """
    构建 Suno v4 音乐生成Prompt

    Suno最佳实践：
    - 用情绪词 + 曲风 + 乐器 + 节拍 + 时长
    - 避免过于具体的歌词描述（纯音乐不需要）
    """
    parts = [mood, genre]
    if instruments:
        parts.append(f"featuring {', '.join(instruments)}")
    parts.append(tempo)
    parts.append(f"{duration} seconds instrumental")
    parts.append("no vocals, background music")
    return ", ".join(filter(None, parts))
