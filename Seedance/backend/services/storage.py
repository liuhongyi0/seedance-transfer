"""
对象存储服务 —— R2（海外）/ 阿里云 OSS（国内）/ imgbb 降级
上传用户原图，中转私有 URL → 公网 URL
"""

import os
import uuid
import base64
import httpx
from config import settings

R2_KEY = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_ENDPOINT = os.getenv("R2_ENDPOINT", "")
R2_BUCKET = os.getenv("R2_BUCKET", "seedance-studios")
R2_PUBLIC_BASE = os.getenv("R2_PUBLIC_BASE", "")  # 如 https://pub.xxx.r2.dev

_s3 = None


def _get_s3():
    """延迟初始化 boto3 S3 client"""
    global _s3
    if _s3 is None and all([R2_KEY, R2_SECRET, R2_ENDPOINT]):
        import boto3
        from botocore.config import Config
        _s3 = boto3.client(
            "s3",
            endpoint_url=R2_ENDPOINT,
            aws_access_key_id=R2_KEY,
            aws_secret_access_key=R2_SECRET,
            config=Config(signature_version="s3v4", region_name="auto"),
        )
    return _s3


async def upload_from_url(http: httpx.AsyncClient, source_url: str,
                          prefix: str = "rehost") -> str:
    """
    从源 URL 下载文件，上传到 R2，返回公网 URL。
    R2 未配置时降级到 imgbb。
    """
    # 1. 下载
    dl = await http.get(source_url, timeout=60.0, follow_redirects=True)
    dl.raise_for_status()
    content = dl.content
    content_type = dl.headers.get("content-type", "application/octet-stream")
    return await upload_bytes(content, content_type, prefix=prefix)


async def upload_bytes(content: bytes, content_type: str = "application/octet-stream",
                       prefix: str = "upload") -> str:
    """上传 bytes 到 R2，返回公网 URL"""
    ext = _ext_from_mime(content_type)
    key = f"{prefix}/{uuid.uuid4().hex[:12]}{ext}"

    # R2 / S3
    s3 = _get_s3()
    if s3:
        try:
            s3.put_object(
                Bucket=R2_BUCKET, Key=key, Body=content,
                ContentType=content_type,
            )
        except Exception as e:
            raise RuntimeError(f"R2 put_object failed (bucket={R2_BUCKET}): {e}")
        if R2_PUBLIC_BASE:
            return f"{R2_PUBLIC_BASE.rstrip('/')}/{key}"
        # 自动拼接 endpoint
        ep = R2_ENDPOINT.rstrip("/")
        return f"{ep}/{R2_BUCKET}/{key}"

    # imgbb 降级
    imgbb_key = settings.IMGBB_API_KEY
    if imgbb_key:
        b64 = base64.b64encode(content).decode()
        async with httpx.AsyncClient() as http:
            r = await http.post(
                "https://api.imgbb.com/1/upload",
                data={"key": imgbb_key, "image": b64},
                timeout=30.0,
            )
            r.raise_for_status()
            resp_data = r.json()
            img_url = (resp_data.get("data", {}) or {}).get("url", "")
            if not img_url:
                raise RuntimeError("imgbb upload returned no URL")
            return img_url

    raise RuntimeError("No storage backend configured (R2 or imgbb)")


async def upload_file(content: bytes, filename: str = "image.jpg",
                      content_type: str = "image/jpeg") -> str:
    """上传用户原图到 R2"""
    prefix = "originals"
    return await upload_bytes(content, content_type, prefix=prefix)


def _ext_from_mime(mime: str) -> str:
    m = mime.lower()
    if "png" in m:
        return ".png"
    if "webp" in m:
        return ".webp"
    if "gif" in m:
        return ".gif"
    if "mp4" in m:
        return ".mp4"
    if "webm" in m:
        return ".webm"
    if "mpeg" in m or "mp3" in m:
        return ".mp3"
    if "wav" in m or "wave" in m:
        return ".wav"
    return ".jpg"
