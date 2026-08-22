"""LLM 调用用量模型 — 持久化每次 LLM 调用的 token 消耗"""

import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Float, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LLMUsage(Base):
    """LLM 调用用量记录（持久化，重启不丢失）"""

    __tablename__ = "llm_usage"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # 关联的审查（可选）
    review_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("reviews.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # 模型信息
    model: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    config_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # token 消耗
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    # 调用信息
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self):
        return f"<LLMUsage(model={self.model}, tokens={self.total_tokens})>"