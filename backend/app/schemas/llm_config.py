"""LLM 模型配置 Schemas"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class LLMConfigCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="配置名称，如 'gpt-4o'")
    provider: str = Field(..., description="提供商: openai / deepseek / ollama / custom")
    model: str = Field(..., description="模型名称，如 gpt-4o / deepseek-chat")
    api_key: Optional[str] = Field(None, description="API Key")
    base_url: Optional[str] = Field(None, description="自定义 API 地址")
    max_tokens: int = Field(4096, ge=1)
    temperature: float = Field(0.1, ge=0, le=2)
    is_default: bool = Field(False, description="设为默认模型")
    is_enabled: bool = Field(True)


class LLMConfigUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    is_default: Optional[bool] = None
    is_enabled: Optional[bool] = None


class LLMConfigResponse(BaseModel):
    id: str
    name: str
    provider: str
    model: str
    api_key_set: bool  # 不返回真实 key，只返回是否已设置
    base_url: Optional[str] = None
    max_tokens: int
    temperature: float
    is_default: bool
    is_enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LLMTestResult(BaseModel):
    success: bool
    message: str
    model: Optional[str] = None
    latency_ms: Optional[int] = None
