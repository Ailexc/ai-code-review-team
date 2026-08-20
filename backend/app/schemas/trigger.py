"""触发器相关 Pydantic 模型"""

from pydantic import BaseModel, Field
from typing import Any, Optional


class TriggerRequest(BaseModel):
    """触发器请求"""
    trigger_type: str = Field(..., description="触发器类型: local_directory / code_paste / cli")
    # local_directory 参数
    path: Optional[str] = Field(None, description="本地目录路径（local_directory 触发器用）")
    # code_paste 参数
    code: Optional[str] = Field(None, description="粘贴的代码内容（code_paste 触发器用）")
    filename: Optional[str] = Field("pasted_code.py", description="文件名（code_paste 触发器用）")
    # cli 参数
    files: Optional[list[str]] = Field(None, description="文件列表（cli 触发器用）")
    # 通用
    project_id: Optional[str] = Field(None, description="关联的项目 ID")


class TriggerResponse(BaseModel):
    """触发器执行结果"""
    success: bool
    trigger_type: str
    files: list[str] = []
    file_count: int = 0
    metadata: dict[str, Any] = {}
    error: Optional[str] = None


class TriggerTypeInfo(BaseModel):
    """触发器类型信息"""
    name: str
    description: str


class TriggerListResponse(BaseModel):
    """可用触发器列表"""
    triggers: list[TriggerTypeInfo]
