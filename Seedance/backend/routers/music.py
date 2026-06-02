"""
步骤四：音乐生成路由
POST /api/music/generate   → 调用 EvoLink Suno v4
GET  /api/music/task/{id}  → 轮询任务状态
POST /api/music/save       → 保存到素材盘
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List, Literal
import httpx
import asyncio

from config import settings
from store import store
from services.billing import calculate_cost, charge, refund, require_user
from services.moderation import screen_prompt
from log_config import get_logger

logger = get_logger(__name__)

router = APIRouter()

MOOD_MAP = {
    "热血/高能": "epic, intense, powerful, energetic",
    "温柔舒缓": "gentle, soothing, calm, peaceful",
    "神秘暗黑": "dark, mysterious, ominous, cinematic",
    "欢快轻松": "upbeat, playful, cheerful, light",
    "史诗磅礴": "cinematic, orchestral, grand, majestic",
    "空灵治愈": "ambient, ethereal, healing, transcendent",
}

GENRE_MAP = {
    "电子合成": "electronic synthesis",
    "古典管弦": "classical orchestral",
    "爵士": "jazz",
    "民谣": "folk",
    "摇滚": "rock",
    "嘻哈": "hip hop",
    "国风古典": "Chinese traditional",
    "纯钢琴": "solo piano",
}

TEMPO_MAP = {
    "very_slow": "very slow, meditative, 40-60 BPM",
    "slow": "slow, relaxed, 60-80 BPM",
    "medium": "moderate, 80-110 BPM",
    "fast": "fast, energetic, 120-150 BPM",
}


class MusicGenRequest(BaseModel):
    session_id: str
    mood: str = "温柔舒缓"
    genre: str = "纯钢琴"
    instruments: List[str] = []
    tempo: Literal["very_slow", "slow", "medium", "fast"] = "medium"
    duration: int = 30
    sync_with_video_style: bool = False
    prompt_override: Optional[str] = None
    model_key: Optional[str] = None


class MusicSaveRequest(BaseModel):
    session_id: str
    task_id: str
    audio_url: str
    mood: str = ""
    genre: str = ""
    duration: int = 30


@router.post("/generate")
async def generate_music(req: MusicGenRequest, request: Request):
    """
    生成音乐草稿（Suno v4 via EvoLink，约¥0.10/个）
    """
    try:
        await store.require(req.session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    user_id = await require_user(request)
    cost_subunit = calculate_cost("music", model_key=req.model_key)
    if user_id:
        user = await store.get_user_by_id(user_id)
        balance = user.get("balance_subunit", 0) if user else 0
        if balance < cost_subunit:
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient balance. Need {cost_subunit} {settings.currency_subunit}, have {balance}."
            )
        await charge(user_id, "music", cost_subunit, req.mood)

    if req.prompt_override:
        suno_prompt = req.prompt_override
    else:
        mood_en = MOOD_MAP.get(req.mood, req.mood)
        genre_en = GENRE_MAP.get(req.genre, req.genre)
        tempo_en = TEMPO_MAP.get(req.tempo, "moderate")
        instruments_en = ", ".join(req.instruments) if req.instruments else ""

        suno_prompt = f"{mood_en}, {genre_en}"
        if instruments_en:
            suno_prompt += f", featuring {instruments_en}"
        suno_prompt += f", {tempo_en}, {req.duration} seconds"

    task_id = await store.create_task(req.session_id, "music", {
        "suno_prompt": suno_prompt,
        "mood": req.mood,
        "genre": req.genre,
        "duration": req.duration,
        "estimated_cost_val": settings.cost_music_per_unit
    })

    if not settings.EVOLINK_API_KEY:
        mock_url = "https://www.soundjay.com/misc/sounds/bell-ringing-05.wav"
        await store.update_task(req.session_id, task_id,
                          status="completed", progress=100,
                          result_url=mock_url,
                          meta={"audio_url": mock_url, "suno_prompt": suno_prompt, "cost_val": settings.cost_music_per_unit})
        return {
            "success": True,
            "task_id": task_id,
            "status": "completed",
            "audio_url": mock_url,
            "suno_prompt": suno_prompt,
            "cost_val": settings.cost_music_per_unit,
            "currency": settings.currency,
            "note": "⚠️ Mock模式（EvoLink Suno API尚未开放）"
        }

    http = request.app.state.http_client
    try:
        await store.update_task(req.session_id, task_id, status="processing", progress=5)

        # Content moderation
        await screen_prompt(suno_prompt, f"music/generate:{user_id}")

        from services.model_catalog import get_evolink_name
        evolink_model = get_evolink_name("music", req.model_key)

        resp = await http.post(
            f"{settings.EVOLINK_BASE_URL}/audios/generations",
            headers={"Authorization": f"Bearer {settings.EVOLINK_API_KEY}"},
            json={
                "model": evolink_model,
                "prompt": suno_prompt,
                "duration": req.duration,
                "instrumental": True,
            },
            timeout=60.0
        )
        resp.raise_for_status()
        data = resp.json()

        evo_task_id = data.get("id")
        if not evo_task_id:
            raise HTTPException(status_code=502, detail="EvoLink未返回task_id")

        await store.update_task(req.session_id, task_id, status="processing", progress=10,
                          meta={"evo_task_id": evo_task_id, "suno_prompt": suno_prompt})

        # Background polling (no blocking — client polls via GET /task/{id})
        async def _background_poll():
            try:
                for i in range(settings.MAX_POLL_DRAFT):
                    await asyncio.sleep(settings.POLL_INTERVAL)
                    poll_resp = await http.get(
                        f"{settings.EVOLINK_BASE_URL}/tasks/{evo_task_id}",
                        headers={"Authorization": f"Bearer {settings.EVOLINK_API_KEY}"},
                        timeout=30.0
                    )
                    poll_resp.raise_for_status()
                    poll_data = poll_resp.json()

                    pct = poll_data.get("progress", 0)
                    status = poll_data.get("status", "processing")
                    await store.update_task(req.session_id, task_id, status=status,
                                      progress=min(10 + pct * 0.9, 99))

                    if status in ("completed", "succeeded"):
                        results = poll_data.get("results", [])
                        result_data = poll_data.get("result_data", [])
                        if result_data and isinstance(result_data, list):
                            item = result_data[0]
                            audio_url = item.get("audio_url") if isinstance(item, dict) else item
                        elif results and isinstance(results, list):
                            audio_url = results[0] if isinstance(results[0], str) else results[0].get("audio_url", "")
                        else:
                            audio_url = poll_data.get("audio_url") or (poll_data.get("output") or [None])[0]
                        logger.info(f"✅ 音乐生成完成: {audio_url[:60]}...")
                        await store.update_task(req.session_id, task_id,
                                          status="completed", progress=100,
                                          result_url=audio_url,
                                          meta={"audio_url": audio_url,
                                                "evo_task_id": evo_task_id,
                                                "suno_prompt": suno_prompt,
                                                "credits_used": poll_data.get("usage", {}).get("credits_used")})
                        return

                    elif status == "failed":
                        error_msg = poll_data.get("error", {}).get("message", "未知错误")
                        await store.update_task(req.session_id, task_id, status="failed", error=error_msg)
                        return

                await store.update_task(req.session_id, task_id, status="failed",
                                  error=f"轮询超时（{settings.MAX_POLL_DRAFT * settings.POLL_INTERVAL}s）")
            except Exception as e:
                logger.error(f"❌ 音乐后台轮询异常: {e}")
                await store.update_task(req.session_id, task_id, status="failed", error=str(e)[:200])

        asyncio.create_task(_background_poll())

        return {
            "success": True,
            "task_id": task_id,
            "status": "processing",
            "cost_val": settings.cost_music_per_unit,
            "currency": settings.currency,
            "note": "任务已提交，请轮询 GET /api/music/task/{task_id}?session_id=xxx"
        }

    except httpx.HTTPStatusError as e:
        if user_id and cost_subunit:
            await refund(user_id, "music", cost_subunit, "EvoLink API error")
        detail = f"EvoLink Suno API错误({e.response.status_code})"
        try:
            body = e.response.json()
            detail += f": {body.get('error', {}).get('message', e.response.text[:200])}"
        except Exception:
            detail += f": {e.response.text[:200]}"
        await store.update_task(req.session_id, task_id, status="failed", error=detail)
        raise HTTPException(status_code=502, detail=detail)
    except HTTPException:
        if user_id and cost_subunit:
            await refund(user_id, "music", cost_subunit, "task failed")
        raise
    except Exception as e:
        if user_id and cost_subunit:
            await refund(user_id, "music", cost_subunit, str(e)[:80])
        await store.update_task(req.session_id, task_id, status="failed", error=str(e))
        raise HTTPException(status_code=500, detail="Music generation failed due to an internal error")

@router.get("/task/{task_id}")
async def poll_music(task_id: str, session_id: str, request: Request):
    """轮询音乐生成状态"""
    task = await store.get_task(session_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if not settings.EVOLINK_API_KEY or task["status"] in ("completed", "failed"):
        return {
            "task_id": task_id,
            "status": task["status"],
            "progress": task.get("progress", 100),
            "audio_url": task.get("result_url"),
            "error": task.get("error")
        }

    evo_task_id = task.get("meta", {}).get("evo_task_id")
    if not evo_task_id:
        return {"task_id": task_id, "status": "processing", "progress": 10}

    http = request.app.state.http_client
    try:
        resp = await http.get(
            f"{settings.EVOLINK_BASE_URL}/tasks/{evo_task_id}",
            headers={"Authorization": f"Bearer {settings.EVOLINK_API_KEY}"},
            timeout=10.0
        )
        resp.raise_for_status()
        data = resp.json()

        provider_status = data.get("status", "processing")
        audio_url = None

        if provider_status in ("succeeded", "completed"):
            results = data.get("results", [])
            result_data = data.get("result_data", [])
            if result_data and isinstance(result_data, list):
                item = result_data[0]
                audio_url = item.get("audio_url") if isinstance(item, dict) else item
            elif results and isinstance(results, list):
                audio_url = results[0] if isinstance(results[0], str) else results[0].get("audio_url", "")
            else:
                audio_url = data.get("audio_url") or (data.get("output") or [None])[0]
            await store.update_task(session_id, task_id,
                              status="completed", progress=100, result_url=audio_url)
        elif provider_status == "failed":
            await store.update_task(session_id, task_id,
                              status="failed", error=data.get("error", "音乐生成失败"))
        else:
            import time
            elapsed = time.time() - task["created_at"]
            progress = min(90, int(elapsed / 30 * 80) + 10)
            await store.update_task(session_id, task_id, progress=progress)

        cur = await store.get_task(session_id, task_id)
        return {
            "task_id": task_id,
            "status": cur["status"],
            "progress": cur.get("progress", 0),
            "audio_url": audio_url,
        }

    except Exception as e:
        return {"task_id": task_id, "status": "processing", "progress": 20,
                "note": f"轮询出错: {str(e)[:50]}"}


@router.post("/save")
async def save_music(req: MusicSaveRequest):
    """将音乐保存到素材盘"""
    mus_id = await store.add_music(
        session_id=req.session_id,
        url=req.audio_url,
        mood=req.mood,
        genre=req.genre,
        duration=req.duration
    )
    return {"success": True, "music_id": mus_id}
