"""
步骤一：图片生成路由
POST /api/image/generate   → 调用 EvoLink Seedream 4.5 生成参考图
GET  /api/image/task/{id}  → 查询生成任务状态
POST /api/image/save       → 将生成的图片保存到素材盘
POST /api/image/color      → 保存步骤二的调色参数
POST /api/image/upload     → 上传客户原图到 imgbb，返回公网 URL
"""

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, List, Literal
import httpx
import asyncio

from config import settings
from store import store
from services.prompt_builder import build_image_prompt
from services.billing import calculate_cost, charge, refund, require_user
from log_config import get_logger

logger = get_logger(__name__)

router = APIRouter()

# ─── 请求模型 ─────────────────────────────────────────────────────────────────

class ImageGenRequest(BaseModel):
    session_id: str
    prompt_cn: str                   # 中文描述
    style: str = "电影质感"
    lighting: str = "自然柔光"
    mood: str = "温暖治愈"
    theme: str = "人物"
    ratio: Literal["16:9", "9:16", "1:1", "4:3"] = "16:9"
    count: int = 3
    model_key: Optional[str] = None
    # EvoLink 支持的 size 格式：aspect ratio 字符串（非像素尺寸）
    # auto, 1:1, 16:9, 9:16, 4:3, 3:4 等

class ImageSaveRequest(BaseModel):
    session_id: str
    task_id: str
    image_urls: List[str]   # 要保存的图片URL（可多选）

class ColorSaveRequest(BaseModel):
    session_id: str
    image_id: str
    brightness: float = 0
    contrast: float = 0
    shadows: float = 0
    highlights: float = 0
    saturation: float = 0
    color_temp: float = 0


# ─── 路由 ─────────────────────────────────────────────────────────────────────

@router.post("/generate")
async def generate_images(req: ImageGenRequest, request: Request):
    """
    提交图片生成任务
    - 将中文参数翻译/拼合为英文Prompt
    - 调用 EvoLink Seedream 4.5 API（异步任务，自动轮询）
    - 返回图片URL列表
    """
    # 参数校验
    if req.count < 1 or req.count > 4:
        raise HTTPException(status_code=400, detail="count must be 1-4")

    # 验证Session
    try:
        await store.require(req.session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # 计费：提取用户、计算成本、检查余额、扣款
    user_id = await require_user(request)
    cost_subunit = calculate_cost("image", count=req.count, model_key=req.model_key)
    if user_id:
        user = await store.get_user_by_id(user_id)
        balance = user.get("balance_subunit", 0) if user else 0
        if balance < cost_subunit:
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient balance. Need {cost_subunit} {settings.currency_subunit}, have {balance}."
            )
        try:
            await charge(user_id, "image", cost_subunit,
                         f"{req.count}x images, prompt: {req.prompt_cn[:50]}")
        except ValueError as e:
            raise HTTPException(status_code=402, detail=str(e))

    # 构建英文Prompt
    prompt_en = build_image_prompt(
        theme=req.theme,
        style=req.style,
        lighting=req.lighting,
        mood=req.mood,
        keywords_cn=req.prompt_cn
    )

    # EvoLink Seedream 使用 aspect ratio 字符串（非像素尺寸）
    size = req.ratio

    # 创建本地任务记录
    task_id = await store.create_task(req.session_id, "image", {
        "prompt_en": prompt_en,
        "prompt_cn": req.prompt_cn,
        "ratio": req.ratio,
        "count": req.count,
    })

    # 没有配置EvoLink Key时，返回Mock数据
    if not settings.EVOLINK_API_KEY:
        mock_images = [
            f"https://picsum.photos/seed/{task_id[:4]}{i}/800/450" for i in range(req.count)
        ]
        await store.update_task(req.session_id, task_id,
                          status="completed", progress=100,
                          result_url=mock_images[0],
                          meta={"images": mock_images, "prompt_en": prompt_en})
        return {
            "success": True,
            "task_id": task_id,
            "status": "completed",
            "images": mock_images,
            "prompt_en": prompt_en,
            "cost_subunit": cost_subunit,
            "currency": settings.currency,
            "note": "⚠️ Mock模式（未配置EVOLINK_API_KEY）"
        }

    # 真实调用 EvoLink Seedream 4.5（并发生成 count 张）
    http = request.app.state.http_client
    try:
        await store.update_task(req.session_id, task_id, status="processing", progress=10)

        from services.model_catalog import get_evolink_name
        evolink_model = get_evolink_name("image", req.model_key)

        async def _submit_one() -> str:
            """提交单张图片生成任务，返回 evo_task_id"""
            r = await http.post(
                f"{settings.EVOLINK_BASE_URL}/images/generations",
                headers={"Authorization": f"Bearer {settings.EVOLINK_API_KEY}"},
                json={"model": evolink_model, "prompt": prompt_en, "size": size},
                timeout=60.0
            )
            r.raise_for_status()
            d = r.json()
            tid = d.get("id")
            if not tid:
                raise ValueError(f"EvoLink未返回task_id: {str(d)[:100]}")
            return tid

        async def _poll_one(evo_tid: str) -> Optional[str]:
            """轮询单个任务，返回图片URL或None"""
            for _ in range(25):
                await asyncio.sleep(3)
                pr = await http.get(
                    f"{settings.EVOLINK_BASE_URL}/tasks/{evo_tid}",
                    headers={"Authorization": f"Bearer {settings.EVOLINK_API_KEY}"},
                    timeout=30.0
                )
                pr.raise_for_status()
                pd = pr.json()
                st = pd.get("status", "processing")
                if st in ("completed", "succeeded"):
                    results = pd.get("results", [])
                    if results:
                        return results[0] if isinstance(results[0], str) else results[0].get("url")
                    rd = pd.get("result_data", [])
                    if rd:
                        return rd[0].get("url")
                    # data[].url 格式
                    data_list = pd.get("data", [])
                    if data_list:
                        return data_list[0].get("url")
                    return pd.get("url") or pd.get("image_url")
                if st == "failed":
                    return None
            return None

        # 并发提交 count 个任务
        evo_task_ids = await asyncio.gather(*[_submit_one() for _ in range(req.count)])
        await store.update_task(req.session_id, task_id, status="processing", progress=30,
                          meta={"evo_task_ids": list(evo_task_ids)})

        # 并发轮询所有任务
        image_urls = await asyncio.gather(*[_poll_one(tid) for tid in evo_task_ids])
        results = [u for u in image_urls if u]

        if not results:
            raise HTTPException(status_code=502, detail="EvoLink未返回任何图片URL")

        await store.update_task(req.session_id, task_id,
                          status="completed", progress=100,
                          result_url=results[0],
                          meta={"images": results, "prompt_en": prompt_en,
                                "evo_task_ids": list(evo_task_ids)})

        return {
            "success": True,
            "task_id": task_id,
            "status": "completed",
            "images": results,
            "prompt_en": prompt_en,
            "cost_subunit": cost_subunit,
            "currency": settings.currency,
        }

    except httpx.HTTPStatusError as e:
        if user_id and cost_subunit:
            await refund(user_id, "image", cost_subunit, "EvoLink API error")
        await store.update_task(req.session_id, task_id,
                          status="failed", error=str(e))
        raise HTTPException(status_code=502, detail=f"EvoLink API错误: {e.response.status_code}")
    except HTTPException:
        if user_id and cost_subunit:
            await refund(user_id, "image", cost_subunit, "task failed")
        raise
    except Exception as e:
        if user_id and cost_subunit:
            await refund(user_id, "image", cost_subunit, str(e)[:80])
        await store.update_task(req.session_id, task_id,
                          status="failed", error=str(e))
        raise HTTPException(status_code=500, detail="Image generation failed due to an internal error")


@router.get("/task/{task_id}")
async def get_task_status(task_id: str, session_id: str):
    """查询图片生成任务状态"""
    task = await store.get_task(session_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    images = task.get("meta", {}).get("images", [])
    return {
        "task_id": task_id,
        "status": task["status"],
        "progress": task.get("progress", 0),
        "images": images,
        "error": task.get("error")
    }


@router.post("/save")
async def save_images(req: ImageSaveRequest):
    """将选中的图片保存到素材盘"""
    saved_ids = []
    for url in req.image_urls[:9]:  # 最多9张
        img_id = await store.add_image(req.session_id, url)
        saved_ids.append(img_id)

    return {
        "success": True,
        "saved_count": len(saved_ids),
        "image_ids": saved_ids
    }


@router.post("/upload")
async def upload_customer_image(
    session_id: str = Form(...),
    file: UploadFile = File(...),
    request: Request = None
):
    """上传客户原图：接收文件 → 上传 R2 → 保存到素材盘 → 返回公网 URL"""
    try:
        await store.require(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="图片不能超过 10MB")

    try:
        from services.storage import upload_file
        url = await upload_file(content, filename=file.filename or "image.jpg",
                                content_type=file.content_type or "image/jpeg")
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=f"Storage not configured: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upload failed: {str(e)}")

    img_id = await store.add_image(session_id, url)
    return {"success": True, "image_id": img_id, "url": url}


class DescribeRequest(BaseModel):
    session_id: str
    image_url: str
    context_hint: str = ""   # 用户选择的主题/关键词，作为描述分析的方向提示

class StylizeRequest(BaseModel):
    session_id: str
    image_url: str
    style: str = "cinematic film"
    lighting: str = "soft natural light"
    mood: str = "warm healing"
    ratio: Literal["16:9", "9:16", "1:1", "4:3"] = "16:9"
    extra_prompt: str = ""   # 主题 + 关键词
    model_key: Optional[str] = None


DESCRIBE_SYSTEM = (
    "You are a professional video director's assistant. "
    "Analyze the image and output a concise English prompt (≤80 words) "
    "suitable for Seedance video generation. "
    "Describe: main subject, key visual elements, composition, lighting, atmosphere. "
    "Do NOT mention people's real names or faces. "
    "Output the prompt only, no explanations."
)


@router.post("/describe")
async def describe_image(req: DescribeRequest, request: Request):
    """调用视觉大模型分析图片，自动生成视频 Prompt"""
    try:
        await store.require(req.session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not settings.VOLC_API_KEY:
        return {"success": True,
                "prompt_en": "A beautiful scene with cinematic composition, soft natural lighting, warm atmosphere.",
                "note": "Mock模式（未配置VOLC_API_KEY）"}

    http = request.app.state.http_client
    try:
        resp = await http.post(
            f"{settings.VOLC_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {settings.VOLC_API_KEY}",
                     "Content-Type": "application/json"},
            json={
                "model": settings.VOLC_VISION_MODEL,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": req.image_url}},
                        {"type": "text",
                         "text": DESCRIBE_SYSTEM + (f"\n\nUser context hint (focus on these): {req.context_hint}" if req.context_hint else "")}
                    ]
                }],
                "max_tokens": 200,
                "temperature": 0.5
            },
            timeout=30.0
        )
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices", [])
        prompt_en = (choices[0].get("message", {}).get("content", "") if choices else "").strip()
        return {"success": True, "prompt_en": prompt_en}
    except httpx.HTTPStatusError as e:
        raw = e.response.text[:500]
        logger.error(f"❌ 视觉模型HTTP错误 {e.response.status_code}: {raw}")
        try:
            body = e.response.json()
            err = body.get("error", {})
            detail = err.get("message", raw) if isinstance(err, dict) else str(err)
        except Exception:
            detail = raw
        raise HTTPException(status_code=502, detail=f"视觉模型调用失败({e.response.status_code}): {detail}")
    except Exception:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Image description failed due to an internal error")


@router.post("/stylize")
async def stylize_image(req: StylizeRequest, request: Request):
    """AI 风格化：先用视觉模型描述图片内容，再结合风格 Prompt 重新生成"""
    try:
        await store.require(req.session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    http = request.app.state.http_client

    # Step 1: 获取图片内容描述
    content_desc = ""
    if settings.VOLC_API_KEY:
        try:
            resp = await http.post(
                f"{settings.VOLC_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {settings.VOLC_API_KEY}",
                         "Content-Type": "application/json"},
                json={
                    "model": settings.VOLC_VISION_MODEL,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": req.image_url}},
                            {"type": "text",
                             "text": "Describe the main subject and composition of this image in one concise sentence (≤30 words). Output only the description."}
                        ]
                    }],
                    "max_tokens": 80,
                    "temperature": 0.3
                },
                timeout=20.0
            )
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            content_desc = (choices[0].get("message", {}).get("content", "") if choices else "").strip()
        except Exception as e:
            logger.warning(f"⚠️ 视觉描述失败，继续风格化: {e}")

    # Step 2: 构建风格化 Prompt
    style_prompt = f"{content_desc + ', ' if content_desc else ''}{req.extra_prompt + ', ' if req.extra_prompt else ''}{req.style}, {req.lighting}, {req.mood}, high quality, detailed"

    if not settings.EVOLINK_API_KEY:
        mock_url = f"https://picsum.photos/seed/style{hash(req.style)%1000}/800/450"
        return {"success": True, "image_url": mock_url,
                "prompt_en": style_prompt, "note": "Mock模式"}

    # Step 3: 调用 EvoLink 生成风格化图片（带原图为参考）
    try:
        task_id_local = await store.create_task(req.session_id, "image_stylize", {
            "prompt_en": style_prompt, "ratio": req.ratio
        })
        from services.model_catalog import get_evolink_name

        evolink_model = get_evolink_name("image", req.model_key)
        payload = {
            "model": evolink_model,
            "prompt": style_prompt,
            "size": req.ratio,
        }
        # 尝试传入参考图（若 EvoLink 支持）
        if req.image_url:
            payload["reference_image_url"] = req.image_url

        r = await http.post(
            f"{settings.EVOLINK_BASE_URL}/images/generations",
            headers={"Authorization": f"Bearer {settings.EVOLINK_API_KEY}"},
            json=payload,
            timeout=60.0
        )
        r.raise_for_status()
        d = r.json()
        evo_tid = d.get("id")
        if not evo_tid:
            raise ValueError(f"EvoLink未返回task_id: {str(d)[:100]}")

        # 轮询
        for _ in range(25):
            await asyncio.sleep(3)
            pr = await http.get(
                f"{settings.EVOLINK_BASE_URL}/tasks/{evo_tid}",
                headers={"Authorization": f"Bearer {settings.EVOLINK_API_KEY}"},
                timeout=30.0
            )
            pr.raise_for_status()
            pd = pr.json()
            st = pd.get("status", "processing")
            if st in ("completed", "succeeded"):
                results = pd.get("results", [])
                if results:
                    img_url = results[0] if isinstance(results[0], str) else results[0].get("url")
                else:
                    data_list = pd.get("data", [])
                    img_url = (data_list[0].get("url") if data_list else None) or pd.get("url")
                img_id = await store.add_image(req.session_id, img_url)
                await store.update_task(req.session_id, task_id_local,
                                  status="completed", progress=100, result_url=img_url)
                return {"success": True, "image_url": img_url,
                        "image_id": img_id, "prompt_en": style_prompt}
            if st == "failed":
                raise ValueError(pd.get("error", "风格化失败"))
        raise ValueError("风格化轮询超时")
    except httpx.HTTPStatusError as e:
        try:
            body = e.response.json()
            # 若是 reference_image_url 不支持，自动重试不带参考图
            err_msg = body.get("error", {}).get("message", "") if isinstance(body.get("error"), dict) else str(body.get("error",""))
            if "reference_image_url" in err_msg or "unknown" in err_msg.lower():
                payload.pop("reference_image_url", None)
                r2 = await http.post(
                    f"{settings.EVOLINK_BASE_URL}/images/generations",
                    headers={"Authorization": f"Bearer {settings.EVOLINK_API_KEY}"},
                    json=payload, timeout=60.0
                )
                r2.raise_for_status()
                # 简化轮询
                evo_tid2 = r2.json().get("id")
                for _ in range(25):
                    await asyncio.sleep(3)
                    pr2 = await http.get(f"{settings.EVOLINK_BASE_URL}/tasks/{evo_tid2}",
                                         headers={"Authorization": f"Bearer {settings.EVOLINK_API_KEY}"}, timeout=30.0)
                    pr2.raise_for_status()
                    pd2 = pr2.json()
                    if pd2.get("status") in ("completed","succeeded"):
                        results2 = pd2.get("results", [])
                        img_url2 = results2[0] if results2 else pd2.get("url")
                        img_id2 = await store.add_image(req.session_id, img_url2)
                        return {"success": True, "image_url": img_url2,
                                "image_id": img_id2, "prompt_en": style_prompt,
                                "note": "参考图参数不支持，已用纯提示词生成"}
                    if pd2.get("status") == "failed":
                        raise ValueError("风格化失败")
                raise ValueError("轮询超时")
        except HTTPException:
            raise
        except Exception as inner_e:
            logger.warning(f"⚠️ 风格化回退失败: {inner_e}")
        raise HTTPException(status_code=502, detail=f"EvoLink风格化失败: {e.response.status_code}")
    except Exception:
        raise HTTPException(status_code=500, detail="Image stylization failed due to an internal error")
@router.post("/color")
async def save_color(req: ColorSaveRequest):
    """步骤二：保存图片调色参数（供步骤三拼Prompt时使用）"""
    params = {
        "brightness": req.brightness,
        "contrast": req.contrast,
        "shadows": req.shadows,
        "highlights": req.highlights,
        "saturation": req.saturation,
        "color_temp": req.color_temp,
    }
    ok = await store.save_color_params(req.session_id, req.image_id, params)
    if not ok:
        raise HTTPException(status_code=404, detail="图片不存在")

    return {"success": True, "message": "调色参数已保存"}
