"""审查发现相关 Pydantic 模型"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class FindingResponse(BaseModel):
    """审查发现响应"""
    id: str
    review_id: str
    agent_name: str
    category: str
    severity: str
    status: str = "open"
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    column_number: Optional[int] = None
    code_snippet: Optional[str] = None
    message: str
    description: Optional[str] = None
    suggestion: Optional[str] = None
    reference_url: Optional[str] = None
    is_auto_fixable: bool = False
    fix_suggestion: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
