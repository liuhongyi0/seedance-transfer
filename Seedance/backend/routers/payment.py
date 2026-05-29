"""
支付路由
GET  /api/payment/pricing          → 套餐定价（根据 region 显示 ¥ 或 $）
GET  /api/payment/dashboard        → 用户控制台（需 Bearer Token）
GET  /api/payment/transactions     → 交易记录（需 Bearer Token）
POST /api/payment/test-topup       → 测试充值（开发期，需 Bearer Token）
POST /api/payment/create-checkout  → 创建 Stripe Checkout Session
POST /api/payment/stripe/webhook   → Stripe Webhook
POST /api/payment/wechat/webhook   → 微信支付回调（占位）
"""

import os
import stripe as _stripe
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from config import settings
from store import store

router = APIRouter()

STRIPE_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# Stripe 套餐映射：package_id → (amount_subunit, credits, name)
STRIPE_PACKAGES = {
    "starter":  {"amount_subunit": 700,   "credits": 50,  "name": "Starter"},
    "standard": {"amount_subunit": 1800,  "credits": 200, "name": "Standard"},
    "pro":      {"amount_subunit": 5200,  "credits": 800, "name": "Pro"},
}


class CheckoutRequest(BaseModel):
    package_id: str
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class TopupRequest(BaseModel):
    amount_subunit: int = 10000
    tx_type: str = "test_topup"


# ─── 辅助函数 ─────────────────────────────────────────────────────────────

def _verify_token(request: Request) -> str:
    """从 Authorization header 提取并验证 JWT，返回 user_id"""
    from routers.auth import verify_jwt

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Login required")
    user_id = verify_jwt(auth_header[7:])
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id


# ─── 路由 ─────────────────────────────────────────────────────────────────

@router.get("/pricing")
async def get_pricing():
    """返回套餐定价，根据 region 自动切换币种"""
    sym = settings.currency_symbol
    cur = settings.currency

    if settings.is_intl:
        packages = [
            {"id": "starter",  "name": "Starter",  "amount": 7,   "credits": 50,
             "desc": "~1 full creation",  "popular": False},
            {"id": "standard", "name": "Standard", "amount": 18,  "credits": 200,
             "desc": "~3 full creations", "popular": True},
            {"id": "pro",      "name": "Pro",      "amount": 52,  "credits": 800,
             "desc": "~12 full creations", "popular": False},
        ]
    else:
        packages = [
            {"id": "starter",  "name": "体验包",  "amount": 49,  "credits": 35,
             "desc": "约1次完整创作（1080p×10s）", "popular": False},
            {"id": "standard", "name": "基础包",  "amount": 128, "credits": 110,
             "desc": "约3次完整创作 · 月度订阅",   "popular": True},
            {"id": "pro",      "name": "专业包",  "amount": 368, "credits": 400,
             "desc": "约12次完整创作 · 月度订阅",  "popular": False},
        ]

    return {
        "currency": cur,
        "symbol": sym,
        "packages": [
            {**p, "display": f"{sym}{p['amount']}",
             "credits_display": f"{p['credits']} 点数"}
            for p in packages
        ],
        "note": "Payment integration coming soon" if settings.is_intl else "支付功能即将上线，点数永久有效"
    }


@router.get("/dashboard")
async def get_dashboard(request: Request):
    """用户控制台：余额 + 交易记录 + 定价"""
    user_id = _verify_token(request)
    user = await store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    transactions = await store.get_transactions(user_id, limit=20)

    return {
        "success": True,
        "user": {
            "user_id": user["user_id"],
            "email": user.get("email"),
            "phone": user.get("phone"),
            "balance_subunit": user["balance_subunit"],
            "currency": user["currency"],
            "created_at": user.get("created_at"),
        },
        "transactions": transactions,
    }


@router.get("/transactions")
async def get_transactions(request: Request):
    """最近 50 条交易记录"""
    user_id = _verify_token(request)
    txs = await store.get_transactions(user_id, limit=50)
    return {"success": True, "transactions": txs}


@router.post("/test-topup")
async def test_topup(req: TopupRequest, request: Request):
    """
    测试充值（仅开发期使用，生产环境由 Stripe/微信支付 webhook 替代）
    在 PG 事务中完成：UPDATE balance + INSERT transaction
    """
    user_id = _verify_token(request)
    try:
        new_balance = await store.topup_balance(
            user_id, req.amount_subunit, tx_type=req.tx_type,
            note="Test recharge (development only)"
        )
        return {"success": True, "new_balance_subunit": new_balance}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/create-checkout")
async def create_checkout(req: CheckoutRequest, request: Request):
    """创建 Stripe Checkout Session"""
    if not settings.is_intl:
        raise HTTPException(status_code=501, detail="Stripe only available in international region")

    user_id = _verify_token(request)
    pkg = STRIPE_PACKAGES.get(req.package_id)
    if not pkg:
        raise HTTPException(status_code=400, detail=f"Unknown package: {req.package_id}")

    if not STRIPE_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    success_url = req.success_url or f"{BASE_URL}/"
    cancel_url = req.cancel_url or f"{BASE_URL}/"

    try:
        session = _stripe.checkout.Session.create(
            api_key=STRIPE_KEY,
            mode="payment",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": settings.currency.lower(),
                    "product_data": {
                        "name": f"Seedance {pkg['name']} — {pkg['credits']} Credits",
                    },
                    "unit_amount": pkg["amount_subunit"],
                },
                "quantity": 1,
            }],
            metadata={
                "user_id": user_id,
                "package_id": req.package_id,
                "credits": str(pkg["credits"]),
            },
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return {"success": True, "url": session.url}
    except Exception as e:
        print(f"[STRIPE CHECKOUT] Error: {e}")
        raise HTTPException(status_code=500, detail="Stripe checkout creation failed")


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """Stripe Webhook：接收 payment 确认事件，自动充值"""
    if not STRIPE_KEY or not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Stripe webhook not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    print(f"[WEBHOOK] sig_header={sig_header[:50]}... key={STRIPE_KEY[:15]}... whsec={STRIPE_WEBHOOK_SECRET[:15]}...")
    try:
        event = _stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET, api_key=STRIPE_KEY
        )
    except ValueError as e:
        print(f"[WEBHOOK] ValueError: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")
    except _stripe.error.SignatureVerificationError as e:
        print(f"[WEBHOOK] SignatureVerificationError: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid signature: {e}")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        # Stripe SDK v9+ 返回 StripeObject, 无 .get() 方法，需 to_dict()
        s = session.to_dict() if hasattr(session, 'to_dict') else dict(session)
        meta = s.get("metadata") or {}
        user_id = meta.get("user_id")
        package_id = meta.get("package_id", "unknown")
        amount_total = s.get("amount_total", 0)

        if user_id:
            note = f"Stripe: {package_id}, session: {s.get('id', '')[:20]}"
            try:
                await store.topup_balance(user_id, amount_total, tx_type="topup", note=note)
            except Exception:
                import traceback
                print(f"[WEBHOOK] topup failed: {traceback.format_exc()}")
                raise HTTPException(status_code=500, detail="Topup failed")

    return {"status": "ok"}


@router.post("/wechat/webhook")
async def wechat_webhook(request: Request):
    """微信支付回调（占位）"""
    raise HTTPException(
        status_code=501,
        detail="WeChat Pay webhook not yet implemented."
    )
