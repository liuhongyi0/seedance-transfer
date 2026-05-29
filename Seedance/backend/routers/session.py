"""
会话管理路由
GET  /api/session/new        → 创建新Session，返回session_id
GET  /api/session/{sid}      → 获取Session资产（素材盘数据）
DELETE /api/session/{sid}/asset → 删除某个素材
"""

from fastapi import APIRouter, HTTPException
from store import store

router = APIRouter()


@router.post("/new")
async def create_session():
    """创建匿名会话，返回 session_id（前端存入 localStorage 或内存）"""
    sid = await store.create()
    return {
        "success": True,
        "session_id": sid,
        "expires_in": 86400,
        "message": "会话已创建，24小时内有效"
    }


@router.get("/{session_id}")
async def get_session(session_id: str):
    """获取当前Session的所有素材盘数据"""
    s = await store.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session不存在或已过期")

    # 返回素材盘内容（不含内部字段）
    return {
        "success": True,
        "session_id": session_id,
        "created_at": s["created_at"],
        "expires_at": s["expires_at"],
        "assets": s["assets"],
        "asset_counts": {
            "images": len(s["assets"]["images"]),
            "videos": len(s["assets"]["videos"]),
            "musics": len(s["assets"]["musics"]),
        }
    }


@router.delete("/{session_id}/image/{image_id}")
async def delete_image(session_id: str, image_id: str):
    """从素材盘删除一张图片"""
    try:
        ok = await store.delete_image(session_id, image_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="图片不存在")
    return {"success": True, "message": f"图片 {image_id} 已删除"}


@router.delete("/{session_id}/video/{video_id}")
async def delete_video(session_id: str, video_id: str):
    """从素材盘删除一个视频草稿"""
    try:
        await store.delete_video(session_id, video_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"success": True, "message": f"视频 {video_id} 已删除"}


@router.delete("/{session_id}/music/{music_id}")
async def delete_music(session_id: str, music_id: str):
    """从素材盘删除一个音乐草稿"""
    try:
        await store.delete_music(session_id, music_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"success": True, "message": f"音乐 {music_id} 已删除"}
