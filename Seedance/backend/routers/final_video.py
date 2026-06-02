"""
步骤五：最终成片生成路由（火山引擎官方 Seedance 2.0）
POST /api/final-video/generate  → 提交高清成片任务
GET  /api/final-video/task/{id} → 轮询状态
GET  /api/final-video/cost      → 预估成本
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, Literal, List
import httpx
import asyncio
import time
import traceback

from config import settings
from store import store
from services.billing import calculate_cost, charge, refund, require_user
from services.storage import upload_bytes

from log_config import get_logger
logger = get_logger(__name__)


router = APIRouter()


async def _rehost_to_r2(video_url: str) -> str:
    """
    把火山引擎中国 CDN 的视频下载后转存到 R2，
    让海外用户通过 Cloudflare 全球节点快速访问。
    转存失败时静默降级，返回原始 URL。
    """
    if not video_url:
        return video_url
    try:
        timeout = httpx.Timeout(connect=30.0, read=300.0, write=60.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(video_url, follow_redirects=True)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "video/mp4")
            r2_url = await upload_bytes(resp.content, content_type, prefix="final")
            logger.info(f"[rehost] 视频转存 R2 成功: {r2_url}")
            return r2_url
    except Exception as e:
        logger.info(f"[rehost] 视频转存 R2 失败，降级使用原始 URL: {e}")
        return video_url


def _cost_table():
    p = settings.cost_final_per_sec
    return {
        "720p":  {d: round(p["720p"] * d / 100, 2) for d in [5, 6, 8, 10, 12, 15]},
        "1080p": {d: round(p["1080p"] * d / 100, 2) for d in [5, 6, 8, 10, 12, 15]},
        "2k":    {d: round(p["2k"] * d / 100, 2) for d in [5, 6, 8, 10, 12, 15]},
    }

def _cost(resolution: str, duration: int) -> float:
    return round(settings.cost_final_per_sec.get(resolution, 0) * duration / 100, 2)

# 火山引擎 Seedance 2.0 真实 API 端点
VOLC_TASK_URL = "/contents/generations/tasks"


class FinalVideoRequest(BaseModel):
    session_id: str
    prompt_en: str                                    # 英文Prompt文本
    reference_image_ids: List[str] = []               # 参考图（素材盘ID列表，最多2张）
    reference_image_urls: List[str] = []              # 或直接传URL
    video_draft_id: Optional[str] = None              # 运镜参考视频
    video_draft_url: Optional[str] = None             # 或直接传URL
    music_id: Optional[str] = None                    # 背景音乐
    music_url: Optional[str] = None                   # 或直接传URL
    resolution: Literal["720p", "1080p", "2k"] = "1080p"
    duration: int = Field(12, ge=5, le=15, description="Duration in seconds (5-15)")
    ratio: Literal["16:9", "9:16", "1:1", "4:3"] = "16:9"
    generate_audio: bool = True
    watermark: bool = False


@router.get("/cost")
async def estimate_cost(resolution: str = "1080p", duration: int = 12):
    """预估最终成片成本"""
    cost = _cost_table().get(resolution, {}).get(duration, 0)
    per_sec_subunit = settings.cost_final_per_sec.get(resolution, 0)
    per_sec = per_sec_subunit / 100
    sym = settings.currency_symbol
    return {
        "resolution": resolution,
        "duration": duration,
        "cost": cost,
        "cost_per_sec": per_sec,
        "currency": settings.currency,
        "formula": f"{sym}{per_sec}/s × {duration}s = {sym}{cost}"
    }


@router.post("/generate")
async def generate_final_video(req: FinalVideoRequest, request: Request):
    """
    提交最终成片任务（火山引擎 Seedance 2.0 官方API）

    使用 multimodal content[] 格式，支持：
    - text: Prompt文本
    - image_url (role=reference_image): 参考图（首帧/尾帧）
    - video_url (role=reference_video): 运镜参考草稿
    - audio_url (role=reference_audio): 背景音乐
    """
    try:
        s = await store.require(req.session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    user_id = await require_user(request)
    cost_subunit = calculate_cost("final_video", resolution=req.resolution, duration=req.duration)
    if user_id:
        user = await store.get_user_by_id(user_id)
        balance = user.get("balance_subunit", 0) if user else 0
        if balance < cost_subunit:
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient balance. Need {cost_subunit} {settings.currency_subunit}, have {balance}."
            )
        await charge(user_id, "final_video", cost_subunit,
                     f"{req.resolution} {req.duration}s")

    # 收集参考图URL
    image_urls = list(req.reference_image_urls)
    for img_id in req.reference_image_ids:
        url = await store.get_image_url(req.session_id, img_id)
        if url:
            image_urls.append(url)

    # 收集视频草稿URL
    draft_url = req.video_draft_url
    if not draft_url and req.video_draft_id:
        for vid in s["assets"]["videos"]:
            if vid["id"] == req.video_draft_id:
                draft_url = vid["url"]
                break

    # 收集音乐URL
    music_url = req.music_url
    if not music_url and req.music_id:
        for mus in s["assets"]["musics"]:
            if mus["id"] == req.music_id:
                music_url = mus["url"]
                break

    # 预估成本
    cost_val = _cost(req.resolution, req.duration)

    # 构建 multimodal content[] 数组（火山引擎 Seedance 2.0 真实格式）
    content: list = []

    if req.prompt_en:
        content.append({"type": "text", "text": req.prompt_en})

    for url in image_urls[:2]:  # 最多2张参考图
        content.append({
            "type": "image_url",
            "image_url": {"url": url},
            "role": "reference_image"
        })

    if draft_url:
        content.append({
            "type": "video_url",
            "video_url": {"url": draft_url},
            "role": "reference_video"
        })

    if music_url:
        content.append({
            "type": "audio_url",
            "audio_url": {"url": music_url},
            "role": "reference_audio"
        })

    if not content:
        raise HTTPException(status_code=400, detail="至少需要提供 prompt_en 或 reference_image")

    task_id = await store.create_task(req.session_id, "final_video", {
        "prompt_en": req.prompt_en,
        "resolution": req.resolution,
        "duration": req.duration,
        "ratio": req.ratio,
        "image_urls": image_urls,
        "draft_url": draft_url,
        "music_url": music_url,
        "estimated_cost_val": cost_val
    })

    if not settings.VOLC_API_KEY or settings.VOLC_API_KEY.startswith("your_"):
        mock_url = "https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_10mb.mp4"
        await store.update_task(req.session_id, task_id,
                          status="completed", progress=100,
                          result_url=mock_url,
                          meta={"video_url": mock_url, "cost_val": cost_val})
        return {
            "success": True,
            "task_id": task_id,
            "status": "completed",
            "video_url": mock_url,
            "cost_val": cost_val,
            "currency": settings.currency,
            "note": "⚠️ Mock模式（未配置VOLC_API_KEY）"
        }

    http = request.app.state.http_client
    try:
        await store.update_task(req.session_id, task_id, status="processing", progress=3)

        payload = {
            "model": settings.VOLC_MODEL,
            "content": content,
            "generate_audio": req.generate_audio,
            "ratio": req.ratio,
            "duration": req.duration,
            "watermark": req.watermark,
        }

        resp = await http.post(
            f"{settings.VOLC_BASE_URL}{VOLC_TASK_URL}",
            headers={
                "Authorization": f"Bearer {settings.VOLC_API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=60.0
        )
        resp.raise_for_status()
        data = resp.json()

        volc_task_id = data.get("id") or data.get("task_id")
        if not volc_task_id:
            raise HTTPException(status_code=502, detail=f"火山引擎未返回task_id: {str(data)[:200]}")

        await store.update_task(req.session_id, task_id, status="processing", progress=5,
                          meta={"volc_task_id": volc_task_id,
                                "prompt_en": req.prompt_en,
                                "cost_val": cost_val})

        # Background polling — doesn't block the response
        async def _background_poll():
            try:
                for i in range(settings.MAX_POLL_FINAL):
                    await asyncio.sleep(settings.POLL_INTERVAL)
                    try:
                        poll_resp = await http.get(
                            f"{settings.VOLC_BASE_URL}{VOLC_TASK_URL}/{volc_task_id}",
                            headers={"Authorization": f"Bearer {settings.VOLC_API_KEY}"},
                            timeout=30.0
                        )
                        poll_resp.raise_for_status()
                        poll_data = poll_resp.json()
                    except Exception as pe:
                        logger.info(f"[final poll] HTTP error: {pe}")
                        continue

                    pct = poll_data.get("progress", 0)
                    status = poll_data.get("status", "processing")
                    await store.update_task(req.session_id, task_id, status=status,
                                      progress=min(5 + pct * 0.95, 99))

                    if status in ("completed", "succeeded"):
                        video_url = poll_data.get("content", {}).get("video_url") or \
                                    poll_data.get("video_url") or \
                                    (poll_data.get("output") or [None])[0]
                        video_url = await _rehost_to_r2(video_url)
                        existing_task = await store.get_task(req.session_id, task_id)
                        await store.update_task(req.session_id, task_id,
                                          status="completed", progress=100,
                                          result_url=video_url,
                                          meta={**((existing_task or {}).get("meta") or {}),
                                                "final_cost_val": cost_val,
                                                "volc_task_id": volc_task_id})
                        return
                    elif status == "failed":
                        error_msg = poll_data.get("error", {}).get("message", "未知错误")
                        await store.update_task(req.session_id, task_id, status="failed", error=error_msg)
                        return

                await store.update_task(req.session_id, task_id, status="failed",
                                  error=f"轮询超时（{settings.MAX_POLL_FINAL * settings.POLL_INTERVAL}s）")
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
            "note": "任务已提交，请轮询 GET /api/final-video/task/{task_id}?session_id=xxx"
        }

    except httpx.HTTPStatusError as e:
        if user_id and cost_subunit:
            await refund(user_id, "final_video", cost_subunit, "API error")
        detail = f"火山引擎API错误({e.response.status_code})"
        try:
            body = e.response.json()
            detail += f": {body.get('error', {}).get('message', e.response.text[:200])}"
        except Exception:
            detail += f": {e.response.text[:200]}"
        await store.update_task(req.session_id, task_id, status="failed", error=detail)
        raise HTTPException(status_code=502, detail=detail)
    except HTTPException:
        if user_id and cost_subunit:
            await refund(user_id, "final_video", cost_subunit, "task failed")
        raise
    except Exception as e:
        if user_id and cost_subunit:
            await refund(user_id, "final_video", cost_subunit, str(e)[:80])
        await store.update_task(req.session_id, task_id, status="failed", error=str(e)[:200])
        raise HTTPException(status_code=500, detail="Final video generation failed due to an internal error")

@router.get("/task/{task_id}")
async def poll_final_video(task_id: str, session_id: str, request: Request):
    """轮询最终成片任务状态"""
    task = await store.get_task(session_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if not settings.VOLC_API_KEY or settings.VOLC_API_KEY.startswith("your_") or \
       task["status"] in ("completed", "failed"):
        return {
            "task_id": task_id,
            "status": task["status"],
            "progress": task.get("progress", 100),
            "video_url": task.get("result_url"),
            "cost_val": task.get("meta", {}).get("cost_val", 0),
            "currency": settings.currency,
            "error": task.get("error")
        }

    volc_task_id = task.get("meta", {}).get("volc_task_id")
    if not volc_task_id:
        return {"task_id": task_id, "status": "processing", "progress": 5}

    http = request.app.state.http_client
    try:
        resp = await http.get(
            f"{settings.VOLC_BASE_URL}{VOLC_TASK_URL}/{volc_task_id}",
            headers={"Authorization": f"Bearer {settings.VOLC_API_KEY}"},
            timeout=15.0
        )
        resp.raise_for_status()
        data = resp.json()

        provider_status = data.get("status", "processing")
        video_url = None

        if provider_status in ("succeeded", "completed"):
            video_url = data.get("content", {}).get("video_url") or \
                        data.get("video_url") or \
                        (data.get("output") or [None])[0]
            # 转存到 R2，避免海外用户直接访问中国 CDN 速度慢
            video_url = await _rehost_to_r2(video_url)
            await store.update_task(session_id, task_id,
                              status="completed", progress=100,
                              result_url=video_url)
        elif provider_status == "failed":
            await store.update_task(session_id, task_id,
                              status="failed",
                              error=data.get("error", "成片生成失败"))
        else:
            elapsed = time.time() - task["created_at"]
            progress = min(90, int(elapsed / 300 * 85) + 5)
            await store.update_task(session_id, task_id, progress=progress)

        cur = await store.get_task(session_id, task_id)
        return {
            "task_id": task_id,
            "status": cur["status"],
            "progress": cur.get("progress", 0),
            "video_url": video_url,
            "cost_val": cur.get("meta", {}).get("cost_val", 0),
            "currency": settings.currency
        }

    except Exception as e:
        return {"task_id": task_id, "status": "processing", "progress": 20,
                "note": f"轮询出错: {str(e)[:50]}"}


class ShareRequest(BaseModel):
    session_id: str
    task_id: str
    video_url: str
    prompt_en: str = ""
    resolution: str = "1080p"
    duration: int = 12
    thumbnail_url: str = ""


@router.post("/share")
async def create_share(req: ShareRequest, request: Request):
    """创建分享链接"""
    user_id = await require_user(request)
    share_id = await store.create_share(
        video_url=req.video_url,
        prompt_en=req.prompt_en,
        resolution=req.resolution,
        duration=req.duration,
        thumbnail_url=req.thumbnail_url,
        user_id=user_id or "",
    )
    return {"success": True, "share_id": share_id, "share_url": f"/share/{share_id}"}
