"""审查进度事件总线 — 内存级发布/订阅 + 历史回放

ReviewService 在审查各阶段发布事件，WebSocket 端点订阅并推送给前端。
事件历史会保留，新订阅者连接时先回放历史事件，避免漏掉早期进度。
单进程内存实现（足够本项目规模；多进程需替换为 Redis pub/sub）。
"""

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger()

# 历史保留的事件类型（完成后仍保留供回放）
_TERMINAL_EVENTS = ("review_completed", "review_failed")


class ProgressEmitter:
    """审查进度事件总线（含历史回放）"""

    def __init__(self):
        # review_id -> list[asyncio.Queue]
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        # review_id -> list[历史事件 payload]
        self._history: dict[str, list[dict]] = {}

    def subscribe(self, review_id: str) -> asyncio.Queue:
        """订阅某个审查的进度事件（先回放历史，再接收实时）"""
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(review_id, []).append(q)
        # 回放历史事件，避免漏掉订阅前已发射的进度
        for payload in self._history.get(review_id, []):
            q.put_nowait(payload)
        logger.info("WS 订阅", review_id=review_id, subs=len(self._subscribers[review_id]),
                    replayed=len(self._history.get(review_id, [])))
        return q

    def unsubscribe(self, review_id: str, queue: asyncio.Queue):
        """取消订阅；若无订阅者且审查已结束，清理历史"""
        subs = self._subscribers.get(review_id, [])
        if queue in subs:
            subs.remove(queue)
        if not subs:
            self._subscribers.pop(review_id, None)
            # 若审查已结束，清理历史
            history = self._history.get(review_id, [])
            if history and history[-1].get("event") in _TERMINAL_EVENTS:
                self._history.pop(review_id, None)

    async def emit(self, review_id: str, event: str, data: dict[str, Any] | None = None):
        """发布进度事件：记录历史 + 推送给所有订阅者"""
        payload = {
            "event": event,
            "review_id": review_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data or {},
        }
        # 记录历史
        self._history.setdefault(review_id, []).append(payload)
        # 审查结束后，保留历史直到所有订阅者断开（由 unsubscribe 清理）

        subs = self._subscribers.get(review_id, [])
        for q in subs:
            try:
                await q.put(payload)
            except Exception as e:
                logger.warning("WS 推送失败", error=str(e))
        logger.info("进度事件", review_id=review_id, event_name=event, subs=len(subs))


# 全局单例
progress_emitter = ProgressEmitter()
