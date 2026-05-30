"""
步骤三：视频草稿生成路由
POST /api/video-draft/generate  → 调用 EvoLink Seedance Fast 480p×5s
GET  /api/video-draft/task/{id} → 轮询任务状态
POST /api/video-draft/save      → 保存完成的草稿到素材盘
"""

import traceback
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Literal
import httpx
import asyncio

from config import settings
from store import store
from services.color_to_prompt import color_params_to_prompt
from services.billing import calculate_cost, charge, refund, require_user
from log_config import get_logger

logger = get_logger(__name__)

router = APIRouter()


async def rehost_image(image_url: str, http: httpx.AsyncClient) -> str:
    """
    把私有/受限图片 URL 转成 R2 公网 URL。
    未配置存储后端则原样返回（降级）。
    """
    try:
        from services.storage import upload_from_url
        return await upload_from_url(http, image_url, prefix="rehost")
    except RuntimeError:
        # 无存储后端，原样返回
        return image_url
    except Exception as e:
        logger.warning(f"⚠️ rehost 上传失败，使用原始 URL: {e}")
        return image_url


class VideoDraftGenRequest(BaseModel):
    session_id: str
    reference_image_id: Optional[str] = None
    reference_image_url: Optional[str] = None
    prompt_en: str
    resolution: Literal["480p"] = "480p"
    duration: Literal[5] = 5
    model_key: Optional[str] = None

class VideoDraftSaveRequest(BaseModel):
    session_id: str
    task_id: str
    video_url: str
    thumbnail_url: str = ""
    prompt_en: str = ""


@router.post("/generate")
async def generate_video_draft(req: VideoDraftGenRequest, request: Request):
    """
    生成视频草稿（480p × 5s，EvoLink Fast，约¥2.7/个）

    流程：
    1. 从素材盘取参考图URL
    2. 若有调色参数，注入到Prompt末尾
    3. 提交到 EvoLink Seedance 2.0 Fast → 轮询直到完成
    4. 返回 video_url
    """
    try:
        s = await store.require(req.session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    user_id = await require_user(request)
    cost_subunit = calculate_cost("video_draft", model_key=req.model_key,
                                  duration=req.duration, resolution=req.resolution)
    if user_id:
        user = await store.get_user_by_id(user_id)
        balance = user.get("balance_subunit", 0) if user else 0
        if balance < cost_subunit:
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient balance. Need {cost_subunit} {settings.currency_subunit}, have {balance}."
            )
        await charge(user_id, "video_draft", cost_subunit, f"480p 5s draft")

    ref_url = req.reference_image_url
    if not ref_url and req.reference_image_id:
        ref_url = await store.get_image_url(req.session_id, req.reference_image_id)

    full_prompt = req.prompt_en
    if req.reference_image_id:
        for img in s["assets"]["images"]:
            if img["id"] == req.reference_image_id and img.get("color_params"):
                color_addon = color_params_to_prompt(img["color_params"])
                if color_addon:
                    full_prompt = f"{full_prompt}, {color_addon}"
                break

    cost_val = cost_subunit / 100.0
    task_id = await store.create_task(req.session_id, "video_draft", {
        "prompt_en": full_prompt,
        "ref_url": ref_url,
        "resolution": req.resolution,
        "duration": req.duration,
        "estimated_cost_val": cost_val
    })

    from services.model_catalog import VIDEO_DRAFT, get_provider
    provider = get_provider(VIDEO_DRAFT, req.model_key)

    api_key_missing = (provider == "volcengine" and not settings.VOLC_API_KEY) or \
                      (provider != "volcengine" and not settings.EVOLINK_API_KEY)
    if api_key_missing:
        mock_url = "https://sample-videos.com/video321/mp4/240/big_buck_bunny_240p_5mb.mp4"
        await store.update_task(req.session_id, task_id,
                          status="completed", progress=100,
                          result_url=mock_url,
                          meta={"video_url": mock_url, "thumbnail_url": "",
                                "prompt_en": full_prompt, "cost_val": 0})
        return {
            "success": True,
            "task_id": task_id,
            "status": "completed",
            "video_url": mock_url,
            "cost_val": 0,
            "currency": settings.currency,
            "note": f"Mock模式（未配置{provider.upper()}_API_KEY）"
        }

    http = request.app.state.http_client
    URL_ERR_KWS = ["URL", "url", "accessibility", "Image processing", "network", "image host"]

    try:
        await store.update_task(req.session_id, task_id, status="processing", progress=5)

        # Rehost for EvoLink (can't access private URLs); Volcengine handles it natively
        public_ref_url = ref_url
        if ref_url and provider != "volcengine":
            public_ref_url = await rehost_image(ref_url, http)
            logger.info(f"🖼️ 参考图中转: {ref_url[:60]}... → {public_ref_url[:60]}...")

        from services.video_provider import submit_video, poll_video

        # Submit to provider → return immediately, poll in background
        submit_result = await submit_video(
            http, prompt=full_prompt, model_key=req.model_key,
            duration=req.duration, resolution=req.resolution,
            image_url=public_ref_url if public_ref_url else None,
        )
        remote_id = submit_result.get("remote_id", "")
        if not remote_id:
            raise HTTPException(status_code=502, detail=f"{provider}未返回task_id")

        await store.update_task(req.session_id, task_id, status="processing", progress=5,
                          meta={"remote_id": remote_id, "provider": provider,
                                "prompt_en": full_prompt, "ref_url": ref_url})

        # Background polling — doesn't block the response
        async def _background_poll():
            note_bg = ""
            try:
                for i in range(settings.MAX_POLL_DRAFT):
                    await asyncio.sleep(settings.POLL_INTERVAL)
                    pct = min(10 + (i / settings.MAX_POLL_DRAFT) * 90, 99)
                    await store.update_task(req.session_id, task_id, status="processing",
                                      progress=pct)
                    result = await poll_video(http, remote_id=remote_id, provider=provider, max_attempts=1)
                    st = result.get("status", "processing")
                    if st == "succeeded":
                        vurl = result.get("video_url", "")
                        logger.info(f"✅ 视频生成完成 ({provider}): {vurl}")
                        await store.update_task(req.session_id, task_id,
                                          status="completed", progress=100,
                                          result_url=vurl,
                                          meta={"video_url": vurl, "remote_id": remote_id,
                                                "prompt_en": full_prompt, "provider": provider,
                                                "note": note_bg})
                        return
                    if st == "failed":
                        msg = result.get("error", "生成失败")
                        # Try fallback without ref image on URL errors
                        if public_ref_url and any(k in str(msg) for k in URL_ERR_KWS):
                            note_bg = "⚠️ 参考图URL不可公开访问，已自动降级为纯提示词生成"
                            logger.warning(f"⚠️ 降级重试（无参考图）原因: {msg}")
                            fb = await submit_video(
                                http, prompt=full_prompt, model_key=req.model_key,
                                duration=req.duration, resolution=req.resolution,
                                image_url=None,
                            )
                            remote_id2 = fb.get("remote_id", "")
                            if remote_id2:
                                # Re-poll with new remote_id, simpler loop
                                for j in range(settings.MAX_POLL_DRAFT):
                                    await asyncio.sleep(settings.POLL_INTERVAL)
                                    pct2 = min(10 + (j / settings.MAX_POLL_DRAFT) * 90, 99)
                                    await store.update_task(req.session_id, task_id,
                                                      status="processing", progress=pct2,
                                                      meta={"remote_id": remote_id2, "provider": provider,
                                                            "note": note_bg})
                                    r2 = await poll_video(http, remote_id=remote_id2, provider=provider, max_attempts=1)
                                    if r2.get("status") == "succeeded":
                                        vurl2 = r2.get("video_url", "")
                                        await store.update_task(req.session_id, task_id,
                                                          status="completed", progress=100,
                                                          result_url=vurl2,
                                                          meta={"video_url": vurl2, "remote_id": remote_id2,
                                                                "prompt_en": full_prompt, "provider": provider,
                                                                "note": note_bg})
                                        return
                                    if r2.get("status") == "failed":
                                        break
                        await store.update_task(req.session_id, task_id, status="failed", error=str(msg))
                        return
                await store.update_task(req.session_id, task_id, status="failed",
                                  error=f"轮询超时（{settings.MAX_POLL_DRAFT * settings.POLL_INTERVAL}s）")
            except Exception as e:
                logger.error(f"❌ 后台轮询异常: {e}")
                traceback.print_exc()
                await store.update_task(req.session_id, task_id, status="failed", error=str(e)[:200])

        asyncio.create_task(_background_poll())

        return {
            "success": True,
            "task_id": task_id,
            "status": "processing",
            "cost_val": cost_val,
            "currency": settings.currency,
            "note": "任务已提交，请轮询 /api/video-draft/task/{task_id}?session_id=xxx"
        }

    except HTTPException:
        if user_id and cost_subunit:
            await refund(user_id, "video_draft", cost_subunit, "task failed")
        raise
    except httpx.HTTPStatusError as e:
        if user_id and cost_subunit:
            await refund(user_id, "video_draft", cost_subunit, "EvoLink API error")
        detail = f"EvoLink API错误({e.response.status_code})"
        try:
            body = e.response.json()
            err_obj = body.get("error", {})
            if isinstance(err_obj, dict):
                detail += f": {err_obj.get('message', e.response.text[:200])}"
            else:
                detail += f": {err_obj or e.response.text[:200]}"
        except Exception:
            detail += f": {e.response.text[:200]}"
        logger.error(f"❌ HTTPStatusError: {detail}")
        await store.update_task(req.session_id, task_id, status="failed", error=detail)
        raise HTTPException(status_code=502, detail=detail) from e
    except Exception as e:
        if user_id and cost_subunit:
            await refund(user_id, "video_draft", cost_subunit, str(e)[:80])
        logger.error(f"❌ 未预期异常: {str(e)}")
        traceback.print_exc()
        await store.update_task(req.session_id, task_id, status="failed", error=str(e)[:200])
        raise HTTPException(status_code=500, detail="Video draft generation failed due to an internal error") from e


@router.get("/task/{task_id}")
async def poll_video_draft(task_id: str, session_id: str, request: Request):
    """
    轮询视频草稿任务状态
    前端每3秒调用一次，直到 status=completed 或 failed
    """
    task = await store.get_task(session_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # Already terminal? Return immediately
    if task["status"] in ("completed", "failed"):
        return {
            "task_id": task_id,
            "status": task["status"],
            "progress": task.get("progress", 100),
            "video_url": task.get("result_url"),
            "error": task.get("error")
        }

    # Background poller is running — just return current stored status
    return {
        "task_id": task_id,
        "status": task.get("status", "processing"),
        "progress": task.get("progress", 10),
        "video_url": task.get("result_url"),
    }


@router.post("/save")
async def save_video_draft(req: VideoDraftSaveRequest):
    """将完成的视频草稿保存到素材盘"""
    vid_id = await store.add_video(
        session_id=req.session_id,
        url=req.video_url,
        thumbnail=req.thumbnail_url,
        duration=5,
        prompt=req.prompt_en
    )
    return {"success": True, "video_id": vid_id}
