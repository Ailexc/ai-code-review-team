"""审查进度事件总线 — 内存级发布/订阅

ReviewService 在审查各阶段发布事件，WebSocket 端点订阅并推送给前端。
单进程内存实现（足够本项目规模；多进程需替换为 Redis pub/sub）。
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger()


class ProgressEmitter:
    """审查进度事件总线"""

    def __init__(self):
        # review_id -> list[asyncio.Queue]
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, review_id: str) -> asyncio.Queue:
        """订阅某个审查的进度事件"""
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(review_id, []).append(q)
        logger.info("WS 订阅", review_id=review_id, subs=len(self._subscribers[review_id]))
        return q

    def unsubscribe(self, review_id: str, queue: asyncio.Queue):
        """取消订阅"""
        subs = self._subscribers.get(review_id, [])
        if queue in subs:
            subs.remove(queue)
        if not subs:
            self._subscribers.pop(review_id, None)

    async def emit(self, review_id: str, event: str, data: dict[str, Any] | None = None):
        """发布进度事件给所有订阅者"""
        payload = {
            "event": event,
            "review_id": review_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data or {},
        }
        subs = self._subscribers.get(review_id, [])
        for q in subs:
            try:
                await q.put(payload)
            except Exception as e:
                logger.warning("WS 推送失败", error=str(e))
        logger.info("进度事件", review_id=review_id, event_name=event, subs=len(subs))


# 全局单例
progress_emitter = ProgressEmitter()
