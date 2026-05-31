"""
模型选择路由
GET /api/models?step=image|video_draft|music|final_video → 可用模型列表（含信用点消耗）"""
from fastapi import APIRouter, HTTPException
from config import settings
from services.model_catalog import (IMAGE, VIDEO_DRAFT, MUSIC, FINAL_VIDEO, get_models,
                                     get_credits, get_credits_per_sec)

router = APIRouter()
VALID_STEPS = {IMAGE, VIDEO_DRAFT, MUSIC, FINAL_VIDEO}

@router.get("")
async def list_models(step: str = ""):
    if step not in VALID_STEPS:
        detail = f"Invalid step '{step}'. Valid: {', '.join(sorted(VALID_STEPS))}"
        raise HTTPException(status_code=400, detail=detail)

    models_raw = get_models(step)
    is_intl = settings.is_intl

    models = []
    for m in models_raw:
        key = m["key"]
        entry = {
            "key": key,
            "display_name": m["display_cn"],
            "display_name_en": m["display_en"],
            "is_default": m.get("default", False),
            "tags": m.get("tags", []),
            "provider": m.get("provider", "evolink"),
        }
        if step in (IMAGE, MUSIC):
            entry["credits"] = m.get("credits", 1 if step == IMAGE else 2)
        elif step == VIDEO_DRAFT:
            entry["credits_per_sec"] = m.get("credits_per_sec", 1)
        elif step == FINAL_VIDEO:
            cps = m.get("credits_per_sec", {"720p": 2, "1080p": 3})
            entry["credits_per_sec"] = cps

        models.append(entry)

    return {"step": step, "models": models}
