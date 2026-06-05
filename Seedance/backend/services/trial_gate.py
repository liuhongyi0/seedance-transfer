"""
试用量产门禁 — 未付费用户不能使用高 cost 模型
"""
from store import store
from services.model_catalog import get_credits, IMAGE, VIDEO_DRAFT, MUSIC

# 免费试用可用的模型上限
TRIAL_MAX_VIDEO_PER_SEC = 2  # SD2.0(4pt/s) 不可用
TRIAL_MAX_IMAGE_CREDITS = 1  # MJ V7(3pt) 不可用
TRIAL_MAX_MUSIC_CREDITS = 2  # 音乐统一 2pt，都可用


async def is_trial_user(user_id: str) -> bool:
    """用户是否从未充值过（只有免费试用赠金）"""
    if not user_id:
        return True
    txs = await store.get_transactions(user_id, limit=200)
    # 检查是否有 topup 类型的交易（非 gift 非 test_topup）
    for tx in txs:
        if tx.get("tx_type") in ("topup", "payment"):
            return False
    return True


async def check_trial_gate(user_id: str, step: str, model_key: str) -> None:
    """
    检查试用用户是否试图使用高端模型。
    如果免费用户选了贵模型 → 直接拒绝。
    """
    if not user_id:
        return  # no auth → handled elsewhere

    trial = await is_trial_user(user_id)
    if not trial:
        return  # 已付费用户 → 不受限制

    from fastapi import HTTPException

    if step == VIDEO_DRAFT:
        cost = get_credits(VIDEO_DRAFT, model_key)
        if cost > TRIAL_MAX_VIDEO_PER_SEC:
            raise HTTPException(
                status_code=402,
                detail=f"Free trial allows models up to {TRIAL_MAX_VIDEO_PER_SEC}pt/sec. "
                       f"'{model_key}' costs {cost}pt/sec. Buy a package to unlock all 18 models."
            )
    elif step == IMAGE:
        cost = get_credits(IMAGE, model_key)
        if cost > TRIAL_MAX_IMAGE_CREDITS:
            raise HTTPException(
                status_code=402,
                detail=f"Free trial allows models up to {TRIAL_MAX_IMAGE_CREDITS}pt/image. "
                       f"'{model_key}' costs {cost}pt. Buy a package to unlock all 18 models."
            )
    elif step == MUSIC:
        cost = get_credits(MUSIC, model_key)
        if cost > TRIAL_MAX_MUSIC_CREDITS:
            raise HTTPException(
                status_code=402,
                detail=f"Free trial allows models up to {TRIAL_MAX_MUSIC_CREDITS}pt/track. "
                       f"'{model_key}' costs {cost}pt. Buy a package to unlock all 18 models."
            )
