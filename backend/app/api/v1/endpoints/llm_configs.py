"""LLM 模型配置 API"""

import time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

import structlog

from app.core.database import get_db
from app.models.llm_config import LLMConfig
from app.schemas.llm_config import (
    LLMConfigCreate, LLMConfigUpdate, LLMConfigResponse, LLMTestResult,
)

logger = structlog.get_logger()
router = APIRouter()


def _to_response(config: LLMConfig) -> LLMConfigResponse:
    return LLMConfigResponse(
        id=config.id,
        name=config.name,
        provider=config.provider,
        model=config.model,
        api_key_set=bool(config.api_key),
        base_url=config.base_url,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
        is_default=config.is_default,
        is_enabled=config.is_enabled,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.get("", response_model=list[LLMConfigResponse])
async def list_configs(db: AsyncSession = Depends(get_db)):
    """获取所有模型配置"""
    result = await db.execute(select(LLMConfig).order_by(LLMConfig.created_at.desc()))
    return [_to_response(c) for c in result.scalars().all()]


@router.post("", response_model=LLMConfigResponse, status_code=201)
async def create_config(data: LLMConfigCreate, db: AsyncSession = Depends(get_db)):
    """创建模型配置"""
    existing = await db.execute(select(LLMConfig).where(LLMConfig.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"配置名 '{data.name}' 已存在")

    # 如果设为默认，取消其他默认
    if data.is_default:
        await _clear_defaults(db)

    config = LLMConfig(**data.model_dump())
    db.add(config)
    await db.flush()
    await db.refresh(config)
    logger.info("创建模型配置", name=config.name, model=config.model)
    return _to_response(config)


@router.put("/{config_id}", response_model=LLMConfigResponse)
async def update_config(config_id: str, data: LLMConfigUpdate, db: AsyncSession = Depends(get_db)):
    """更新模型配置"""
    result = await db.execute(select(LLMConfig).where(LLMConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")

    update_data = data.model_dump(exclude_unset=True)

    # 如果设为默认，取消其他默认
    if update_data.get("is_default"):
        await _clear_defaults(db)

    # 如果 api_key 为空字符串，设为 None（清除）
    if update_data.get("api_key") == "":
        update_data["api_key"] = None

    for field, value in update_data.items():
        setattr(config, field, value)

    await db.flush()
    await db.refresh(config)
    return _to_response(config)


@router.delete("/{config_id}", status_code=204)
async def delete_config(config_id: str, db: AsyncSession = Depends(get_db)):
    """删除模型配置"""
    result = await db.execute(select(LLMConfig).where(LLMConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    await db.delete(config)


@router.post("/{config_id}/test", response_model=LLMTestResult)
async def test_config(config_id: str, db: AsyncSession = Depends(get_db)):
    """测试模型连接"""
    result = await db.execute(select(LLMConfig).where(LLMConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")

    if not config.api_key and config.provider not in ("ollama",):
        return LLMTestResult(success=False, message="未设置 API Key")

    try:
        import httpx

        base_url = config.base_url or _get_default_base_url(config.provider)
        headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}

        start = time.monotonic()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json={
                    "model": config.model,
                    "messages": [{"role": "user", "content": "Say 'OK' in one word."}],
                    "max_tokens": 10,
                },
            )
        latency = int((time.monotonic() - start) * 1000)

        if resp.status_code == 200:
            data = resp.json()
            reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return LLMTestResult(
                success=True,
                message=f"连接成功，模型回复: {reply.strip()[:50]}",
                model=config.model,
                latency_ms=latency,
            )
        else:
            return LLMTestResult(
                success=False,
                message=f"API 返回 {resp.status_code}: {resp.text[:200]}",
            )
    except Exception as e:
        return LLMTestResult(success=False, message=f"连接失败: {e}")


def _get_default_base_url(provider: str) -> str:
    urls = {
        "openai": "https://api.openai.com/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "ollama": "http://localhost:11434/v1",
    }
    return urls.get(provider, "https://api.openai.com/v1")


async def _clear_defaults(db: AsyncSession):
    result = await db.execute(select(LLMConfig).where(LLMConfig.is_default == True))
    for config in result.scalars().all():
        config.is_default = False
