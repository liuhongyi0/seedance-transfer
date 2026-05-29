"""
模型选择路由
GET /api/models?step=image|video_draft|music|final_video → 可用模型列表（含定价）
"""

from fastapi import APIRouter, HTTPException
from config import settings
from services.model_catalog import IMAGE, VIDEO_DRAFT, MUSIC, FINAL_VIDEO, get_models

router = APIRouter()

VALID_STEPS = {IMAGE, VIDEO_DRAFT, MUSIC, FINAL_VIDEO}


@router.get("")
async def list_models(step: str = ""):
    """返回指定步骤的可用模型列表，含中英文名、定价、标签"""
    if step not in VALID_STEPS:
        detail = f"Invalid step '{step}'. Valid: {', '.join(sorted(VALID_STEPS))}"
        raise HTTPException(status_code=400, detail=detail)

    models_raw = get_models(step)
    sym = settings.currency_symbol
    is_intl = settings.is_intl

    models = []
    for m in models_raw:
        # Flat price: use explicit field, or derive from per-sec 720p × 5s baseline
        if "price_intl" in m:
            price_subunit = m["price_intl"] if is_intl else m["price_cn"]
        else:
            per_sec_map = m.get("price_per_sec_intl" if is_intl else "price_per_sec_cn", {})
            per_sec = per_sec_map.get("720p", 0)
            price_subunit = per_sec * 5  # 5s baseline for display

        price_display = price_subunit / 100.0
        entry = {
            "key": m["key"],
            "display_name": m["display_cn"],
            "display_name_en": m["display_en"],
            "price": round(price_display, 2),
            "price_subunit": price_subunit,
            "price_display": f"{sym}{price_display:.2f}",
            "is_default": m.get("default", False),
            "tags": m.get("tags", []),
            "provider": m.get("provider", "evolink"),
        }
        if step == VIDEO_DRAFT:
            per_sec_map = m.get("price_per_sec_intl" if is_intl else "price_per_sec_cn", {})
            entry["price_per_sec"] = {k: v / 100.0 for k, v in per_sec_map.items()}
        models.append(entry)

    return {
        "step": step,
        "currency": settings.currency,
        "symbol": sym,
        "models": models,
    }
