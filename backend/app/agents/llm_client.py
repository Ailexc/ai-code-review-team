"""共享 LLM 客户端 — 配置获取、并发调用、JSON 解析

供各 Agent（安全/规范/依赖等）复用，避免重复代码。
"""

import asyncio
import json
import time
from typing import Any, Optional

import httpx
import structlog

from app.services.metrics import metrics
from app.services.review_steps import get_review_ctx

logger = structlog.get_logger()

# 默认兼容地址（当配置未提供 base_url 时）
DEFAULT_BASE_URL = "https://api.xiaomimimo.com/v1"


async def get_active_llm_config():
    """获取启用的 LLM 配置

    优先级：启用且默认且有 Key > 启用且有 Key（任意）
    """
    from app.models.llm_config import LLMConfig
    from app.core.database import async_session_factory
    from sqlalchemy import select

    async with async_session_factory() as db:
        result = await db.execute(
            select(LLMConfig)
            .where(
                LLMConfig.is_enabled == True,
                LLMConfig.api_key.isnot(None)
            )
            .order_by(LLMConfig.is_default.desc())
        )
        return result.scalars().first()


async def llm_complete(
    config,
    prompt: str,
    *,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    timeout: float = 90,
) -> Optional[str]:
    """调用 LLM 补全，返回 content 文本；失败返回 None"""
    content, _usage = await llm_complete_with_usage(
        config, prompt, max_tokens=max_tokens, temperature=temperature, timeout=timeout
    )
    return content


async def llm_complete_with_usage(
    config,
    prompt: str,
    *,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    timeout: float = 90,
) -> tuple[Optional[str], dict]:
    """调用 LLM 补全，返回 (content 文本, usage 字典)；失败返回 (None, {})

    usage: {model, prompt_tokens, completion_tokens, total_tokens}（可观测性用）
    """
    base_url = config.base_url or DEFAULT_BASE_URL
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.model,
        "messages": [{"role": "user", "content": prompt}],
        # 推理模型需要足够 token 预算，这里统一封顶 4096
        "max_tokens": min(max_tokens or config.max_tokens, 4096),
        "temperature": config.temperature if temperature is None else temperature,
    }
    try:
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
        latency = time.monotonic() - t0
        if resp.status_code != 200:
            metrics.record_llm_call(False, latency, model=config.model)
            logger.warning("LLM API 调用失败", status=resp.status_code, detail=resp.text[:200])
            return None, {}
        resp_json = resp.json()
        usage_raw = resp_json.get("usage", {})
        prompt_tokens = usage_raw.get("prompt_tokens", 0)
        completion_tokens = usage_raw.get("completion_tokens", 0)
        total_tokens = usage_raw.get("total_tokens", prompt_tokens + completion_tokens)
        metrics.record_llm_call(True, latency, total_tokens, model=config.model)
        usage = {
            "model": config.model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
        # 持久化 token 用量（重启不丢失；关联当前审查上下文）
        try:
            ctx = get_review_ctx()
            await _record_usage(
                model=config.model,
                config_name=config.name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                latency_ms=int(latency * 1000),
                success=True,
                review_id=(ctx or {}).get("review_id"),
            )
        except Exception as e:
            logger.warning("LLM 用量记录失败", error=str(e))
        return resp_json.get("choices", [{}])[0].get("message", {}).get("content", ""), usage
    except Exception as e:
        metrics.record_llm_call(False, 0, model=config.model)
        logger.warning("LLM 调用异常", error=str(e))
        return None, {}


async def _record_usage(
    model: str,
    config_name: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    latency_ms: int | None,
    success: bool,
    review_id: str | None = None,
):
    """持久化 LLM 调用用量到数据库（review_id 来自审查上下文，可空）"""
    from app.core.database import async_session_factory
    from app.models.llm_usage import LLMUsage

    async with async_session_factory() as db:
        usage = LLMUsage(
            model=model,
            config_name=config_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            success=success,
            review_id=review_id,
        )
        db.add(usage)
        await db.commit()


def parse_json_object(reply: str | None) -> Optional[dict]:
    """从 LLM 回复中提取 JSON 对象（容忍 markdown 代码围栏等噪音）"""
    if not reply:
        return None
    start = reply.find("{")
    end = reply.rfind("}") + 1
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(reply[start:end])
    except json.JSONDecodeError:
        logger.warning("LLM 返回的 JSON 解析失败", reply=reply[:200])
        return None


async def run_llm_analysis(
    config,
    prompts: list[tuple[str, str]],
    *,
    concurrency: int = 3,
    default_rule: str = "LLM",
) -> list[dict[str, Any]]:
    """并发调用 LLM 分析多个文件，返回标准化 findings

    Args:
        config: LLM 配置对象
        prompts: [(file_path, prompt), ...]
        concurrency: 最大并发数
        default_rule: rule_id 前缀

    在审查链路中时（contextvars 有值），每次文件分析自动记录：
    - llm_call_logs 全文档案（提示词/响应原文）
    - review_steps 时间线摘要步骤（tokens / 耗时 / 发现数）

    Returns:
        标准化 finding dict 列表
    """
    sem = asyncio.Semaphore(concurrency)

    async def _one(file_path: str, prompt: str) -> list[dict[str, Any]]:
        async with sem:
            t0 = time.monotonic()
            reply, usage = await llm_complete_with_usage(config, prompt)
            latency_ms = int((time.monotonic() - t0) * 1000)
        data = parse_json_object(reply)
        findings = []
        if data:
            for f in data.get("findings", []):
                findings.append({
                    "rule_id": f.get("rule_id", f"{default_rule}-{len(findings) + 1:03d}"),
                    "severity": f.get("severity", "suggestion"),
                    "message": f.get("message", ""),
                    "file_path": f.get("file_path", file_path),
                    "line_start": f.get("line_number"),
                    "code_snippet": f.get("code_snippet", "")[:500],
                    "suggestion": f.get("suggestion", ""),
                })
        # 可观测性：逐文件分析落库（不在审查链路中时内部自动跳过）
        try:
            from app.services.review_steps import review_step_recorder

            await review_step_recorder.record_llm_file_analysis(
                agent_name=(get_review_ctx() or {}).get("agent_name", ""),
                file_path=file_path,
                prompt=prompt,
                reply=reply,
                findings_count=len(findings),
                latency_ms=latency_ms,
                usage=usage,
                success=bool(reply),
            )
        except Exception as e:
            logger.warning("逐文件分析步骤记录失败", error=str(e))
        return findings

    results = await asyncio.gather(*[_one(fp, p) for fp, p in prompts])
    return [f for sublist in results for f in sublist]
