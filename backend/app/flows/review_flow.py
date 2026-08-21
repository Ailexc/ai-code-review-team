"""ReviewFlow — CrewAI Flows 双层编排骨架

设计理念（与 docs/agent-learning-notes.md 一致）：
- 外层 Flow：确定性、白盒、可调试。用 @start / @listen 装饰器编排
  parse → dispatch → run → aggregate → report 的固定流程，状态用 Pydantic model 管理。
- 内层 Agent：复用已测试的 SecurityAgent / CodeStyleAgent（各自封装 LLM 调用），
  保持稳定的 LLM 接入，避免 CrewAI LLM 配置的脆弱性。

本 Flow 是可选的编排路径，生产路径仍是 ReviewService（直接编排）。
二者共享同一套 Agent 与共享 LLM 客户端，保证行为一致。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, Field

from app.agents.security_agent import SecurityAgent
from app.agents.code_style_agent import CodeStyleAgent

logger = structlog.get_logger()

# 尽量延迟导入 CrewAI，避免在不使用 Flow 时引入重型依赖
try:
    from crewai.flow.flow import Flow, listen, start
    _CREWAI_AVAILABLE = True
except Exception as e:  # pragma: no cover - 仅在依赖缺失时触发
    logger.warning("CrewAI 不可用，ReviewFlow 将以降级模式运行", error=str(e))
    _CREWAI_AVAILABLE = False
    Flow = object  # type: ignore

    def start(*a, **k):  # type: ignore
        def deco(fn):
            return fn
        return deco

    def listen(*a, **k):  # type: ignore
        def deco(fn):
            return fn
        return deco


class ReviewState(BaseModel):
    """Flow 共享状态 — 在各节点间传递"""

    project_path: str = ""
    project_name: str = "Unknown"
    file_paths: list[str] | None = None
    review_type: str = "full"

    # 各 Agent 的产出
    findings_by_agent: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    total_findings: int = 0
    summary: str = ""


# review_type → (Agent 类, agent_name, category)
_AGENT_MAP = {
    "security": (SecurityAgent, "security", "security"),
    "code_style": (CodeStyleAgent, "code_style", "code_style"),
}


def _resolve_agents(review_type: str) -> list[tuple[type, str, str]]:
    if review_type == "full":
        return list(_AGENT_MAP.values())
    if review_type in _AGENT_MAP:
        return [_AGENT_MAP[review_type]]
    return [_AGENT_MAP["security"]]


class ReviewFlow(Flow[ReviewState]):
    """代码审查编排 Flow

    用法:
        flow = ReviewFlow()
        result = await flow.kickoff_async(ReviewState(project_path=..., review_type="full"))
    """

    @start()
    def parse_project(self) -> None:
        """节点1：校验项目路径"""
        state = self.state
        path = Path(state.project_path)
        if not path.exists():
            logger.warning("ReviewFlow: 项目路径不存在", path=state.project_path)
        logger.info("ReviewFlow: 解析项目", path=state.project_path, type=state.review_type)

    @listen(parse_project)
    def dispatch_agents(self) -> None:
        """节点2：根据审查类型决定运行哪些 Agent"""
        agents = _resolve_agents(self.state.review_type)
        logger.info(
            "ReviewFlow: 分派 Agent",
            agents=[name for _, name, _ in agents],
        )

    @listen(dispatch_agents)
    async def run_agents(self) -> None:
        """节点3：并行运行各 Agent 并聚合结果

        内层：复用 SecurityAgent / CodeStyleAgent，它们各自封装 LLM 调用。
        """
        import asyncio

        state = self.state
        agents = _resolve_agents(state.review_type)
        path = Path(state.project_path)

        async def _run_one(agent_cls, agent_name: str):
            agent = agent_cls()
            findings = await agent.analyze(
                project_path=state.project_path,
                file_paths=state.file_paths,
            )
            return agent_name, findings

        results = await asyncio.gather(
            *[_run_one(cls, name) for cls, name, _ in agents]
        )

        for agent_name, findings in results:
            state.findings_by_agent[agent_name] = findings

    @listen(run_agents)
    def aggregate(self) -> None:
        """节点4：聚合去重 + 统计"""
        state = self.state
        seen: set[tuple] = set()
        all_findings: list[dict[str, Any]] = []
        for findings in state.findings_by_agent.values():
            for f in findings:
                key = (f.get("rule_id"), f.get("file_path"), f.get("line_start"))
                if key not in seen:
                    seen.add(key)
                    all_findings.append(f)

        state.total_findings = len(all_findings)
        parts = []
        for sev, label in (("critical", "🔴"), ("warning", "🟡"), ("suggestion", "🔵"), ("nitpick", "⚪")):
            count = sum(1 for f in all_findings if f.get("severity") == sev)
            if count:
                parts.append(f"{label} {count} 个{ {'critical':'严重','warning':'警告','suggestion':'建议','nitpick':'细节'}[sev] }")
        state.summary = "✅ 未发现问题" if not parts else f"发现 {state.total_findings} 个问题：" + "，".join(parts)
        logger.info("ReviewFlow: 聚合完成", total=state.total_findings)

    @listen(aggregate)
    def generate_report(self) -> ReviewState:
        """节点5：完成（报告生成在 API 层按需调用 ReportGenerator）"""
        logger.info("ReviewFlow: 编排完成", summary=self.state.summary)
        return self.state


async def run_review_flow(
    project_path: str,
    review_type: str = "full",
    file_paths: list[str] | None = None,
    project_name: str = "Unknown",
) -> ReviewState:
    """便捷入口：运行 ReviewFlow 并返回最终状态"""
    if not _CREWAI_AVAILABLE:
        raise RuntimeError("CrewAI 不可用，无法运行 ReviewFlow")

    flow = ReviewFlow()
    # CrewAI Flow 的 kickoff 接收 dict（而非 Pydantic 实例），内部构造状态
    inputs = {
        "project_path": project_path,
        "review_type": review_type,
        "file_paths": file_paths,
        "project_name": project_name,
    }
    result = await flow.kickoff_async(inputs)
    # kickoff 返回 StateWithId 包装对象，其属性代理到底层 state
    # 重新构造为 ReviewState 以获得稳定类型
    return ReviewState(
        project_path=getattr(result, "project_path", project_path),
        review_type=getattr(result, "review_type", review_type),
        file_paths=getattr(result, "file_paths", file_paths),
        project_name=getattr(result, "project_name", project_name),
        findings_by_agent=dict(getattr(result, "findings_by_agent", {}) or {}),
        total_findings=getattr(result, "total_findings", 0),
        summary=getattr(result, "summary", ""),
    )
