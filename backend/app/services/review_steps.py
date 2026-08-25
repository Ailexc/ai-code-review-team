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

import contextvars

logger = structlog.get_logger()

# —— 深度可观测性扩展（2026-08-25）——
# 当前审查上下文（工具内部埋点用；无值 = 不在审查链路中，静默跳过记录）。
# _run_crew_node 在 kickoff 前 set；Semgrep 规则集扫描、逐文件 LLM 分析等
# 不经 CrewAI 事件总线的动作读取它自动归属到当前审查。
current_review_ctx: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "current_review_ctx", default=None
)


def get_review_ctx() -> dict[str, str] | None:
    """读取当前审查上下文（None 表示不在审查链路中）"""
    return current_review_ctx.get()


def _truncate(text: Any, limit: int = 300) -> str | None:
    """安全截断为字符串（detail 摘要用）"""
    if text is None:
        return None
    s = text if isinstance(text, str) else str(text)
    if len(s) <= limit:
        return s
    return s[:limit] + f"…（截断，全文 {len(s)} 字符）"


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

    async def record_tool_substep(
        self,
        agent_name: str,
        node_type: str,
        action_text: str,
        duration_ms: int | None = None,
        detail: dict | None = None,
        status: str = "completed",
    ) -> None:
        """记录确定性扫描子步骤（自动从 contextvars 取审查归属；不在审查链路中则跳过）

        供各专业 Agent 在 Semgrep/Ruff/pip-audit/AST 等确定性环节调用，
        无需关心 review_id 从哪来。
        """
        ctx = get_review_ctx()
        if not ctx:
            return
        await self.record(
            review_id=ctx["review_id"],
            phase="tool",
            node_type=node_type,
            status=status,
            agent_name=agent_name,
            action_text=action_text,
            duration_ms=duration_ms,
            detail=detail or {},
        )

    async def record_llm_file_analysis(
        self,
        agent_name: str,
        file_path: str,
        prompt: str,
        reply: str | None,
        findings_count: int,
        latency_ms: int,
        usage: dict | None = None,
        success: bool = True,
    ) -> None:
        """记录一次工具内部的逐文件 LLM 分析

        全文（prompt/reply 原文）写入 llm_call_logs；
        review_steps 只写摘要行 + transcript_id 引用（时间线接口保持轻量）。
        不在审查链路中（ctx 为空）时跳过一切落库。
        """
        ctx = get_review_ctx()
        if not ctx:
            return
        review_id = ctx["review_id"]
        usage = usage or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)

        # 1) 全文档案（llm_call_logs）
        transcript_id: str | None = None
        try:
            from app.models.llm_call_log import LLMCallLog

            async with async_session_factory() as db:
                max_seq = (
                    await db.execute(
                        select(func.max(LLMCallLog.seq)).where(
                            LLMCallLog.review_id == review_id
                        )
                    )
                ).scalar()
                log = LLMCallLog(
                    review_id=review_id,
                    agent_name=agent_name,
                    seq=(max_seq or 0) + 1,
                    source="tool_internal",
                    call_type="file_analysis",
                    model=usage.get("model"),
                    messages=[{"role": "user", "content": prompt}],
                    response=reply,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=int(usage.get("total_tokens") or (prompt_tokens + completion_tokens)),
                    latency_ms=latency_ms,
                    success=success,
                )
                db.add(log)
                await db.commit()
                await db.refresh(log)
                transcript_id = log.id
        except Exception as e:
            logger.warning("LLM 全文日志写入失败", error=str(e), review_id=review_id)

        # 2) 时间线摘要步骤
        file_short = file_path.rsplit("/", 1)[-1]
        status_word = "成功" if success else "失败"
        await self.record(
            review_id=review_id,
            phase="llm",
            node_type="llm_file_analysis",
            status="completed" if success else "failed",
            agent_name=agent_name,
            action_text=(
                f"🧠 LLM 语义分析 {file_short}：发现 {findings_count} 个问题"
                f"（{prompt_tokens + completion_tokens} tokens，{latency_ms / 1000:.1f}s，{status_word}）"
            ),
            input_summary=f"{file_path}（提示词 {len(prompt)} 字符）",
            output_summary=f"{findings_count} 条发现" if success else "分析失败",
            duration_ms=latency_ms,
            detail={
                "file_path": file_path,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "findings": findings_count,
                "transcript_id": transcript_id,
                "reply_preview": _truncate(reply, 200),
            },
        )


    async def record_crewai_llm_call(
        self,
        review_id: str,
        agent_name: str,
        call_type: str,
        model: str | None,
        messages: list | None,
        response_text: str,
        latency_ms: int,
        usage: dict | None = None,
        success: bool = True,
        error: str | None = None,
        seq_no: int = 0,
    ) -> None:
        """记录一次框架层（CrewAI 事件总线捕获的）LLM 调用

        全文写 llm_call_logs（source="crewai"），时间线写摘要步骤 + transcript 引用。
        由 crew_event_bridge 的排空器在主循环调用。
        """
        usage = usage or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)

        # 1) 全文档案
        transcript_id: str | None = None
        try:
            from app.models.llm_call_log import LLMCallLog

            async with async_session_factory() as db:
                max_seq = (
                    await db.execute(
                        select(func.max(LLMCallLog.seq)).where(
                            LLMCallLog.review_id == review_id
                        )
                    )
                ).scalar()
                log = LLMCallLog(
                    review_id=review_id,
                    agent_name=agent_name,
                    seq=(max_seq or 0) + 1,
                    source="crewai",
                    call_type=call_type,
                    model=model,
                    messages=messages,
                    response=response_text if success else None,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=int(usage.get("total_tokens") or (prompt_tokens + completion_tokens)),
                    latency_ms=latency_ms,
                    success=success,
                )
                db.add(log)
                await db.commit()
                await db.refresh(log)
                transcript_id = log.id
        except Exception as e:
            logger.warning("框架层 LLM 全文日志写入失败", error=str(e), review_id=review_id)

        # 2) 时间线摘要步骤
        if success:
            if call_type == "tool_call":
                action = (
                    f"🧠 模型调用 #{seq_no}：决定调用工具（模型 {model or '?'}，"
                    f"{prompt_tokens + completion_tokens} tokens，{latency_ms / 1000:.1f}s）"
                )
                output_summary = "决策：调用工具"
            else:
                action = (
                    f"🧠 模型调用 #{seq_no}：输出整理结果（模型 {model or '?'}，"
                    f"{prompt_tokens + completion_tokens} tokens，{latency_ms / 1000:.1f}s）"
                )
                output_summary = _truncate(response_text, 200)
        else:
            action = f"⚠️ 模型调用 #{seq_no} 失败：{_truncate(error, 120)}"
            output_summary = "调用失败"

        await self.record(
            review_id=review_id,
            phase="llm",
            node_type="llm_call",
            status="completed" if success else "failed",
            agent_name=agent_name,
            action_text=action,
            input_summary=f"提示词 {sum(len(str(m.get('content', ''))) for m in (messages or []))} 字符",
            output_summary=output_summary,
            duration_ms=latency_ms if latency_ms else None,
            detail={
                "model": model,
                "call_type": call_type,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "transcript_id": transcript_id,
                "response_preview": _truncate(response_text, 300),
                "error": error,
            },
        )


# 全局单例
review_step_recorder = ReviewStepRecorder()
