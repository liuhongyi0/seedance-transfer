"""
ComfyUI 节点对接路由
POST /api/wizard/analyze     → 分析图片 + 创作想法 → 返回结构化 Prompt 建议
POST /api/wizard/preview      → 根据参数生成 Flux 预览图
POST /api/video/generate      → 提交视频生成任务
GET  /api/video/{id}/status   → 查询任务状态
GET  /api/video/{id}/result   → 获取结果
GET  /api/balance              → 查询余额
POST /api/estimate             → 预估费用
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional
import httpx
import uuid
import asyncio
import json as _json

from config import settings
from store import store
from services.billing import require_user, charge, calculate_cost
from services.moderation import screen_prompt
from log_config import get_logger

logger = get_logger(__name__)

router = APIRouter()

# ─── Descriptions ───────────────────────────────────────────────────────────────

DESCRIBE_SYSTEM = """You are a professional cinematographer and AI film director. Analyze the provided image and return a JSON object with these fields:
- style: overall visual style (e.g., "cinematic", "anime", "realistic", "surreal")
- mood: emotional atmosphere (e.g., "dreamy", "dramatic", "peaceful", "mysterious")
- color_palette: dominant colors and lighting (e.g., "warm golden hour, soft shadows")
- camera: suggested camera movement (e.g., "slow pan right", "static", "dolly in")
- prompt_en: a detailed English video generation prompt (2-3 sentences) combining the user's idea with the image analysis
- prompt_cn: same prompt in Chinese

Return ONLY valid JSON, no other text."""


# ─── Request Models ─────────────────────────────────────────────────────────────

class WizardAnalyzeRequest(BaseModel):
    image_url: str = ""
    image_b64: Optional[str] = None
    idea_text: str = ""
    aspect_ratio: str = "16:9"
    language: str = "zh"

    def get_image_url(self) -> str:
        """Resolve image URL: prefer upload URL, fallback to base64 data URI."""
        if self.image_url:
            return self.image_url
        if self.image_b64:
            b64 = self.image_b64
            if b64.startswith("data:"):
                return b64
            return f"data:image/png;base64,{b64}"
        return ""


class WizardPreviewRequest(BaseModel):
    style: str = "cinematic"
    mood: str = "peaceful"
    color_palette: str = "warm natural"
    camera: str = "static"
    prompt_en: str
    aspect_ratio: str = "16:9"


class VideoGenerateRequest(BaseModel):
    prompt_en: str
    aspect_ratio: str = "16:9"
    duration: int = Field(5, ge=5, le=15, description="Duration in seconds (5-15)")
    resolution: str = "720p"
    image_url: Optional[str] = None
    image_b64: Optional[str] = None
    model_key: Optional[str] = None

    def get_image_url(self) -> Optional[str]:
        """Resolve reference image URL."""
        if self.image_url:
            return self.image_url
        if self.image_b64:
            b64 = self.image_b64
            if b64.startswith("data:"):
                return b64
            return f"data:image/png;base64,{b64}"
        return None


# ─── Wizard Endpoints ───────────────────────────────────────────────────────────

@router.post("/wizard/analyze")
async def wizard_analyze(req: WizardAnalyzeRequest, request: Request):
    user_id = await require_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    image_url = req.get_image_url()
    if not image_url:
        raise HTTPException(status_code=400, detail="image_url or image_b64 required")

    if not settings.VOLC_API_KEY:
        return {
            "success": True,
            "style": "cinematic",
            "mood": "dramatic",
            "color_palette": "warm golden tones, soft shadows",
            "camera": "slow pan right",
            "prompt_en": "A cinematic scene with dramatic lighting, smooth camera movement, rich colors and detailed textures.",
            "prompt_cn": "电影质感场景，戏剧性光影，流畅运镜，丰富色彩与细腻质感。",
            "note": "Mock (no VOLC_API_KEY configured)"
        }

    # Content moderation
    if req.idea_text:
        await screen_prompt(req.idea_text, f"wizard/analyze:{user_id}")

    http = request.app.state.http_client
    try:
        resp = await http.post(
            f"{settings.VOLC_BASE_URL}/chat/completions"
            headers={
                "Authorization": f"Bearer {settings.VOLC_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": settings.VOLC_VISION_MODEL,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_url}},
                        {"type": "text", "text": DESCRIBE_SYSTEM +
                         (f"\n\nUser's creative idea: {req.idea_text}" if req.idea_text else "")}
                    ]
                }],
                "max_tokens": 500,
                "temperature": 0.7
            },
            timeout=60.0
        )
        resp.raise_for_status()
        data = resp.json()
        choices = (data or {}).get("choices", [])
        if not choices:
            return {"success": False, "note": "Vision model returned empty response"}
        raw = (choices[0].get("message", {}).get("content", "") or "").strip()

        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]

        if len(raw) > 10_000:
            logger.info(f"[wizard/analyze] LLM response too large ({len(raw)} chars), truncating")
            raw = raw[:10_000]

        result = _json.loads(raw)
        return {"success": True, **result}
    except (httpx.HTTPStatusError, _json.JSONDecodeError) as e:
        return {
            "success": True,
            "style": "cinematic",
            "mood": "dramatic",
            "color_palette": "natural tones",
            "camera": "static",
            "prompt_en": "A beautifully composed cinematic video scene with rich detail.",
            "prompt_cn": "精致构图的电影感视频画面，细节丰富。",
            "note": f"Fallback (vision model error: {str(e)[:100]})"
        }


@router.post("/wizard/preview")
async def wizard_preview(req: WizardPreviewRequest, request: Request):
    user_id = await require_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    cost = calculate_cost("image", count=1)
    balance = await charge(user_id, "image", cost, f"wizard_preview:{req.prompt_en[:50]}")
    if balance is None:
        raise HTTPException(status_code=402, detail="Insufficient balance")

    # Content moderation
    await screen_prompt(req.prompt_en, f"wizard/preview:{user_id}")

    if not settings.EVOLINK_API_KEY:
        return {"success": True, "preview_url": "", "note": "Mock (no EVOLINK_API_KEY)"}

    http = request.app.state.http_client
    try:
        resp = await http.post(
            f"{settings.EVOLINK_BASE_URL}/images/generations",
            headers={
                "Authorization": f"Bearer {settings.EVOLINK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={"model": "doubao-seedream-4.5", "prompt": req.prompt_en,
                  "size": "1024x576", "n": 1},
            timeout=30.0
        )
        if resp.status_code == 200:
            evo_data = resp.json()
            evo_tid = evo_data.get("id")
            if evo_tid:
                for _ in range(20):
                    await asyncio.sleep(2)
                    pr = await http.get(
                        f"{settings.EVOLINK_BASE_URL}/tasks/{evo_tid}",
                        headers={"Authorization": f"Bearer {settings.EVOLINK_API_KEY}"},
                        timeout=15.0
                    )
                    if pr.status_code == 200:
                        pd = pr.json()
                        if pd.get("status") == "succeeded":
                            img_url = pd.get("output", {}).get("results", [None])[0]
                            if img_url:
                                return {"success": True, "preview_url": img_url}
                        elif pd.get("status") == "failed":
                            break
    except Exception as e:
        logger.error(f"[wizard/preview] Error: {e}")

    return {"success": True, "preview_url": "", "note": "Preview generation pending"}


# ─── Video Endpoints ────────────────────────────────────────────────────────────

@router.post("/video/generate")
async def video_generate(req: VideoGenerateRequest, request: Request):
    user_id = await require_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    from services.model_catalog import VIDEO_DRAFT, get_provider

    cost = calculate_cost("video_draft", model_key=req.model_key,
                          duration=req.duration, resolution=req.resolution)
    balance = await charge(user_id, "video_draft", cost,
                           f"video_generate:{req.prompt_en[:50]}")
    if balance is None:
        raise HTTPException(status_code=402, detail="Insufficient balance")

    task_id = f"sd-{uuid.uuid4().hex[:8]}"
    provider = get_provider(VIDEO_DRAFT, req.model_key)

    # Check required API key for the provider
    if provider == "volcengine" and not settings.VOLC_API_KEY:
        return {"success": True, "task_id": task_id, "status": "processing",
                "note": f"Mock mode (no VOLC_API_KEY)"}
    if provider != "volcengine" and not settings.EVOLINK_API_KEY:
        return {"success": True, "task_id": task_id, "status": "processing",
                "note": "Mock mode (no EVOLINK_API_KEY)"}

    http = request.app.state.http_client
    try:
        # Content moderation
    await screen_prompt(req.prompt_en, f"video/generate:{user_id}")

    from services.video_provider import submit_video

        result = await submit_video(
            http,
            prompt=req.prompt_en,
            model_key=req.model_key,
            duration=req.duration,
            resolution=req.resolution,
            aspect_ratio=req.aspect_ratio,
            image_url=req.get_image_url(),
        )
        remote_id = result.get("remote_id", "")
        if remote_id:
            await store.save_video_task(task_id, user_id, remote_id,
                                        provider=result.get("provider"))
            return {"success": True, "task_id": task_id, "status": "processing",
                    "provider": result.get("provider")}
    except Exception as e:
        logger.error(f"[video/generate] Error: {e}")

    return {"success": True, "task_id": task_id, "status": "processing",
            "note": f"{provider} submit skipped"}


@router.get("/video/{task_id}/status")
async def video_status(task_id: str, request: Request):
    await require_user(request)
    task = await store.get_video_task(task_id)
    if not task:
        return {"task_id": task_id, "status": "not_found"}

    remote_id = task.get("evo_task_id", "")
    provider = task.get("provider", "evolink")
    if not remote_id:
        return {"task_id": task_id, "status": "processing", "progress": 50}

    http = request.app.state.http_client
    try:
        from services.video_provider import poll_video
        result = await poll_video(http, remote_id=remote_id, max_attempts=1)
        status = result.get("status", "processing")
        video_url = result.get("video_url", "")

        progress = 100 if status == "succeeded" else (50 if status == "failed" else 30)
        return {
            "task_id": task_id,
            "status": status,
            "progress": progress,
            "video_url": video_url,
            "provider": provider,
        }
    except Exception as e:
        logger.error(f"[video/status] Error: {e}")

    return {"task_id": task_id, "status": "processing", "progress": 20,
            "provider": provider}


@router.get("/video/{task_id}/result")
async def video_result(task_id: str, request: Request):
    await require_user(request)
    task = await store.get_video_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    remote_id = task.get("evo_task_id", "")
    video_url = ""
    if remote_id:
        http = request.app.state.http_client
        try:
            from services.video_provider import poll_video

            result = await poll_video(http, remote_id=remote_id, max_attempts=1)
            if result.get("status") == "succeeded":
                video_url = result.get("video_url", "")
        except Exception:
            logger.error(f"[wizard] Video poll failed for task {task_id} (non-fatal)")
            pass  # poll failure is non-fatal in a multi-source status check

    return {
        "task_id": task_id,
        "status": "succeeded" if video_url else "processing",
        "video_url": video_url,
    }


# ─── Balance & Estimate ─────────────────────────────────────────────────────────

@router.get("/balance")
async def get_balance(request: Request):
    user_id = await require_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = await store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "success": True,
        "balance_subunit": user["balance_subunit"],
        "balance_yuan": round(user["balance_subunit"] / 100, 2),
        "balance_usd": round(user["balance_subunit"] / 100 / 7.2, 2),
        "currency": user.get("currency", "USD"),
    }


@router.post("/estimate")
async def estimate(req: VideoGenerateRequest):
    vcost = calculate_cost("video_draft", model_key=req.model_key,
                           duration=req.duration, resolution=req.resolution)
    icost = calculate_cost("image", count=1)
    return {
        "success": True,
        "video_cost_subunit": vcost,
        "preview_cost_subunit": icost,
        "total_subunit": vcost + icost,
    }
