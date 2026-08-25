"""审查步骤持久化 — 可观测性（写入 review_steps 表）

ReviewFlow 在每个节点完成后调用 review_step_recorder.record()，
把该步的执行结果（做了什么 / 耗时 / 输入输出摘要 / 跳过或异常）落库。
供「审查详情页」回看完整执行过程（时间线）。失败不阻断审查。

注意：Flow 的多个 @listen 节点并行执行，会并发调用 record()。
SQLite 单写者 + WAL + busy_timeout 已足够；record 内置短重试兜底偶发写锁。
（不引入 asyncio.Lock：模块级单例 Lock 会绑定事件循环，pytest-asyncio 多 loop 下报错。）
"""

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import func, select

from app.core.database import async_session_factory
from app.models.review_step import ReviewStep

logger = structlog.get_logger()


class ReviewStepRecorder:
    """把审查执行步骤持久化到 review_steps 表（sequence 自动递增，写库失败短重试）"""

    async def record(
        self,
        review_id: str,
        phase: str,
        node_type: str,
        status: str,
        action_text: str | None = None,
        agent_name: str | None = None,
        input_summary: str | None = None,
        output_summary: str | None = None,
        duration_ms: int | None = None,
        detail: dict | None = None,
    ) -> None:
        """记录一个已结束的步骤（completed / skipped / failed）"""
        if not review_id:
            return
        now = datetime.now(timezone.utc)
        for attempt in range(3):
            try:
                async with async_session_factory() as db:
                    max_seq = (
                        await db.execute(
                            select(func.max(ReviewStep.sequence)).where(
                                ReviewStep.review_id == review_id
                            )
                        )
                    ).scalar()
                    step = ReviewStep(
                        review_id=review_id,
                        sequence=(max_seq or 0) + 1,
                        phase=phase,
                        node_type=node_type,
                        status=status,
                        action_text=action_text,
                        agent_name=agent_name,
                        input_summary=input_summary,
                        output_summary=output_summary,
                        duration_ms=duration_ms,
                        detail=detail or {},
                        started_at=now,
                        ended_at=now if status in ("completed", "skipped", "failed") else None,
                    )
                    db.add(step)
                    await db.commit()
                return
            except Exception as e:
                if attempt == 2:
                    logger.warning(
                        "审查步骤持久化失败",
                        error=str(e), review_id=review_id, node_type=node_type,
                    )
                else:
                    await asyncio.sleep(0.15 * (attempt + 1))


# 全局单例
review_step_recorder = ReviewStepRecorder()
