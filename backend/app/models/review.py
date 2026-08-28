"""审查记录模型"""

import uuid
from datetime import datetime
from sqlalchemy import String, Text, Integer, DateTime, Float, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.review_step import ReviewStep


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False)  # manual, scheduled, webhook
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)  # pending, running, completed, failed
    review_type: Mapped[str] = mapped_column(String(100), nullable=False)  # full, security, code_style, dependency, test_coverage
    # 编排模式：parallel = 6 独立 Crew 并行（默认）；hierarchical = manager 派发（学习对比用）
    orchestration_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="parallel")

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    health_score_snapshot: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_findings: Mapped[int] = mapped_column(Integer, default=0)
    critical_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    suggestion_count: Mapped[int] = mapped_column(Integer, default=0)
    nitpick_count: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # 关系
    project: Mapped["Project"] = relationship(back_populates="reviews")
    findings: Mapped[list["Finding"]] = relationship(back_populates="review", cascade="all, delete-orphan")
    steps: Mapped[list["ReviewStep"]] = relationship(
        back_populates="review", cascade="all, delete-orphan", order_by="ReviewStep.sequence"
    )

    def __repr__(self):
        return f"<Review(id={self.id}, status={self.status})>"
