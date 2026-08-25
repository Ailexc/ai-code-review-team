"""LLM 调用全文日志 — 可观测性深度学习数据

完整留存每次 LLM 调用的提示词原文与响应原文（用户决策：完整留存供学习）：
- source="crewai"：框架层调用（Agent 的 ReAct 决策/收尾），由事件桥接器写入；
- source="tool_internal"：工具内部逐文件分析（原生 httpx，不经框架），由 llm_client 写入。

review_steps.detail 只存截断摘要 + transcript_id 引用，时间线接口保持轻量；
全文通过 GET /reviews/{review_id}/llm-logs/{log_id} 按需拉取。
随 Review 级联删除。
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LLMCallLog(Base):
    """单次 LLM 调用的完整输入输出（学习用全文档案）"""

    __tablename__ = "llm_call_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    review_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_name: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    # 审查内递增序号（按写入顺序）
    seq: Mapped[int] = mapped_column(Integer, default=0)

    # crewai = 框架层调用；tool_internal = 工具内部原生 httpx 调用
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="crewai")
    # tool_call / llm_call / file_analysis
    call_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # 完整内容（messages: [{role, content}, ...]；response 为模型返回原文）
    messages: Mapped[list | None] = mapped_column(JSON, nullable=True)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)

    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self):
        return f"<LLMCallLog(review={self.review_id[:8]}, agent={self.agent_name}, model={self.model})>"
