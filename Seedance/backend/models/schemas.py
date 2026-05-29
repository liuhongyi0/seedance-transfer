"""
Pydantic 数据模型 —— 所有API请求/响应的类型定义
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from enum import Enum


# ─── 通用 ───────────────────────────────────────────────────────────────────

class ApiResponse(BaseModel):
    success: bool
    message: str = ""
    data: Optional[dict] = None


# ─── 会话 ───────────────────────────────────────────────────────────────────

class SessionCreate(BaseModel):
    pass  # 匿名会话，无需参数

class SessionInfo(BaseModel):
    session_id: str
    created_at: str
    assets: dict  # {images: [], videos: [], musics: []}


# ─── 步骤一：图片生成 ─────────────────────────────────────────────────────────

class ImageGenerateRequest(BaseModel):
    session_id: str
    prompt_cn: str = Field(..., description="中文描述，后端自动翻译为英文")
    style: str = Field(default="cinematic", description="风格标签")
    lighting: str = Field(default="natural soft light", description="光线标签")
    mood: str = Field(default="warm healing", description="情绪氛围")
    theme: str = Field(default="", description="主题（人物/产品/建筑等）")
    ratio: Literal["16:9", "9:16", "1:1", "4:3"] = "16:9"
    count: int = Field(default=3, ge=1, le=4, description="生成数量")

class ImageGenerateResponse(BaseModel):
    task_id: str
    status: str  # pending / processing / completed / failed
    images: List[str] = []  # 图片URL列表


# ─── 步骤二：图片调色（纯前端CSS，后端仅记录参数供步骤三使用）────────────────

class ColorAdjustSaveRequest(BaseModel):
    session_id: str
    image_id: str
    brightness: float = 0    # -100 ~ +100
    contrast: float = 0
    shadows: float = 0
    highlights: float = 0
    saturation: float = 0
    color_temp: float = 0    # 负=冷蓝 正=暖黄


# ─── 步骤三：视频草稿生成 ──────────────────────────────────────────────────────

class VideoDraftRequest(BaseModel):
    session_id: str
    reference_image_id: Optional[str] = None   # 素材盘中的图片ID
    reference_image_url: Optional[str] = None  # 直接传URL也可
    prompt_en: str = Field(..., description="英文提示词（由前端Prompt Builder拼合）")
    # 草稿固定参数（节省成本）
    resolution: Literal["480p"] = "480p"
    duration: Literal[5] = 5

class VideoDraftResponse(BaseModel):
    task_id: str
    status: str
    video_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    cost_usd: float = 0.37   # 480p×5s EvoLink Fast 预估成本


# ─── 步骤四：音乐生成 ─────────────────────────────────────────────────────────

class MusicGenerateRequest(BaseModel):
    session_id: str
    mood: str = Field(..., description="情绪：热血/温柔/神秘/欢快/史诗/空灵")
    genre: str = Field(..., description="曲风：电子/古典/爵士/民谣/摇滚/国风")
    instruments: List[str] = Field(default=[], description="主要乐器列表")
    tempo: Literal["very_slow", "slow", "medium", "fast"] = "medium"
    duration: int = Field(default=30, ge=10, le=30)
    prompt_override: Optional[str] = None  # 高级用户可直接传Suno prompt

class MusicGenerateResponse(BaseModel):
    task_id: str
    status: str
    audio_url: Optional[str] = None
    waveform_url: Optional[str] = None
    duration_s: int = 30


# ─── 步骤五：最终成片生成 ──────────────────────────────────────────────────────

class FinalVideoRequest(BaseModel):
    session_id: str
    reference_image_id: str         # 选中的参考图（必须）
    video_draft_id: str             # 选中的视频草稿（必须，用于提取运镜/风格）
    music_id: Optional[str] = None  # 选中的音乐（可选）
    prompt_en: str                  # 最终确认的英文Prompt
    resolution: Literal["720p", "1080p", "2k"] = "1080p"
    duration: Literal[6, 8, 10, 12, 15] = 12
    aspect_ratio: Literal["16:9", "9:16", "1:1", "4:3"] = "16:9"

class FinalVideoResponse(BaseModel):
    task_id: str
    status: str
    video_url: Optional[str] = None
    cost_cny: float = 0.0            # 实际扣费（人民币）
    estimated_wait_s: int = 120      # 预计等待秒数


# ─── 任务轮询 ─────────────────────────────────────────────────────────────────

class TaskStatusResponse(BaseModel):
    task_id: str
    status: Literal["pending", "processing", "completed", "failed"]
    progress: int = 0       # 0-100
    result_url: Optional[str] = None
    error: Optional[str] = None
    cost: Optional[float] = None
