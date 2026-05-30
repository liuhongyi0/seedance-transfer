"""
Video generation provider — routes to Volcengine (Seedance 直连) or EvoLink
based on model catalog provider field.

Volcengine: uses multimodal content[] format (Ark API)
EvoLink:    uses flat JSON format (proxy API)
"""

import asyncio
import httpx
from typing import Optional
from log_config import get_logger

logger = get_logger(__name__)

from config import settings
from services.model_catalog import (
    VIDEO_DRAFT, get_provider, get_volc_model, get_evolink_name
)


async def submit_video(
    http: httpx.AsyncClient,
    *,
    prompt: str,
    model_key: Optional[str] = None,
    duration: int = 5,
    resolution: str = "720p",
    aspect_ratio: str = "16:9",
    image_url: Optional[str] = None,
) -> dict:
    """Submit a video generation task. Returns {"task_id": "...", "remote_id": "..."}."""

    provider = get_provider(VIDEO_DRAFT, model_key)

    if provider == "volcengine":
        return await _submit_volc(http, prompt=prompt, model_key=model_key,
                                  duration=duration, resolution=resolution,
                                  aspect_ratio=aspect_ratio, image_url=image_url)
    else:
        return await _submit_evolink(http, prompt=prompt, model_key=model_key,
                                     duration=duration, aspect_ratio=aspect_ratio,
                                     image_url=image_url)


async def poll_video(
    http: httpx.AsyncClient,
    *,
    remote_id: str,
    model_key: Optional[str] = None,
    provider: Optional[str] = None,
    max_attempts: int = 100,
) -> dict:
    """Poll video task until complete. Returns {"status": "succeeded|failed|processing", "video_url": "..."}."""

    if not provider:
        provider = get_provider(VIDEO_DRAFT, model_key)

    if provider == "volcengine":
        return await _poll_volc(http, remote_id, max_attempts)
    else:
        return await _poll_evolink(http, remote_id, max_attempts)


# ── Volcengine (Ark API) ────────────────────────────────────────────────────

async def _submit_volc(
    http: httpx.AsyncClient,
    *,
    prompt: str,
    model_key: Optional[str],
    duration: int,
    resolution: str,
    aspect_ratio: str,
    image_url: Optional[str],
) -> dict:
    model = get_volc_model(VIDEO_DRAFT, model_key, resolution)
    content: list = []

    if prompt:
        content.append({"type": "text", "text": prompt})

    if image_url:
        content.append({
            "type": "image_url",
            "image_url": {"url": image_url},
            "role": "reference_image",
        })

    payload = {
        "model": model,
        "content": content,
        "duration": duration,
        "ratio": aspect_ratio,
        "watermark": False,
    }

    resp = await http.post(
        f"{settings.VOLC_BASE_URL}{settings.VOLC_VIDEO_TASK_URL}",
        headers={
            "Authorization": f"Bearer {settings.VOLC_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()
    remote_id = data.get("id") or data.get("task_id", "")
    return {"remote_id": remote_id, "provider": "volcengine"}


async def _poll_volc(
    http: httpx.AsyncClient,
    remote_id: str,
    max_attempts: int,
) -> dict:
    for _ in range(max_attempts):
        await asyncio.sleep(settings.POLL_INTERVAL)
        try:
            resp = await http.get(
                f"{settings.VOLC_BASE_URL}{settings.VOLC_VIDEO_TASK_URL}/{remote_id}",
                headers={"Authorization": f"Bearer {settings.VOLC_API_KEY}"},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"[volc poll] Error: {e}")
            continue

        status = data.get("status", "processing")
        if status in ("completed", "succeeded"):
            video_url = (
                data.get("content", {}).get("video_url")
                or data.get("video_url")
                or (data.get("output") or [None])[0]
            )
            return {"status": "succeeded", "video_url": video_url or ""}
        elif status == "failed":
            err = data.get("error", {}).get("message", "Unknown error")
            return {"status": "failed", "error": err}

    return {"status": "processing", "video_url": ""}


# ── EvoLink (proxy API) ─────────────────────────────────────────────────────

async def _submit_evolink(
    http: httpx.AsyncClient,
    *,
    prompt: str,
    model_key: Optional[str],
    duration: int,
    aspect_ratio: str,
    image_url: Optional[str],
) -> dict:
    # Pick model variant: image-to-video if ref image exists, else text-to-video
    base_model = get_evolink_name(VIDEO_DRAFT, model_key)
    if image_url:
        # Use image-to-video variant (e.g. seedance-2.0-fast-image-to-video)
        evolink_model = base_model.replace("-text-to-video", "-image-to-video") \
                                   if "-text-to-video" in base_model else base_model
    else:
        evolink_model = base_model

    body = {
        "model": evolink_model,
        "prompt": prompt,
        "duration": duration,
        "size": aspect_ratio,  # "16:9" format
    }
    if image_url:
        body["image_urls"] = [image_url]

    resp = await http.post(
        f"{settings.EVOLINK_BASE_URL}/videos/generations",
        headers={
            "Authorization": f"Bearer {settings.EVOLINK_API_KEY}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    remote_id = data.get("id", "")
    return {"remote_id": remote_id, "provider": "evolink"}


async def _poll_evolink(
    http: httpx.AsyncClient,
    remote_id: str,
    max_attempts: int,
) -> dict:
    for _ in range(max_attempts):
        await asyncio.sleep(settings.POLL_INTERVAL)
        try:
            resp = await http.get(
                f"{settings.EVOLINK_BASE_URL}/tasks/{remote_id}",
                headers={"Authorization": f"Bearer {settings.EVOLINK_API_KEY}"},
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"[evolink poll] Error: {e}")
            continue

        status = data.get("status", "processing")
        if status == "succeeded":
            # EvoLink returns result_data[].video_url or results[]
            result_data = data.get("result_data", [])
            if result_data and isinstance(result_data, list):
                item = result_data[0]
                video_url = item.get("video_url") if isinstance(item, dict) else item
            else:
                results = data.get("results", [])
                video_url = results[0] if results else ""
                if isinstance(video_url, dict):
                    video_url = video_url.get("video_url", "")
            return {"status": "succeeded", "video_url": video_url or ""}
        elif status == "failed":
            return {"status": "failed", "error": "EvoLink generation failed"}

    return {"status": "processing", "video_url": ""}
