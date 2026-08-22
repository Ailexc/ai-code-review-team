"""LLM 变更意图分析 — 理解代码变更的目的和影响

对标 CodeRabbit / Qodo 的语义理解：
1. 分析变更意图（这个变更想做什么）
2. 识别跨文件影响（遗漏的配套修改）
3. 生成变更摘要
"""

from typing import Any

import structlog

logger = structlog.get_logger()

# LLM 意图分析提示词
INTENT_PROMPT = """你是一个资深代码审查专家。请分析以下代码变更的意图和影响。

## 变更文件
{changed_files}

## 结构化变更
{structural_changes}

## 影响分析
{impact_analysis}

请用 JSON 格式返回分析结果:
```json
{{
    "summary": "变更的整体目的和意图（2-3 句话）",
    "intent": "这个变更想解决什么问题",
    "risks": [
        {{
            "risk": "风险描述",
            "severity": "high/medium/low",
            "suggestion": "建议"
        }}
    ],
    "missing_changes": [
        {{
            "description": "可能遗漏的配套修改",
            "reason": "为什么需要这个修改"
        }}
    ]
}}
```

审查重点:
1. 变更意图是否清晰，是否与提交信息一致
2. 是否有跨文件的配套修改遗漏（如调用方未更新）
3. 是否有破坏性变更（API 签名变化、删除函数等）
4. 是否有潜在风险（兼容性、性能、安全）

注意:
1. 只返回 JSON，不要有其他内容
2. 如果没有风险，返回空数组: {{"risks": [], "missing_changes": []}}"""


async def analyze_intent(
    diff_result: dict,
) -> dict:
    """分析变更意图

    Args:
        diff_result: SemanticDiff.analyze() 的返回结果

    Returns:
        { summary, intent, risks, missing_changes }
    """
    try:
        from app.agents.llm_client import get_active_llm_config, llm_complete, parse_json_object

        config = await get_active_llm_config()
        if not config:
            return {"summary": "未配置 LLM，跳过意图分析", "intent": "", "risks": [], "missing_changes": []}

        # 组装 prompt
        changed_files = "\n".join(diff_result.get("changed_files", []))
        structural_changes = "\n".join(
            f"- [{c['type']}] {c['description']} (line {c['line']})"
            for c in diff_result.get("structural_changes", [])
        )
        impact_analysis = "\n".join(
            f"- {i['message']} (risk: {i['risk']})"
            for i in diff_result.get("impact_analysis", [])
        )

        prompt = INTENT_PROMPT.format(
            changed_files=changed_files or "(无)",
            structural_changes=structural_changes or "(无结构化变更)",
            impact_analysis=impact_analysis or "(无影响分析)",
        )

        reply = await llm_complete(config, prompt)
        data = parse_json_object(reply)
        if not data:
            return {"summary": "意图分析失败", "intent": "", "risks": [], "missing_changes": []}

        return {
            "summary": data.get("summary", ""),
            "intent": data.get("intent", ""),
            "risks": data.get("risks", []),
            "missing_changes": data.get("missing_changes", []),
        }
    except Exception as e:
        logger.warning("意图分析失败", error=str(e))
        return {"summary": "意图分析失败", "intent": "", "risks": [], "missing_changes": []}