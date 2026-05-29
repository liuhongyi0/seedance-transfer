"""
SSE 实时推送路由
GET /api/sse/task/{task_id}?session_id=xxx  → Server-Sent Events 流
"""

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sse_broker import sse_broker
from store import store
import asyncio
import json

router = APIRouter()


@router.get("/task/{task_id}")
async def sse_task_stream(task_id: str, session_id: str, request: Request):
    """
    订阅任务状态更新（Server-Sent Events）

    前端使用：
        const es = new EventSource(`/api/sse/task/${task_id}?session_id=${SESSION_ID}`);
        es.onmessage = (e) => { const data = JSON.parse(e.data); updateUI(data); };
        es.onerror = () => es.close();
    """
    async def event_generator():
        # 发送初始状态
        task = await store.get_task(session_id, task_id)
        init_status = "pending"
        if task:
            init_status = task.get("status", "pending")
            init_data = json.dumps({
                "task_id": task_id,
                "status": init_status,
                "progress": task.get("progress", 0),
                "result_url": task.get("result_url"),
                "error": task.get("error"),
            }, ensure_ascii=False)
            yield f"data: {init_data}\n\n"

        # 已完成/失败 → 直接发送 done 退出
        if init_status in ("completed", "failed", "succeeded"):
            yield f"event: done\ndata: {init_data}\n\n"
            return

        q = sse_broker.subscribe(task_id)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                    if data.get("status") in ("completed", "failed", "succeeded"):
                        yield f"event: done\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                        break
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            sse_broker.unsubscribe(task_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx 禁用缓冲
        }
    )
