"""审查步骤响应 schema — 可观测性"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class ReviewStepResponse(BaseModel):
    """审查执行步骤（时间线节点）"""

    id: str
    review_id: str
    sequence: int
    phase: str          # outer_flow / inner_crew / tool / llm / info
    node_type: str
    agent_name: Optional[str] = None
    status: str         # running / completed / skipped / failed
    action_text: Optional[str] = None
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    detail: Optional[dict[str, Any]] = None

    model_config = {"from_attributes": True}


class LLMLogResponse(BaseModel):
    """LLM 调用全文档案（提示词/响应原文，学习用）"""

    id: str
    review_id: str
    agent_name: Optional[str] = None
    seq: int
    source: str            # crewai / tool_internal
    call_type: Optional[str] = None
    model: Optional[str] = None
    messages: Optional[list] = None
    response: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: Optional[int] = None
    success: bool = True
    created_at: datetime

    model_config = {"from_attributes": True}
