"""
计费服务 —— 计算成本、扣款、退款
所有金额以 subunit（cents / fen）为单位，避免浮点精度问题
"""

from typing import Optional
from config import settings
from store import store


def calculate_cost(task_type: str, model_key: Optional[str] = None, **params) -> int:
    """计算任务成本，返回 subunit（cents/fen）

    - image / music：按模型目录固定单价 × count
    - video_draft：按模型目录 per-second 价 × duration（对齐 EvoLink 按秒计费）
    - final_video：按 config cost_final_per_sec × duration
    """
    from services.model_catalog import IMAGE, VIDEO_DRAFT, MUSIC, FINAL_VIDEO, get_credits

    if task_type == VIDEO_DRAFT:
        duration = params.get("duration", 5)
        resolution = params.get("resolution", "720p")
        credits_per_sec = get_credits(VIDEO_DRAFT, model_key)
        return credits_per_sec * duration

    if task_type in (IMAGE, MUSIC):
        credits = get_credits(task_type, model_key)
        count = params.get("count", 1)
        return credits * count

    if task_type == FINAL_VIDEO:
        resolution = params.get("resolution", "1080p")
        duration = params.get("duration", 12)
        credits_per_sec = get_credits(FINAL_VIDEO, None, resolution)
        return credits_per_sec * duration

    return 0


async def charge(user_id: str, task_type: str, amount_subunit: int, meta: str = "") -> int:
    """扣款（负值），返回新余额"""
    note = f"{task_type}: {meta}"[:200]
    return await store.topup_balance(user_id, -amount_subunit, tx_type="spend", note=note)


async def refund(user_id: str, task_type: str, amount_subunit: int, meta: str = "") -> int:
    """退款（正值），返回新余额"""
    note = f"refund {task_type}: {meta}"[:200]
    return await store.topup_balance(user_id, amount_subunit, tx_type="refund", note=note)


async def require_user(request) -> Optional[str]:
    """从 Authorization header 提取 user_id，支持 JWT 和 API Key（sk-seed-xxx）"""
    from routers.auth import verify_jwt
    import hashlib
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    if token.startswith("sk-seed-"):
        key_hash = hashlib.sha256(token.encode()).hexdigest()
        from store import store
        key = await store.get_api_key_by_hash(key_hash)
        if key:
            await store.touch_api_key(key["key_id"])
            request.state.user_id = key["user_id"]
            return key["user_id"]
        request.state.user_id = None
        return None
    user_id = verify_jwt(token)
    if user_id:
        request.state.user_id = user_id
    return user_id
