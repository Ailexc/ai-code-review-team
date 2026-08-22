"""自动修复相关 Pydantic 模型"""

from pydantic import BaseModel
from typing import Optional


class AutoFixPatch(BaseModel):
    """单个修复补丁"""
    type: str  # ruff / llm
    file: Optional[str] = None
    diff: str
    files: Optional[list[str]] = None


class AutoFixResult(BaseModel):
    """自动修复结果"""
    patches: list[AutoFixPatch]
    fixed_files: list[str]
    skipped: list[dict]
    summary: str
