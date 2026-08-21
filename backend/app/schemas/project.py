"""项目相关 Pydantic 模型"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ProjectCreate(BaseModel):
    """创建项目请求"""
    name: str = Field(..., min_length=1, max_length=255, description="项目名称")
    path: str = Field(..., min_length=1, max_length=1024, description="项目路径")
    description: Optional[str] = Field(None, description="项目描述")
    language: Optional[str] = Field(None, description="编程语言")
    framework: Optional[str] = Field(None, description="框架")


class ProjectUpdate(BaseModel):
    """更新项目请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    language: Optional[str] = None
    framework: Optional[str] = None
    is_active: Optional[bool] = None


class ProjectResponse(BaseModel):
    """项目响应"""
    id: str
    name: str
    path: str
    description: Optional[str] = None
    language: Optional[str] = None
    framework: Optional[str] = None
    git_remote: Optional[str] = None
    health_score: float = 0.0
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    """项目列表响应"""
    items: List[ProjectResponse]
    total: int
    page: int
    page_size: int
