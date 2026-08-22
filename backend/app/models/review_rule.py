"""审查规则模型 — 从历史审查中学习的团队规范"""

import uuid
from datetime import datetime
from sqlalchemy import String, Text, Integer, Boolean, DateTime, Float, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ReviewRule(Base):
    """审查规则 — 从历史 finding 挖掘的团队规范"""

    __tablename__ = "review_rules"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 规则类型: pattern(模式) / convention(规范) / preference(偏好)
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False, default="pattern")
    # 关联的 Agent 和严重度
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(50), nullable=False, default="suggestion")
    # 规则内容（正则/关键词/描述）
    pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 学习来源（历史 finding 的 message 模式）
    source_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 置信度（0-1）和出现次数
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=0)
    # 权重（影响审查时的优先级）
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # 学习来源: auto(自动挖掘) / manual(手动) / feedback(用户反馈)
    source: Mapped[str] = mapped_column(String(50), default="auto")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self):
        return f"<ReviewRule(name={self.name}, agent={self.agent_name}, confidence={self.confidence})>"