"""审查过程步骤模型 — 可观测性核心

持久化审查执行的每一步（外层 Flow 节点 / 内层 Crew / 工具调用 / LLM 调用），
让用户对审查过程"清清楚楚感知每一步"：做了什么、输入/输出、耗时、跳过/异常。
随 Review 级联删除。
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ReviewStep(Base):
    __tablename__ = "review_steps"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    review_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0)  # 时间线排序
    phase: Mapped[str] = mapped_column(String(20), nullable=False, default="outer_flow")
    # outer_flow / inner_crew / tool / llm / info
    node_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # parse_project / run_*_crew / aggregate / generate_report / skip_agent / tool_call / llm_call ...
    agent_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    # running / completed / skipped / failed

    action_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # 中文：这一步做了什么
    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 额外详情（tokens/异常/跳过原因等）

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # 关系
    review: Mapped["Review"] = relationship(back_populates="steps")

    def __repr__(self):
        return f"<ReviewStep(review={self.review_id[:8]}, seq={self.sequence}, {self.node_type}, {self.status})>"
