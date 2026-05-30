"""
文件上传路由
POST /api/upload/video  → 上传视频到 R2，返回永久 URL
POST /api/upload/image  → 上传图片到 R2，返回永久 URL
"""

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from services.storage import upload_bytes
from log_config import get_logger

logger = get_logger(__name__)

router = APIRouter()

MAX_VIDEO_SIZE = 500 * 1024 * 1024  # 500MB
MAX_IMAGE_SIZE = 20 * 1024 * 1024   # 20MB


@router.post("/video")
async def upload_video(file: UploadFile = File(...)):
    """上传视频文件到 R2，返回永久公网 URL"""
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Only video files are accepted")

    content = await file.read()
    if len(content) > MAX_VIDEO_SIZE:
        raise HTTPException(status_code=400, detail="Video too large (max 500MB)")

    try:
        url = await upload_bytes(content, file.content_type, prefix="videos")
        return {
            "success": True,
            "url": url,
            "filename": file.filename,
            "size": len(content),
            "content_type": file.content_type,
        }
    except Exception as e:
        logger.error(f"[UPLOAD VIDEO] Error: {e}")
        raise HTTPException(status_code=500, detail="Video upload failed due to an internal error")


@router.post("/image")
async def upload_image(file: UploadFile = File(...)):
    """上传图片文件到 R2，返回永久公网 URL"""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are accepted")

    content = await file.read()
    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="Image too large (max 20MB)")

    try:
        url = await upload_bytes(content, file.content_type, prefix="images")
        return {
            "success": True,
            "url": url,
            "filename": file.filename,
            "size": len(content),
            "content_type": file.content_type,
        }
    except Exception as e:
        logger.error(f"[UPLOAD IMAGE] Error: {e}")
        raise HTTPException(status_code=500, detail="Image upload failed due to an internal error")
