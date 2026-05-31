"""
支付路由 — Creem（MoR 全球支付）
GET  /api/payment/pricing          → 套餐定价（根据 region 显示 ¥ 或 $）
GET  /api/payment/dashboard        → 用户控制台（需 Bearer Token）
GET  /api/payment/transactions     → 交易记录（需 Bearer Token）
POST /api/payment/test-topup       → 测试充值（开发期，需 Bearer Token）
POST /api/payment/create-checkout  → 创建 Creem Checkout Session
POST /api/payment/creem/webhook    → Creem Webhook（自动充值）
POST /api/payment/wechat/webhook   → 微信支付回调（占位）
"""

import os
import hmac
import hashlib
import httpx
import uuid
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from config import settings
from store import store
from log_config import get_logger

logger = get_logger(__name__)

router = APIRouter()

CREEM_API_KEY = os.getenv("CREEM_API_KEY", "")
CREEM_WEBHOOK_SECRET = os.getenv("CREEM_WEBHOOK_SECRET", "")
CREEM_TEST_MODE = CREEM_API_KEY.startswith("creem_test_") if CREEM_API_KEY else True
CREEM_BASE = "https://test-api.creem.io" if CREEM_TEST_MODE else "https://api.creem.io"
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# Creem 产品映射：package_id → (product_id, pts, name)
# 在 Creem Dashboard 创建产品后，把 product_id 填到这里
CREEM_PRODUCTS = {
    "starter":  {"product_id": os.getenv("CREEM_PRODUCT_STARTER", ""),  "credits": 120, "name": "Starter"},
    "standard": {"product_id": os.getenv("CREEM_PRODUCT_STANDARD", ""), "credits": 270, "name": "Standard"},
    "pro":      {"product_id": os.getenv("CREEM_PRODUCT_PRO", ""),      "credits": 900, "name": "Pro"},
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
            {"id": "starter",  "name": "Starter",  "amount": 11.9,   "credits": 120,
             "desc": "30s 720p · $0.40/s",  "popular": False},
            {"id": "standard", "name": "Standard", "amount": 23.9,  "credits": 270,
             "desc": "75s 720p · $0.32/s", "popular": True},
            {"id": "pro",      "name": "Pro",      "amount": 69.9,  "credits": 900,
             "desc": "250s 720p · $0.28/s", "popular": False},
        ]
    else:
        packages = [
            {"id": "starter",  "name": "体验包",  "amount": 79,  "credits": 120,
             "desc": "30秒720p · ¥2.63/秒", "popular": False},
            {"id": "standard", "name": "基础包",  "amount": 169, "credits": 270,
             "desc": "75秒720p · ¥2.25/秒", "popular": True},
            {"id": "pro",      "name": "专业包",  "amount": 499, "credits": 900,
             "desc": "250秒720p · ¥2.00/秒", "popular": False},
        ]

    return {
        "currency": cur,
        "symbol": sym,
        "packages": [
            {**p, "display": f"{sym}{p['amount']}",
             "credits_display": f"{p['credits']} pts"}
            for p in packages
        ],
        "note": "" if CREEM_API_KEY else ("支付功能即将上线" if not settings.is_intl else "Payment coming soon"),
        "payment_provider": "creem",
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
    """测试充值（仅开发期，生产可关闭）"""
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
    """创建 Creem Checkout Session"""
    if not settings.is_intl:
        raise HTTPException(status_code=501, detail="Payment only available in international region")

    user_id = _verify_token(request)
    pkg = CREEM_PRODUCTS.get(req.package_id)
    if not pkg:
        raise HTTPException(status_code=400, detail=f"Unknown package: {req.package_id}")
    if not pkg["product_id"]:
        raise HTTPException(status_code=500,
            detail=f"Creem product_id not configured for '{req.package_id}'. Set CREEM_PRODUCT_{req.package_id.upper()}")

    if not CREEM_API_KEY:
        raise HTTPException(status_code=500, detail="Creem not configured")

    # Get user info for customer.email
    user = await store.get_user_by_id(user_id)
    user_email = user.get("email", "") if user else ""

    success_url = req.success_url or f"{BASE_URL}/"
    cancel_url = req.cancel_url or f"{BASE_URL}/"

    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.post(
                f"{CREEM_BASE}/v1/checkouts",
                headers={
                    "x-api-key": CREEM_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "product_id": pkg["product_id"],
                    "request_id": str(uuid.uuid4()),
                    "units": 1,
                    "customer": {
                        "email": user_email,
                    },
                    "success_url": success_url,
                    "metadata": {
                        "user_id": user_id,
                        "package_id": req.package_id,
                        "credits": str(pkg["credits"]),
                    },
                },
            )
            # Creem returns 303 redirect to checkout page
            if resp.status_code in (200, 201, 303):
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                checkout_url = data.get("checkout_url") or data.get("url") or str(resp.url)
                return {"success": True, "url": checkout_url}
            else:
                body = resp.text[:300]
                logger.error(f"[CREEM CHECKOUT] {resp.status_code}: {body}")
                raise HTTPException(status_code=502, detail=f"Creem error: {resp.status_code}")
    except httpx.HTTPError as e:
        logger.error(f"[CREEM CHECKOUT] HTTP error: {e}")
        raise HTTPException(status_code=502, detail="Creem checkout creation failed")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CREEM CHECKOUT] Error: {e}")
        raise HTTPException(status_code=500, detail="Creem checkout creation failed")


@router.post("/creem/webhook")
async def creem_webhook(request: Request):
    """Creem Webhook：接收 checkout.completed 事件，自动充值"""
    if not CREEM_API_KEY or not CREEM_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Creem webhook not configured")

    payload = await request.body()
    sig_header = request.headers.get("creem-signature", "")

    # Verify HMAC-SHA256 signature (strip "sha256=" prefix if present)
    if sig_header.startswith("sha256="):
        sig_value = sig_header[7:]
    else:
        sig_value = sig_header

    expected = hmac.new(
        CREEM_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, sig_value):
        logger.warning("[CREEM WEBHOOK] Invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        import json
        event = json.loads(payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = event.get("type") or event.get("event") or ""
    logger.info(f"[CREEM WEBHOOK] Event: {event_type}")

    # Handle checkout completed → top up user balance
    if event_type == "checkout.completed":
        # Creem event structure: data.object.metadata
        obj = event.get("data", {}).get("object", event.get("data", {}))
        meta = obj.get("metadata") or {}
        user_id = meta.get("user_id")
        package_id = meta.get("package_id", "unknown")

        if user_id:
            # Determine credits from package
            pkg = CREEM_PRODUCTS.get(package_id, {})
            credits = pkg.get("credits", 0)
            # Creem uses minor units (cents); 1 credit ≈ 0.15 USD
            # Map package credits to subunit: starter=50pt=$7=700c, standard=200pt=$18=1800c, pro=800pt=$52=5200c
            amount_subunit = {
                "starter": 700, "standard": 1800, "pro": 5200
            }.get(package_id, int(credits * 14))  # fallback ~14 cents/credit

            note = f"Creem: {package_id}"
            try:
                await store.topup_balance(user_id, amount_subunit, tx_type="topup", note=note)
                logger.info(f"[CREEM WEBHOOK] ✅ Topped up {user_id}: +{amount_subunit} cents for {package_id}")
            except Exception:
                import traceback
                logger.error(f"[CREEM WEBHOOK] topup failed: {traceback.format_exc()}")
                raise HTTPException(status_code=500, detail="Topup failed")

    return {"status": "ok"}


@router.post("/wechat/webhook")
async def wechat_webhook(request: Request):
    """微信支付回调（占位）"""
    raise HTTPException(
        status_code=501,
        detail="WeChat Pay webhook not yet implemented."
    )
