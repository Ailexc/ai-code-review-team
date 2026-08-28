"""内层 Crew 工厂 — CrewAI Flows + Crews 双层架构的「内层」

每个专业 Agent 构建一个独立 Crew（上下文隔离）：
- Agent：CrewAI 角色定义（role / goal / backstory / tools / llm）
- Task：审查任务描述 + 期望输出（output_pydantic 强约束）
- Crew：单 Agent 独立 Crew（Process.sequential），自主调用工具完成审查

确定性审查逻辑（Semgrep/Ruff/pip-audit/AST + LLM 分析）封装为 CrewAI 工具，
由 Agent 自主调用，体现「工具调用 + 自主分析」的内层协作模式。

本模块是生产主路径的一部分：外层 ReviewFlow 通过 build_review_crew() 为
每个参与的 Agent 构建 Crew，并行 kickoff。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import structlog
from crewai import Agent, Crew, Process, Task
from crewai.llm import LLM
from crewai.tools import tool
from pydantic import BaseModel, Field

from app.agents.code_style_agent import CodeStyleAgent
from app.agents.dependency_agent import DependencyAgent
from app.agents.git_review_agent import GitReviewAgent
from app.agents.llm_client import DEFAULT_BASE_URL
from app.agents.performance_agent import PerformanceAgent
from app.agents.security_agent import SecurityAgent
from app.agents.test_coverage_agent import TestCoverageAgent

# CrewAI 默认把任务输出存储写到「用户数据目录」（`~/Library/Application Support/...`
# 或 `~/.local/share/...`），可能不可写或污染用户环境。
# 统一重定向到项目内可写目录（backend/data/crewai），任何部署环境均可写。
os.environ.setdefault(
    "CREWAI_STORAGE_DIR",
    str(Path(__file__).resolve().parent.parent / "data" / "crewai"),
)

logger = structlog.get_logger()

# ============ 专业 Agent 的 CrewAI 角色定义 ============

AGENT_PROFILES: dict[str, dict[str, Any]] = {
    "security": {
        "agent_cls": SecurityAgent,
        "role": "资深代码安全审查专家",
        "goal": "全面检测项目代码中的安全漏洞：SQL注入、命令注入、XSS、硬编码密钥、危险反序列化、eval 滥用等",
        "backstory": (
            "你是一位拥有 15 年应用安全经验的工程师，精通 OWASP Top 10 与常见漏洞模式。"
            "你会调用安全扫描工具获取静态扫描结果（Semgrep 规则集 + LLM 语义分析），"
            "审阅结果并输出可执行的修复建议。你只报告真实存在的风险，不编造发现。"
        ),
    },
    "code_style": {
        "agent_cls": CodeStyleAgent,
        "role": "代码规范审查专家",
        "goal": "检查代码规范问题：命名规范、函数复杂度、重复代码、缺少类型注解、import 排序等",
        "backstory": (
            "你是一位资深代码评审专家，对 Python/JS/TS 等语言的代码风格与可维护性有严格标准。"
            "你会调用规范检查工具获取静态检查结果（Ruff + LLM 点评），"
            "输出具体到文件与行号的改进建议。"
        ),
    },
    "dependency": {
        "agent_cls": DependencyAgent,
        "role": "依赖安全审查专家",
        "goal": "审查项目依赖的安全性：已知漏洞（pip-audit）、过时依赖（npm registry）、供应链风险",
        "backstory": (
            "你是一位供应链安全专家，熟悉 Python pip 与 Node.js npm 生态的漏洞披露机制。"
            "你会调用依赖扫描工具获取漏洞与过时检测结果，"
            "并评估每个风险的影响面与修复建议。"
        ),
    },
    "test_coverage": {
        "agent_cls": TestCoverageAgent,
        "role": "测试覆盖审查专家",
        "goal": "识别未被测试覆盖的函数与分支，评估测试质量，给出补测建议",
        "backstory": (
            "你是一位测试工程专家，擅长通过 AST 分析发现未测试的代码路径。"
            "你会调用测试覆盖分析工具获取未测试函数清单，"
            "并结合代码上下文给出有针对性的测试建议。"
        ),
    },
    "performance": {
        "agent_cls": PerformanceAgent,
        "role": "性能分析专家",
        "goal": "识别性能反模式：N+1 查询、循环内同步阻塞调用、全表扫描、字符串循环拼接等",
        "backstory": (
            "你是一位后端性能优化专家，对数据库访问模式与异步编程的性能陷阱非常敏感。"
            "你会调用性能分析工具获取 AST 层面的模式检测结果，"
            "并给出量化分析与优化建议。"
        ),
    },
    "git_review": {
        "agent_cls": GitReviewAgent,
        "role": "Git 变更审查专家",
        "goal": "审查 Git 提交与变更：提交规范、分支策略、变更范围、潜在风险",
        "backstory": (
            "你是一位 DevOps 与代码评审专家，关注提交质量与变更风险。"
            "你会调用 Git 审查工具获取仓库状态与变更分析结果，"
            "并评估变更的完整性与潜在问题。"
        ),
    },
}

# ============ 结构化输出约束 ============


class FindingItem(BaseModel):
    """单条审查发现（与现有 AgentFinding 对齐）"""

    rule_id: str = ""
    severity: str = "warning"  # critical / warning / suggestion / nitpick
    message: str = ""
    file_path: str = ""
    line_start: int | None = None
    line_end: int | None = None
    code_snippet: str = ""
    suggestion: str = ""


class FindingsOutput(BaseModel):
    """Task 的结构化输出 — 约束 Agent 输出为 findings 列表"""

    findings: list[FindingItem] = Field(default_factory=list)


# ============ LLM 适配 ============


def build_crew_llm(config) -> LLM:
    """用项目数据库中的 LLM 配置构造 CrewAI LLM（OpenAI 兼容端点）"""
    return LLM(
        model=config.model,
        base_url=config.base_url or DEFAULT_BASE_URL,
        api_key=config.api_key,
        temperature=getattr(config, "temperature", 0.2),
    )


# ============ 工具封装 ============


def _make_scan_tool(
    agent_name: str,
    agent_cls: type,
    project_path: str,
    file_paths: list[str] | None,
) -> Any:
    """把现有确定性审查逻辑（analyze）封装为 CrewAI 工具

    通过闭包绑定 project_path / file_paths，工具无需 LLM 传参即可调用，
    保证工具调用环节可靠；Agent 负责决定调用并整理结果。
    """

    # result_as_answer=True：工具返回的 findings 已是确定的最终结果（schema 确定），
    # 直接作为 Agent 最终答案，跳过 CrewAI 的收尾 LLM 重新格式化（大幅提速，实测验证）。
    # 注意：必须返回 {"findings": [...]} 对象（而非顶层数组），否则 Task 的
    # output_pydantic=FindingsOutput 校验会失败（CrewAI convert_to_model 按对象解析）。
    @tool(f"{agent_name}_review_scan", result_as_answer=True)
    async def review_scan(path: str = "") -> str:
        """执行代码审查扫描，返回结构化 findings JSON（rule_id/severity/message/file_path/line_start/suggestion）。"""
        target = path or project_path
        agent = agent_cls()
        findings = await agent.analyze(project_path=target, file_paths=file_paths)
        return json.dumps({"findings": findings}, ensure_ascii=False)

    return review_scan


# ============ Crew 构建 ============


def build_review_crew(
    agent_name: str,
    project_path: str,
    file_paths: list[str] | None,
    llm: LLM,
    crew_name: str | None = None,
) -> Crew:
    """为单个专业 Agent 构建内层 Crew（上下文隔离）

    Args:
        agent_name: security / code_style / dependency / test_coverage / performance / git_review
        project_path: 待审查项目路径
        file_paths: 限定审查文件（None = 全项目）
        llm: CrewAI LLM 实例（build_crew_llm 构造）
        crew_name: Crew 唯一名称（"{review_id}:{agent_name}"），
                   供事件桥接器把框架事件归属到具体审查与 Agent

    Returns:
        配置好的 Crew，调用方负责 kickoff
    """
    profile = AGENT_PROFILES[agent_name]
    agent_cls = profile["agent_cls"]

    scan_tool = _make_scan_tool(agent_name, agent_cls, project_path, file_paths)

    agent = Agent(
        role=profile["role"],
        goal=profile["goal"],
        backstory=profile["backstory"],
        tools=[scan_tool],
        llm=llm,
        verbose=True,
        allow_delegation=False,  # 单 Agent 独立 Crew，不委派
    )

    task = Task(
        description=(
            f"对项目「{project_path}」执行{profile['role']}审查。\n\n"
            f"执行步骤：\n"
            f"1. 调用工具 `{agent_name}_review_scan` 获取扫描结果（工具内部已完成确定性扫描 + LLM 分析）；\n"
            f"2. 审阅工具返回的 findings，必要时结合你的专业知识补充缺失的发现；\n"
            f"3. 输出完整的 findings 列表。\n\n"
            f"硬性要求：\n"
            f"- 必须调用工具，不得凭空编造发现；\n"
            f"- 不得遗漏工具返回的任何发现；\n"
            f"- severity 取值：critical / warning / suggestion / nitpick；\n"
            f"- file_path 使用相对路径。"
        ),
        expected_output="JSON 对象：{\"findings\": [{rule_id, severity, message, file_path, line_start, code_snippet, suggestion}, ...]}",
        agent=agent,
        output_pydantic=FindingsOutput,
    )

    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
        name=crew_name or f"{agent_name}_crew",
    )
    logger.info("内层 Crew 构建完成", agent=agent_name, project=project_path, crew_name=crew_name)
    return crew


# ============ 结果解析 ============


def parse_crew_findings(crew_result) -> list[dict[str, Any]]:
    """把 Crew kickoff 结果解析为标准化 findings dict 列表（供服务层入库）"""
    findings: list[dict[str, Any]] = []

    # 1) output_pydantic 约束的输出
    pydantic_out = getattr(crew_result, "pydantic", None)
    if pydantic_out is not None:
        items = getattr(pydantic_out, "findings", None)
        if items:
            for it in items:
                findings.append({
                    "rule_id": it.rule_id,
                    "severity": it.severity,
                    "message": it.message,
                    "file_path": it.file_path,
                    "line_start": it.line_start,
                    "line_end": it.line_end,
                    "code_snippet": it.code_snippet,
                    "suggestion": it.suggestion,
                })
            return findings

    # 2) 原始文本兜底（容忍 JSON 噪音）
    raw = getattr(crew_result, "raw", None) or ""
    if raw:
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(raw[start:end])
                # 兼容两种格式：{"findings": [...]} 或顶层数组 [...]
                items = data.get("findings", []) if isinstance(data, dict) else data
                for f in items:
                    findings.append({
                        "rule_id": f.get("rule_id", ""),
                        "severity": f.get("severity", "warning"),
                        "message": f.get("message", ""),
                        "file_path": f.get("file_path", ""),
                        "line_start": f.get("line_start"),
                        "line_end": f.get("line_end"),
                        "code_snippet": f.get("code_snippet", ""),
                        "suggestion": f.get("suggestion", ""),
                    })
        except Exception as e:
            logger.warning("Crew 结果 JSON 解析失败", error=str(e))

    return findings
