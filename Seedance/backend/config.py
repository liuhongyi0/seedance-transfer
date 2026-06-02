"""
配置管理 —— 从 .env 读取所有密钥和参数
"""

import os
from dotenv import load_dotenv
from log_config import get_logger

logger = get_logger(__name__)

load_dotenv()

class Settings:
    # ─── 部署区域 ──────────────────────────────────────────────────────────
    DEPLOYMENT_REGION: str = os.getenv("DEPLOYMENT_REGION", "cn").strip()  # cn | intl

    @property
    def is_intl(self) -> bool:
        return self.DEPLOYMENT_REGION == "intl"

    # ─── 货币配置 ──────────────────────────────────────────────────────────
    @property
    def currency(self) -> str:
        return "USD" if self.is_intl else "CNY"

    @property
    def currency_symbol(self) -> str:
        return "$" if self.is_intl else "¥"

    @property
    def currency_subunit(self) -> str:
        return "cents" if self.is_intl else "fen"

    # ─── EvoLink（统一平台：图片+音乐+视频草稿）────────────────────────────
    EVOLINK_API_KEY: str = os.getenv("EVOLINK_API_KEY", "")
    EVOLINK_BASE_URL: str = "https://api.evolink.ai/v1"

    # EvoLink 模型名称 —— 委托到 model_catalog 默认值
    # 使用 property 确保每次访问都从 catalog 读取（支持运行时更新）
    @property
    def EVOLINK_IMAGE_MODEL(self) -> str:
        from services.model_catalog import get_default
        return get_default("image")["evolink"]

    @property
    def EVOLINK_VIDEO_DRAFT_MODEL(self) -> str:
        from services.model_catalog import get_default
        return get_default("video_draft")["evolink"]

    @property
    def EVOLINK_MUSIC_MODEL(self) -> str:
        from services.model_catalog import get_default
        return get_default("music")["evolink"]

    EVOLINK_VISION_MODEL: str = "gemini-2.5-flash-lite"           # 备用视觉模型

    # ─── 图片中转（imgbb 免费图床，用于把 TOS 私有 URL 转为 EvoLink 可访问的公共 URL）
    # 注册地址：https://api.imgbb.com/  → 获取免费 API Key
    IMGBB_API_KEY: str = os.getenv("IMGBB_API_KEY", "")

    # ─── 火山引擎（最终成片 + Seedance 直连）─────────────────────────────────
    VOLC_API_KEY: str = os.getenv("VOLC_API_KEY", "")
    VOLC_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3"
    VOLC_MODEL: str = "doubao-seedance-2-0-260128"      # 最终成片
    VOLC_VIDEO_TASK_URL: str = "/contents/generations/tasks"
    VOLC_VISION_MODEL: str = "doubao-1-5-vision-pro-32k-250115"  # 图片描述/分析

    # ── 成本速查（image/music 仍由此管理；video_draft 已迁移至 model_catalog）

    @property
    def cost_image_per_unit(self) -> float:
        return 0.03 if self.is_intl else 0.22  # $/张 or ¥/张

    # 注意：视频草稿计费已迁移至 services/model_catalog.py 的 VIDEO_DRAFT_MODELS
    # billing.py 通过 get_video_price_per_sec() 读取，不再使用 config 硬编码

    # ── 安全 ──────────────────────────────────────────────────────────────
    JWT_SECRET: str = os.getenv("JWT_SECRET", "")

    @property
    def cost_music_per_unit(self) -> float:
        return 0.01 if self.is_intl else 0.10  # $/个 or ¥/个

    @property
    def cost_final_per_sec(self) -> dict:
        """最终成片成本 subunit/sec（fen or cents）"""
        if self.is_intl:
            return {"720p": 12, "1080p": 18, "2k": 36}   # cents/sec
        return {"720p": 80, "1080p": 130, "2k": 260}      # fen/sec

    # ─── 服务配置 ────────────────────────────────────────────────────────────
    # Session TTL（秒）：24小时
    SESSION_TTL: int = 86400

    # 轮询间隔（秒）
    POLL_INTERVAL: int = 3

    # 最大轮询次数（视频草稿最长300s，成片最长600s）
    MAX_POLL_DRAFT: int = 100   # 100×3s = 300s（5分钟）
    MAX_POLL_FINAL: int = 200   # 200×3s = 600s


settings = Settings()


def validate_keys():
    """启动时检查必要的API Key是否已配置"""
    missing = []
    if not settings.EVOLINK_API_KEY:
        missing.append("EVOLINK_API_KEY")
    if not settings.VOLC_API_KEY:
        missing.append("VOLC_API_KEY")
    if missing:
        logger.warning(f"⚠️  警告：以下API Key未配置，相关功能将返回Mock数据：{missing}")  # noqa: RUF001
        logger.info("   请在 backend/.env 文件中填写对应Key")
    return len(missing) == 0
