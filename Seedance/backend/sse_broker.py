"""
SSE 任务状态推送 Broker
- 每个 task_id 维护一个 asyncio.Queue
- store.update_task() 时自动推送
- SSE endpoint 订阅 Queue 并流式返回
"""

import asyncio
from typing import Dict


class SSEBroker:
    def __init__(self):
        self._queues: Dict[str, asyncio.Queue] = {}

    def subscribe(self, task_id: str) -> asyncio.Queue:
        q = asyncio.Queue()
        self._queues[task_id] = q
        return q

    def unsubscribe(self, task_id: str):
        self._queues.pop(task_id, None)

    async def publish(self, task_id: str, data: dict):
        q = self._queues.get(task_id)
        if q:
            await q.put(data)


sse_broker = SSEBroker()
