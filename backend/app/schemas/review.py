"""审查相关 Pydantic 模型"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ReviewCreate(BaseModel):
    """创建审查请求"""
    project_id: str = Field(..., description="项目ID")
    review_type: str = Field("full", description="审查类型: full, security, code_style, dependency, test_coverage")
    trigger_type: str = Field("manual", description="触发类型: manual, scheduled, webhook")


class ReviewResponse(BaseModel):
    """审查响应"""
    id: str
    project_id: str
    trigger_type: str
    status: str
    review_type: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    health_score_snapshot: Optional[float] = None
    total_findings: int = 0
    critical_count: int = 0
    warning_count: int = 0
    suggestion_count: int = 0
    nitpick_count: int = 0
    summary: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
